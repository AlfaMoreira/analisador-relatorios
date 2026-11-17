"""Um único conjunto de documentos para revisão local e IA opcional."""
from pathlib import Path
import base64
import threading
import pymupdf
from .corpus import prepare, sha256
from .review import analyze_pages, Finding
import hashlib
import re


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
    evidence = [{"name": d["name"], "sha256": d["sha256"], "path": d["path"]}
                for d in packet["documents"] if d is not principal]
    def analyze(document):
        pages = [p["text"] for p in packet["pages"] if p["document"] == document["id"]]
        return analyze_pages(pages, {"name": document["name"], "sha256": document["sha256"],
                                    "path": document["path"]}, evidence, stage)
    review = analyze(principal)
    for check in review.checks:
        check["document_sha256"] = principal["sha256"]
    review.source["name"] = principal["name"]
    names = {d["sha256"]: d["name"] for d in packet["documents"]}
    for evidence in review.evidence_files:
        evidence["name"] = names.get(evidence["sha256"], evidence["name"])
    review.documents = packet["documents"]
    for finding in review.findings:
        finding.document_sha256 = principal["sha256"]
    # Todos os documentos são objetos de revisão, inclusive os anexos.
    for document in packet["documents"]:
        if document is not principal and document["kind"] == "pdf":
            annex = analyze(document)
            # Escopo e aprovação do relatório principal não são impostos a certificados.
            for finding in annex.findings:
                if finding.rule not in {"EXT-02", "ED-03", "REV-01", "EVD-03"}:
                    finding.document_sha256 = document["sha256"]
                    review.findings.append(finding)
            review.checks.extend(dict(c, document_sha256=document["sha256"]) for c in annex.checks)
        for page in (p for p in packet["pages"] if p["document"] == document["id"]):
            text = page["text"]
            readable = len(re.sub(r"\W", "", text)) >= 40
            review.checks.append({"rule": "COB-01", "page": page["page"],
                "document_sha256": document["sha256"], "document_name": document["name"],
                "status": "texto_conferido" if readable else "requer_leitura_visual",
                "scope": "Regras locais sobre texto extraído; imagens e correção técnica integral não verificadas."})
            issues = []
            if not readable:
                issues.append(("COB-02", "Página sem texto suficiente para conferência automática",
                    "Não foi possível conferir o conteúdo desta página por regras de texto.",
                    "Conferir visualmente a página; ausência de achados não significa conformidade."))
            for match in re.finditer(r"\b(?:TODO|TBD|XXX|PREENCHER|INSERIR\s+(?:NOME|DATA|RESULTADO|CRIT[EÉ]RIO))\b", text, re.I):
                issues.append(("TXT-04", "Possível campo de modelo não preenchido", match[0],
                    "Verificar o trecho e preencher se for um campo pendente; pode ser uma citação legítima."))
            for rule, title, evidence_text, expected in issues:
                key = hashlib.sha256(f"{document['sha256']}|{page['page']}|{rule}|{evidence_text}".encode()).hexdigest()[:16]
                if not any(f.id == key for f in review.findings):
                    review.findings.append(Finding(key, rule, "alerta", title, page["page"],
                        evidence_text, expected, document_sha256=document["sha256"]))
    return review
