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

    def test_client_profile_skill_and_model_are_preserved_in_review_and_consent(self):
        from test_profiles import profile
        saved = self.window.profiles.save(profile())
        self.window.refresh_profiles(saved)
        self.window.reference_date.setText("2026-11-17")
        self.ready_ai()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as consent, patch("revisor.ai.review_packet", return_value=([], [])) as infer:
            self.window.start_review()
        sent_packet = infer.call_args.args[2]
        self.assertEqual(sent_packet["criteria_profile"]["profile_id"], saved)
        self.assertIn("Skill 1.0.0", consent.call_args.args[2])
        self.assertEqual(self.window.review.client_id, "cliente-a")
        self.assertEqual(self.window.review.ai_model, "test-model")
        self.assertEqual(self.window.review.review_context["skill"]["version"], "1.0.0")
        restored = self.window.store.load(self.window.store.list()[0])
        self.assertEqual(restored.review_context, self.window.review.review_context)

    def test_wrong_client_profile_blocks_before_consent_or_inference(self):
        from test_profiles import profile
        saved = self.window.profiles.save(profile())
        self.window.refresh_profiles(saved)
        self.window.client_id.setText("cliente-b")
        self.ready_ai()
        with patch.object(self.window, "show_error") as error, patch.object(QMessageBox, "question") as consent, patch("revisor.ai.review_packet") as infer:
            self.window.start_review()
        error.assert_called_once()
        consent.assert_not_called()
        infer.assert_not_called()

    def test_profile_import_requires_new_approval_and_legacy_history_is_preserved(self):
        from revisor.profile_ui import ProfileDialog
        from test_profiles import profile
        dialog = ProfileDialog(self.window.profiles, self.window, profile())
        self.assertFalse(dialog.approved.isChecked())
        self.window.start_review()
        old_id = self.window.review.id
        self.window.client_id.setText("cliente-a")
        self.window.contract.setText("escopo-1")
        self.window.start_review()
        self.assertEqual(self.window.history.count(), 1)
        self.assertEqual(len(self.window.store.list()), 2)
        self.assertTrue(any(self.window.store.load(p).id == old_id for p in self.window.store.list()))
        dialog.deleteLater()

    def test_page_and_zoom_values_remain_visible_without_internal_buttons(self):
        self.window.show()
        self.app.processEvents()
        for control in (self.window.page, self.window.zoom):
            self.assertGreater(control.lineEdit().width(), 30)
        self.window.zoom.stepUp()
        self.assertEqual(self.window.zoom.text(), "90%")
        self.assertGreater(self.window.zoom.lineEdit().width(), 30)

    def test_selected_reference_is_yellow_in_viewer_and_original_is_preserved(self):
        import base64
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import Qt
        from revisor.corpus import prepare, sha256
        annex = self.make_pdf("referencia.pdf", "Referencia contratual de teste", pages=2)
        self.window.add_paths([str(annex)])
        self.window.start_review()
        entry = next(e for e in self.window.entries if e[1] == "referencia.pdf")
        original_hash = sha256(annex)
        finding = Finding("reference", "IA-01", "alerta", "Referencia exige conferencia", 2,
            "A fonte citada precisa de conferencia", "Conferir fonte e edicao", origin="ia",
            document_sha256=entry[2], excerpt="Referencia contratual de teste")
        self.window.review.findings = [finding]
        self.window.show_review(self.window.review)
        self.assertEqual(self.window.active_entry[2], entry[2])
        self.assertEqual(self.window.page.value(), 2)
        self.assertIn("Amarelo", self.window.highlight_note.text())
        self.assertIn("PONTO: Referencia exige conferencia", self.window.details.toPlainText())
        clean = QPixmap()
        clean.loadFromData(base64.b64decode(prepare(entry, 2)["data"].split(",", 1)[1]))
        clean = clean.scaledToWidth(self.window.preview.pixmap().width(), Qt.TransformationMode.SmoothTransformation)
        self.assertNotEqual(clean.toImage(), self.window.preview.pixmap().toImage())
        self.window.zoom.setValue(120)
        self.assertIn("Amarelo", self.window.highlight_note.text())
        self.window.page.setValue(1)
        self.assertNotIn("Amarelo:", self.window.highlight_note.text())
        self.assertEqual(sha256(annex), original_hash)


if __name__ == "__main__":
    unittest.main()
