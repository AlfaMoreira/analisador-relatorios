"""Cópia do conjunto com destaques e comentários; originais preservados."""
import base64
from pathlib import Path
import re
import tempfile
import pymupdf
from .corpus import prepare
from .export import protect_originals, export_pdf


def export_annotated(review, path):
    path = Path(path)
    protect_originals(review, path)
    sources = review.documents or [review.source, *review.evidence_files]
    merged = pymupdf.open()
    positions = {}
    try:
        for source in sources:
            start = len(merged)
            filename = source["path"]
            if Path(filename).suffix.lower() == ".pdf":
                with pymupdf.open(filename) as original:
                    merged.insert_pdf(original)
            else:
                image = prepare((0, source["name"], source["sha256"], filename))["data"]
                with pymupdf.open(stream=base64.b64decode(image.split(",", 1)[1]), filetype="jpeg") as original:
                    data = original.convert_to_pdf()
                with pymupdf.open(stream=data, filetype="pdf") as converted:
                    merged.insert_pdf(converted)
            positions[source["sha256"]] = (start, len(merged) - start, source["name"])
        counters = {}
        for finding in review.findings:
            digest = finding.document_sha256 or review.source["sha256"]
            if digest not in positions:
                raise ValueError("Um apontamento não está ligado a documento disponível.")
            offset, count, name = positions[digest]
            if not 1 <= finding.page <= count:
                raise ValueError("Um apontamento indica página inexistente.")
            page_index = offset + finding.page - 1
            page = merged[page_index]
            content = (f"{finding.rule} | {finding.title}\nArquivo: {name}, página {finding.page}\n"
                       f"Origem: {'IA, leitura não confirmada' if finding.origin == 'ia' else 'regra local'}\n"
                       f"Evidência: {finding.evidence}\nConferir: {finding.expected}\n"
                       f"Decisão: {finding.decision}\nRevisor: {review.reviewer or 'não informado'}\n"
                       f"Anotação: {finding.comment or 'pendente'}")
            exact = finding.evidence.removeprefix("Sugestão de IA não confirmada: ").strip()
            quads = page.search_for(exact, quads=True) if len(exact) < 600 else []
            # Só destaca localizações encontradas; nunca inventa um recorte da página.
            if not quads:
                candidates = re.findall(r"[<>≤≥]?\s*\d[\d.,]*\s*(?:%|ppm|mg/m³|UFC/m³)", exact, re.I)
                for candidate in candidates:
                    quads.extend(page.search_for(candidate.strip(), quads=True))
            if quads:
                annotation = page.add_highlight_annot(quads)
                annotation.set_colors(stroke=(1, 0.86, 0.15))
            else:
                index = counters.get(page_index, 0)
                counters[page_index] = index + 1
                y = min(page.rect.height - 30, 40 + index * 23)
                annotation = page.add_text_annot((page.rect.width - 23, y), content, icon="Comment")
            annotation.set_info(title="Celacanto · Apontamento", content=content)
            annotation.update()
        # A lista final torna todos os pontos legíveis mesmo em leitores que
        # não abrem as caixas de comentário automaticamente.
        with tempfile.TemporaryDirectory() as temporary:
            summary = export_pdf(review, Path(temporary) / "apontamentos.pdf")
            with pymupdf.open(summary) as summary_pdf:
                merged.insert_pdf(summary_pdf)
        merged.set_metadata({"title": "Cópia comentada para revisão - " + review.source["name"],
                             "author": review.reviewer or "Celacanto", "subject": "Apontamentos; não representa aprovação técnica"})
        merged.save(path, garbage=3, deflate=True)
    finally:
        merged.close()
    return path
