import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
import pymupdf
from revisor.packet import build_packet, batches, local_review
from revisor.corpus import Corpus, sha256
from revisor.ai import review_packet
from revisor.auth import AuthError
from revisor.review import Finding, analyze_pages, compare_reviews
from revisor.learning import ExampleStore
from revisor.annotations import export_annotated


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.corpus = Corpus(self.root / "corpus")

    def tearDown(self):
        self.temp.cleanup()

    def add_pdf(self, name, count, text="Relatorio de Hidrogenio "):
        path = self.root / name
        doc = pymupdf.open()
        for page in range(count):
            doc.new_page().insert_text((40, 40), text * 8 + f"\nPagina {page+1}")
        doc.save(path)
        doc.close()
        digest = self.corpus.import_file(path)[0]
        return next(e for e in self.corpus.entries() if e[2] == digest)

    def test_every_page_has_text_and_visual_representation_and_is_batched_once(self):
        entries = [self.add_pdf("principal.pdf", 5), self.add_pdf("anexo.pdf", 2)]
        packet = build_packet(entries)
        self.assertEqual(len(packet["pages"]), 7)
        self.assertTrue(all(p["image"].startswith("data:image/jpeg;base64,") for p in packet["pages"]))
        flattened = [p for chunk in batches(packet) for p in chunk]
        self.assertEqual([(p["document"], p["page"]) for p in flattened],
                         [(p["document"], p["page"]) for p in packet["pages"]])
        self.assertTrue(all(sum("image" in p for p in chunk) <= 4 for chunk in batches(packet)))

    def test_complete_pdf_with_pages_after_annex_reference_not_declared_missing(self):
        review = analyze_pages(["Relatorio de Hidrogenio " * 8,
            "Anexo 1 - Relatório de Ensaio\nAnexo 2 - Certificados de Calibração", "Certificado de calibração e laudo anexados"])
        finding = next(f for f in review.findings if f.rule == "EVD-03")
        self.assertEqual(finding.severity, "alerta")
        self.assertIn("não presumir ausência", finding.expected)

    def test_local_review_checks_annex_text_and_tracks_every_page_without_ai(self):
        packet = build_packet([self.add_pdf("principal.pdf", 2),
                               self.add_pdf("anexo.pdf", 1, "INSERIR RESULTADO ")])
        with patch("revisor.ai.analyze", side_effect=AssertionError("IA não deve ser chamada")):
            review = local_review(packet)
        coverage = [c for c in review.checks if c["rule"] == "COB-01"]
        self.assertEqual(len(coverage), 3)
        annex = packet["documents"][1]
        self.assertTrue(any(f.rule == "TXT-04" and f.document_sha256 == annex["sha256"]
                            and f.page == 1 for f in review.findings))
        self.assertEqual(review.ai_status, "nao_utilizada")

    def test_local_review_reports_unreadable_page_even_in_textual_document(self):
        entry = self.add_pdf("misto.pdf", 1)
        packet = build_packet([entry])
        packet["pages"].append(dict(packet["pages"][0], page=2, text=""))
        packet["documents"][0]["pages"] = 2
        review = local_review(packet)
        self.assertTrue(any(f.rule == "COB-02" and f.page == 2 for f in review.findings))
        self.assertEqual([c["status"] for c in review.checks if c["rule"] == "COB-01"],
                         ["texto_conferido", "requer_leitura_visual"])

    def test_ai_keeps_document_and_page_reference_and_downgrades_to_suggestion(self):
        packet = build_packet([self.add_pdf("relatorio.pdf", 1), self.add_pdf("laudo.pdf", 2)])
        response = json.dumps({"resumo": "Revisão de teste", "achados": [{"arquivo": "D2", "pagina": 2,
            "severidade": "bloqueante", "titulo": "Conferir medição", "evidencia": "Trecho de teste", "recomendacao": "Conferir laudo"}]})
        with patch("revisor.ai.analyze", return_value=response):
            findings, notes = review_packet(MagicMock(), "model", packet)
        self.assertEqual(findings[0].document_sha256, packet["documents"][1]["sha256"])
        self.assertEqual(findings[0].page, 2)
        self.assertEqual(findings[0].origin, "ia")
        self.assertEqual(findings[0].severity, "alerta")

    def test_ai_invented_page_is_rejected(self):
        packet = build_packet([self.add_pdf("relatorio.pdf", 1)])
        response = json.dumps({"achados": [{"arquivo": "D1", "pagina": 999, "titulo": "Inventado",
            "evidencia": "Texto", "recomendacao": "Texto"}]})
        with patch("revisor.ai.analyze", return_value=response):
            findings, notes = review_packet(MagicMock(), "model", packet)
        self.assertEqual(findings, [])
        self.assertTrue(notes)

    def test_malformed_ai_response_is_not_accepted(self):
        packet = build_packet([self.add_pdf("relatorio.pdf", 1)])
        with patch("revisor.ai.analyze", return_value="Resposta em formato incorreto"), self.assertRaises(AuthError):
            review_packet(MagicMock(), "model", packet)

    def test_cancelled_packet_does_not_read_or_send(self):
        cancel = threading.Event()
        cancel.set()
        entry = self.add_pdf("relatorio.pdf", 1)
        with self.assertRaises(ValueError):
            build_packet([entry], cancel=cancel)

    def test_annotations_preserve_original_and_cover_all_documents(self):
        first = self.add_pdf("relatorio.pdf", 1)
        second = self.add_pdf("anexo.pdf", 1, "Trecho localizavel de teste ")
        packet = build_packet([first, second])
        review = local_review(packet)
        review.findings = [Finding("highlight", "IA-01", "alerta", "Conferir dado", 1,
            "Trecho localizavel de teste", "Conferir", origin="ia", document_sha256=second[2])]
        before = sha256(first[3]), sha256(second[3])
        target = export_annotated(review, self.root / "comentado.pdf")
        with pymupdf.open(target) as document:
            self.assertGreater(len(document), 2)
            annotations = list(document[1].annots())
            self.assertTrue(annotations)
            self.assertIn("Conferir dado", annotations[0].info["content"])
        self.assertEqual(before, (sha256(first[3]), sha256(second[3])))
        with self.assertRaises(ValueError):
            export_annotated(review, first[3])

    def test_learning_only_accepts_confirmed_justified_examples(self):
        review = local_review(build_packet([self.add_pdf("relatorio.pdf", 1)]))
        review.findings.append(Finding("confirmed-test", "TXT-01", "alerta", "Conferir texto", 1, "Texto de teste", "Conferir a redação"))
        store = ExampleStore(self.root / "examples.sqlite3")
        with self.assertRaises(ValueError):
            store.contribute(review)
        finding = review.findings[0]
        review.decide(finding.id, "corrigir", "Confirmado no documento", "Revisor de teste")
        self.assertEqual(store.contribute(review), 1)
        store.contribute(review)
        self.assertEqual(len(store.examples(review.family)), 1)
        target = store.export(review, self.root / "contribuicoes.json")
        self.assertFalse(json.loads(target.read_text(encoding="utf-8"))["automatic_model_training"])

    def test_version_comparison_does_not_claim_correction(self):
        previous = analyze_pages(["Relatório de Hidrogênio " * 8, "Anexo 1 - Relatório de Ensaio"])
        current = analyze_pages(["Relatório de Hidrogênio " * 8])
        previous.findings[0].tracked = True
        comparison = compare_reviews(previous, current)
        self.assertEqual(comparison["items"][0]["state"], "nao_redetectado")
        self.assertIn("não significa correção comprovada", comparison["note"])


if __name__ == "__main__":
    unittest.main()
