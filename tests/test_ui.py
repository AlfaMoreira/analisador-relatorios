import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from revisor.__main__ import Window


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


if __name__ == "__main__":
    unittest.main()
