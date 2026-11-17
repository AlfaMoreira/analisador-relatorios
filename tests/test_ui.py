import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from revisor.__main__ import Window
import pymupdf


class ConsentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = Window(self.root)
        self.window.models.addItem("Modelo de teste", "test-model")
        self.window.question.setPlainText("Conferir o documento")
        self.window.attachments = [{"name": "selecionado.jpg", "page": 1, "sha256": "hash", "data": "private-image-data"}]

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    def test_refusing_consent_never_sends_or_logs(self):
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), patch("revisor.ai.analyze") as infer:
            self.window.analyze()
        infer.assert_not_called()
        self.assertFalse((self.root / "envios.jsonl").exists())

    def test_consent_sends_only_selected_sources_and_audits_without_image(self):
        def run(operation, done):
            done(operation())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), patch.object(self.window, "run_job", side_effect=run), patch("revisor.ai.analyze", return_value="Sugestão") as infer:
            self.window.analyze()
        self.assertEqual(len(infer.call_args.args[3]), 1)
        self.assertEqual(infer.call_args.args[3][0]["name"], "selecionado.jpg")
        log = (self.root / "envios.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("private-image-data", log)
        self.assertEqual([json.loads(line)["status"] for line in log.splitlines()], ["autorizado", "concluido"])
        self.assertIn("NÃO CONFIRMADOS", self.window.result.toPlainText())


class ReviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_local_review_decision_history_and_association(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / "relatorio.pdf"
            doc = pymupdf.open()
            doc.new_page().insert_text((40, 40), "Relatorio de Hidrogenio. " * 8 + "\nAnexo 1 - Relatorio de Ensaio\nAprovado por:")
            doc.save(source)
            doc.close()
            window = Window(root / "app")
            panel = window.review_panel
            panel.report_path = str(source)
            panel.evidence_paths = [str(source)]
            with patch.object(window, "run_job", side_effect=lambda operation, done: done(operation())):
                panel.run_review()
            self.assertIsNotNone(panel.review)
            panel.reviewer.setText("Revisor de teste")
            panel.decision.setCurrentIndex(panel.decision.findData("corrigir"))
            panel.comment.setText("Anexar evidência adequada")
            panel.save_decision()
            panel.link_evidence()
            saved = panel.store.load(panel.store.list()[0])
            self.assertEqual(saved.findings[0].decision, "corrigir")
            self.assertTrue(saved.evidence_links)
            panel.load_selected()
            self.assertEqual(panel.review.id, saved.id)
            window.close()


if __name__ == "__main__":
    unittest.main()
