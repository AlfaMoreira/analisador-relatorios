from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

import pymupdf
from revisor.review import analyze_pages, compare, decimal_pt, review_pdf, ReviewStore
from revisor.export import export_json, export_pdf


def document(family="Hidrogênio", result="≥ 99,999%\n99,999%", extra=""):
    return [f"Relatório de qualificação de {family}\n" + "Objetivo e descrição do ensaio. " * 5,
            f"7. RESULTADO OBTIDO\nPureza de Hidrogênio\n{result}\n{extra}",
            "Conclusão\nAnexo 1 - Relatório de Ensaio\nAnexo 2 - Certificados de Calibração\nAprovado por:\n"]


class ReviewTests(unittest.TestCase):
    def test_inclusive_and_strict_comparators(self):
        self.assertTrue(compare(Decimal("99.999"), "≥", Decimal("99.999")))
        self.assertFalse(compare(Decimal("99.999"), ">", Decimal("99.999")))
        self.assertTrue(compare(Decimal("0.01"), "≤", Decimal("0.01")))
        self.assertFalse(compare(Decimal("0.01"), "<", Decimal("0.01")))
        self.assertEqual(decimal_pt("6.694.026,25"), Decimal("6694026.25"))

    def test_hydrogen_at_limit_is_alert_not_failed_comparison(self):
        review = analyze_pages(document())
        self.assertEqual(review.family, "hidrogenio")
        self.assertEqual(review.checks[0]["numeric_comparison"], "atende")
        self.assertIn("LIM-01", {f.rule for f in review.findings})
        self.assertNotIn("CRT-01", {f.rule for f in review.findings})

    def test_below_limit_is_blocking(self):
        review = analyze_pages(document(result="≥ 99,999%\n99,998%"))
        self.assertTrue(any(f.rule == "CRT-01" and f.severity == "bloqueante" for f in review.findings))

    def test_strict_equality_fails(self):
        review = analyze_pages(document(result="> 99,999%\n99,999%"))
        self.assertTrue(any(f.rule == "CRT-01" for f in review.findings))
        self.assertFalse(any(f.rule == "LIM-01" for f in review.findings))

    def test_genuine_informative_results_not_rejected(self):
        pages = document("Ar Comprimido Respirável", extra="Critérios Informativo\nOxigênio\nInformativo\n20,7 %")
        review = analyze_pages(pages)
        self.assertTrue(any(c.get("mode") == "informativo" for c in review.checks))
        self.assertFalse(any(f.rule == "UNI-01" for f in review.findings))

    def test_oxygen_ppm_requires_confirmation_without_auto_conversion(self):
        pages = document("Ar Comprimido Respirável", extra="Oxigênio\nInformativo\n20,7 ppm")
        review = analyze_pages(pages)
        finding = next(f for f in review.findings if f.rule == "UNI-01")
        self.assertIn("20,7 ppm", finding.evidence)
        self.assertIn("Não substituir", finding.expected)

    def test_bibliographic_year_and_scope_conflict(self):
        pages = document("Ar Ambiente", extra="Farmacopeia Brasileira, 8ª edição – 2024\nSistema de Distribuição de Ar Comprimido")
        rules = {f.rule for f in analyze_pages(pages).findings}
        self.assertTrue({"NRM-04", "TXT-02"}.issubset(rules))
        pages[1] = pages[1].replace("2024", "2026")
        self.assertNotIn("NRM-04", {f.rule for f in analyze_pages(pages).findings})

    def test_evidence_present_still_needs_association(self):
        review = analyze_pages(document(), evidence_files=[{"name": "laudo.pdf", "sha256": "test"}])
        finding = next(f for f in review.findings if f.rule == "EVD-03")
        self.assertEqual(finding.severity, "alerta")
        self.assertIn("associados", finding.expected)

    def test_draft_approval_is_informative(self):
        review = analyze_pages(document(), stage="rascunho")
        self.assertEqual(next(f for f in review.findings if f.rule == "ED-03").severity, "informativo")

    def test_scan_does_not_claim_to_have_read_values(self):
        review = analyze_pages([""])
        self.assertEqual([f.rule for f in review.findings], ["EXT-01"])
        self.assertEqual(review.checks, [])

    def test_pagination_missing_page(self):
        pages = document()
        pages[0] += "\nPágina 1 de 4"
        self.assertIn("EVD-04", {f.rule for f in analyze_pages(pages).findings})

    def test_unparsed_table_is_not_guessed(self):
        pages = document(result="valor ilegível")
        review = analyze_pages(pages)
        self.assertIn("EXT-03", {f.rule for f in review.findings})
        self.assertFalse(any(c.get("quantity") == "pureza_hidrogenio" for c in review.checks))

    def test_table_of_contents_is_not_mistaken_for_results(self):
        pages = document()
        pages.insert(1, "SUMÁRIO\n7. RESULTADOS OBTIDOS ........ 3\n8. CONCLUSÃO ........ 4")
        self.assertFalse(any(f.rule == "EXT-03" for f in analyze_pages(pages).findings))

    def test_malformed_number_generates_finding_instead_of_crashing(self):
        review = analyze_pages(document(result="≥ 99,,999%\n99,999%"))
        self.assertIn("CRT-03", {f.rule for f in review.findings})
        self.assertFalse(any(c.get("quantity") for c in review.checks))

    def test_expired_calibration_based_on_declared_dates(self):
        pages = document(extra="Especificação dos Pontos\nData de Amostragem\n12/09/2026")
        pages.append("Validade da calibração\nAAA-001\nInstrumento\n123456\nCERT-001\n08/2026")
        review = analyze_pages(pages)
        self.assertTrue(any(f.rule == "INS-02" for f in review.findings))
        self.assertFalse(next(c for c in review.checks if c["rule"] == "INS-02")["certificate_verified"])

    def test_store_decisions_requires_human_and_justification(self):
        review = analyze_pages(document())
        finding = review.findings[0]
        with self.assertRaises(ValueError):
            review.decide(finding.id, "aceito", "", "Pessoa")
        with self.assertRaises(ValueError):
            review.decide(finding.id, "aceito", "Confirmado", "")
        review.decide(finding.id, "corrigir", "Solicitar laudo", "Revisor de teste")
        with tempfile.TemporaryDirectory() as root:
            store = ReviewStore(root)
            path = store.save(review)
            loaded = store.load(path)
            self.assertEqual(loaded.findings[0].decision, "corrigir")
            self.assertEqual(loaded.audit[-1]["reviewer"], "Revisor de teste")

    def test_pdf_and_json_include_findings_without_raw_instructions(self):
        review = analyze_pages(document())
        review.findings[0].comment = "<script>texto como dado</script> & revisão"
        with tempfile.TemporaryDirectory() as root:
            pdf = export_pdf(review, Path(root) / "parecer.pdf")
            js = export_json(review, Path(root) / "parecer.json")
            with pymupdf.open(pdf) as doc:
                text = "\n".join(p.get_text() for p in doc)
                self.assertIn("Parecer", text)
                self.assertIn("LIM-01", text)
                self.assertIn("NÃO AUTORIZA", text)
                self.assertIn("texto como dado", text)
            self.assertIn("rules_version", js.read_text(encoding="utf-8"))

    def test_exports_cannot_overwrite_or_hide_changes_to_original(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / "original.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((40, 40), "Relatorio de Hidrogenio " * 8)
            doc.save(source)
            doc.close()
            review = review_pdf(source)
            for exporter in (export_json, export_pdf):
                with self.assertRaises(ValueError):
                    exporter(review, source)
            source.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                export_json(review, root / "parecer.json")


if __name__ == "__main__":
    unittest.main()
