import unittest
import pymupdf
from revisor.locate import locate_finding
from revisor.review import Finding


class LocateTests(unittest.TestCase):
    def setUp(self):
        self.document = pymupdf.open()
        self.page = self.document.new_page()
        self.page.insert_text((40, 60), "Anexo 1 - Relatorio de Ensaio\nResultado: 123 ppm\nReferencia contratual de teste")

    def tearDown(self):
        self.document.close()

    def test_explicit_excerpt_is_used_even_if_evidence_is_explanatory(self):
        finding = Finding("f", "EVD-03", "alerta", "Conferir anexo", 1, "Laudo citado exige conferencia", "Conferir", excerpt="Anexo 1")
        quads, _ = locate_finding(self.page, finding)
        self.assertEqual(len(quads), 1)
        self.assertLess(quads[0].rect.y0, 60)

    def test_explicit_quotation_can_locate_old_findings(self):
        finding = Finding("f", "AI-01", "alerta", "Conferir", 1, 'Conferir "Referencia contratual de teste" no documento.', "Conferir")
        self.assertEqual(len(locate_finding(self.page, finding)[0]), 1)

    def test_numbers_alone_do_not_anchor_an_explanatory_finding(self):
        finding = Finding("f", "AI-01", "alerta", "Conferir", 1, "A leitura de 123 ppm pode precisar de confirmacao.", "Conferir")
        self.assertEqual(locate_finding(self.page, finding)[0], [])

    def test_missing_excerpt_does_not_fabricate_coordinates(self):
        finding = Finding("f", "AI-01", "alerta", "Conferir", 1, "Ausente", "Conferir", excerpt="Conteudo que nao existe")
        self.assertEqual(locate_finding(self.page, finding)[0], [])
