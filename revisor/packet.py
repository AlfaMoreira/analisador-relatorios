"""Um único conjunto de documentos para revisão local e IA opcional."""
from pathlib import Path
import base64
import threading
import pymupdf
from .corpus import prepare, sha256
from .review import review_pdf


def build_packet(entries, progress=lambda _message: None, cancel=None):
    if not entries:
        raise ValueError("Adicione o relatório e os anexos disponíveis.")
    cancel = cancel or threading.Event()
    documents, pages = [], []
    for entry in entries:
        if cancel.is_set():
            raise ValueError("Leitura cancelada.")
        _id, name, digest, path = entry
        if sha256(path) != digest:
            raise ValueError("Um documento mudou desde a importação. Adicione-o novamente.")
        document = dict(id=f"D{len(documents)+1}", name=name, sha256=digest, path=path,
                        kind="pdf" if Path(path).suffix.lower() == ".pdf" else "imagem")
        progress(f"Lendo {name}…")
        if document["kind"] == "pdf":
            with pymupdf.open(path) as pdf:
                if pdf.needs_pass:
                    raise ValueError(f"O documento {name} exige senha.")
                document["pages"] = len(pdf)
                if len(pdf) > 500 or len(pages) + len(pdf) > 600:
                    raise ValueError("Este piloto aceita até 500 páginas por PDF e 600 páginas no conjunto.")
                for number, page in enumerate(pdf, 1):
                    if cancel.is_set():
                        raise ValueError("Leitura cancelada.")
                    text = page.get_text()
                    if len(text) > 60000:
                        raise ValueError(f"A página {number} de {name} excede o tamanho suportado. Nenhuma parte será omitida silenciosamente.")
                    item = dict(document=document["id"], name=name, sha256=digest, page=number, text=text)
                    # Uma página com texto também pode conter tabelas e fitas em imagem.
                    scale = min(1.25, 2400 / max(page.rect.width, page.rect.height))
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    item["image"] = "data:image/jpeg;base64," + base64.b64encode(pixmap.tobytes("jpg")).decode()
                    pages.append(item)
        else:
            document["pages"] = 1
            pages.append(dict(document=document["id"], name=name, sha256=digest, page=1,
                              text="", image=prepare(entry)["data"]))
        documents.append(document)
    if not any(d["kind"] == "pdf" for d in documents):
        raise ValueError("Adicione pelo menos um relatório PDF. As fotos entram como anexos.")
    return dict(documents=documents, pages=pages)


def batches(packet):
    result, current, chars, images = [], [], 0, 0
    for page in packet["pages"]:
        count = len(page["text"])
        image = int("image" in page)
        if current and (len(current) >= 12 or chars + count > 60000 or images + image > 4):
            result.append(current)
            current, chars, images = [], 0, 0
        current.append(page)
        chars += count
        images += image
    if current:
        result.append(current)
    return result


def local_review(packet, stage="antes_da_emissao"):
    principal = next(d for d in packet["documents"] if d["kind"] == "pdf")
    others = [d["path"] for d in packet["documents"] if d is not principal]
    review = review_pdf(principal["path"], others, stage)
    review.source["name"] = principal["name"]
    names = {d["sha256"]: d["name"] for d in packet["documents"]}
    for evidence in review.evidence_files:
        evidence["name"] = names.get(evidence["sha256"], evidence["name"])
    review.documents = packet["documents"]
    for finding in review.findings:
        finding.document_sha256 = principal["sha256"]
    return review
