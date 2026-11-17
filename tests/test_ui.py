import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import pymupdf
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QCoreApplication, QEvent
from revisor.__main__ import Window
from revisor.auth import AuthError
from revisor.packet import build_packet
from revisor.review import Finding


class UnifiedWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = Window(self.root / "app")
        self.window.run_job = lambda operation, done: done(operation(lambda _text: None, threading.Event()))
        self.source = self.make_pdf("relatorio.pdf", "Relatorio de Hidrogenio. " * 8 + "\nAnexo 1 - Relatorio de Ensaio\nAprovado por:")
        self.window.add_paths([str(self.source)])

    def make_pdf(self, name, text, pages=1):
        path = self.root / name
        document = pymupdf.open()
        for index in range(pages):
            document.new_page().insert_text((40, 40), text + f"\nPagina de teste {index+1}")
        document.save(path)
        document.close()
        return path

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def ready_ai(self):
        self.window.ia_ready = True
        self.window.models.clear()
        self.window.models.addItem("Modelo de teste", "test-model")
        self.window.use_ai.setChecked(True)

    def test_refusing_consent_never_sends_or_logs(self):
        self.ready_ai()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), patch("revisor.ai.review_packet") as infer:
            self.window.start_review()
        infer.assert_not_called()
        self.assertFalse((self.window.root / "envios.jsonl").exists())
        self.assertIsNone(self.window.review)

    def test_ai_first_then_local_rules_and_safe_audit(self):
        self.ready_ai()
        events = []
        from revisor.packet import local_review
        def infer(*args):
            events.append("ia")
            return [], []
        def local(packet):
            events.append("local")
            return local_review(packet)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), patch("revisor.ai.review_packet", side_effect=infer), patch("revisor.workspace_ui.local_review", side_effect=local):
            self.window.start_review()
        self.assertEqual(events, ["ia", "local"])
        self.assertEqual(self.window.review.ai_status, "concluida")
        log = (self.window.root / "envios.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("base64", log)
        self.assertEqual([json.loads(line)["status"] for line in log.splitlines()], ["autorizado", "concluido"])

    def test_ai_failure_is_visible_and_local_results_remain_available(self):
        self.ready_ai()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), patch("revisor.ai.review_packet", side_effect=AuthError("Sem permissão para IA")), patch.object(self.window, "show_error") as warning:
            self.window.start_review()
        self.assertEqual(self.window.review.ai_status, "falhou")
        self.assertTrue(self.window.review.findings)
        self.assertIn("IA falhou", self.window.summary.text())
        warning.assert_called_once()

    def test_offline_review_does_not_call_ai(self):
        with patch("revisor.ai.review_packet") as infer:
            self.window.start_review()
        infer.assert_not_called()
        self.assertEqual(self.window.review.ai_status, "nao_utilizada")

    def test_attachments_added_later_use_the_same_entry_point(self):
        self.window.start_review()
        old_id = self.window.review.id
        annex = self.make_pdf("anexo.pdf", "Certificado de calibracao de teste " * 6)
        self.window.add_paths([str(annex)])
        self.window.start_review()
        self.assertEqual(len(self.window.review.documents), 2)
        self.assertEqual(self.window.review.source["name"], "relatorio.pdf")
        self.assertNotEqual(self.window.review.id, old_id)
        self.assertTrue(any(e.get("previous_review") == old_id for e in self.window.review.audit))

    def test_clicking_ai_finding_navigates_to_attachment_page(self):
        annex = self.make_pdf("anexo.pdf", "Laudo de teste " * 10, pages=2)
        self.window.add_paths([str(annex)])
        self.window.start_review()
        digest = self.window.entries[1][2]
        finding = Finding("test-ai", "IA-01", "alerta", "Conferir anexo", 2, "Dado não confirmado", "Conferir", origin="ia", document_sha256=digest)
        self.window.review.findings.insert(0, finding)
        self.window.show_review(self.window.review)
        self.assertEqual(self.window.active_entry[2], digest)
        self.assertEqual(self.window.page.value(), 2)

    def test_decision_and_packet_restore_from_history(self):
        self.window.start_review()
        self.window.reviewer.setText("Revisor de teste")
        self.window.decision.setCurrentIndex(self.window.decision.findData("corrigir"))
        self.window.comment.setText("Solicitar evidências")
        self.window.save_tracking()
        identifier = self.window.review.id
        self.window.entries = []
        self.window.load_history()
        self.assertEqual(self.window.review.id, identifier)
        self.assertEqual(self.window.review.findings[0].decision, "corrigir")
        self.assertTrue(self.window.entries)

    def test_models_load_automatically_after_login(self):
        with patch.object(self.window.auth, "sign_in", return_value="Login validado"), patch("revisor.ai.models", return_value=[("slug", "Modelo")]):
            self.window.sign_in()
        self.assertTrue(self.window.ia_ready)
        self.assertTrue(self.window.use_ai.isChecked())
        self.assertIn("IA pronta", self.window.ai_state.text())

    def test_missing_plan_permission_does_not_show_ai_ready(self):
        with patch("revisor.ai.models", side_effect=AuthError("Uso do plano não autorizado")):
            self.window.load_models()
        self.assertFalse(self.window.ia_ready)
        self.assertFalse(self.window.use_ai.isChecked())
        self.assertIn("não autorizado", self.window.status.text())


if __name__ == "__main__":
    unittest.main()
