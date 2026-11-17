"""Revisão documental local. Regras explícitas, sem decisões técnicas por IA."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import uuid

import pymupdf
from .corpus import sha256

RULES_VERSION = "0.3.0-piloto"
DECISIONS = {"pendente", "aceito", "corrigir", "falso_positivo"}
REFERENCES = [
    {"id": "FB-EDICOES", "title": "Anvisa: Farmacopeia Brasileira e edições anteriores",
     "urls": ["https://www.gov.br/anvisa/pt-br/assuntos/farmacopeia/farmacopeia-brasileira",
              "https://www.gov.br/anvisa/pt-br/assuntos/farmacopeia/farmacopeia-brasileira/edicoes-anteriores"],
     "checked_at": "2026-11-16", "scope": "Metadados: 7ª edição/2024 e 8ª edição/2026. Não valida método nem aplicabilidade."},
    {"id": "ISO-8573-2", "title": "ISO 8573-2:2018",
     "urls": ["https://www.iso.org/standard/66999.html"], "checked_at": "2026-11-16",
     "scope": "Catálogo público: óleo líquido/aerossol. Não cobre vapor nem comprova execução do ensaio."},
]


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")


def decimal_pt(value):
    value = value.strip().replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    return Decimal(value)


def compare(value, operator, limit):
    operators = {">=": lambda: value >= limit, "≥": lambda: value >= limit,
                 "<=": lambda: value <= limit, "≤": lambda: value <= limit,
                 ">": lambda: value > limit, "<": lambda: value < limit,
                 "=": lambda: value == limit}
    if operator not in operators:
        raise ValueError("Comparador não reconhecido.")
    return operators[operator]()


@dataclass
class Finding:
    id: str
    rule: str
    severity: str
    title: str
    page: int
    evidence: str
    expected: str
    decision: str = "pendente"
    comment: str = ""
    origin: str = "local"
    document_sha256: str = ""
    tracked: bool = False


@dataclass
class Review:
    id: str
    created_at: str
    source: dict
    family: str
    page_count: int
    findings: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    evidence_files: list = field(default_factory=list)
    evidence_links: dict = field(default_factory=dict)
    reviewer: str = ""
    stage: str = "antes_da_emissao"
    rules_version: str = RULES_VERSION
    references: list = field(default_factory=lambda: REFERENCES)
    limitations: list = field(default_factory=lambda: [
        "Piloto para hidrogênio, ar comprimido respirável e ar ambiente; outras famílias não validadas.",
        "Texto extraído localmente; imagens, assinaturas e marcações gráficas não são decididas pelo parser.",
        "Laudos e certificados anexados exigem associação e conferência humana; presença não comprova validade.",
        "Não verifica integralmente normas, contratos, incerteza ou segurança do sistema. Não libera emissão.",
    ])
    audit: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    ai_status: str = "nao_utilizada"
    ai_model: str = ""
    comparison: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data["findings"] = [Finding(**item) for item in data["findings"]]
        return cls(**data)

    def decide(self, finding_id, decision, comment, reviewer):
        if decision not in DECISIONS or not reviewer.strip():
            raise ValueError("Informe revisor e uma decisão válida.")
        if decision != "pendente" and not comment.strip():
            raise ValueError("Registre a justificativa da decisão.")
        finding = next((f for f in self.findings if f.id == finding_id), None)
        if finding is None:
            raise ValueError("Achado não encontrado.")
        self.audit.append({"at": datetime.now(timezone.utc).isoformat(), "reviewer": reviewer.strip(),
                           "finding": finding_id, "before": finding.decision, "after": decision,
                           "comment": comment.strip()})
        finding.decision, finding.comment = decision, comment.strip()
        self.reviewer = reviewer.strip()


def analyze_pages(pages, source=None, evidence_files=None, stage="antes_da_emissao"):
    if stage not in {"antes_da_emissao", "rascunho"}:
        raise ValueError("Etapa documental inválida.")
    source = dict(source or {"name": "relatorio.pdf", "sha256": "sintetico"})
    report_number = re.search(r"\bCCR-[A-Z]{3}\d{2}-\d+\b", "\n".join(pages), re.I)
    if report_number:
        source["report_number"] = report_number[0].upper()
    texts = [normalized(t) for t in pages]
    joined = "\n".join(texts)
    header = texts[0] if texts else ""
    family = ("ar_comprimido_respiravel" if "ar comprimido respiravel" in header else
              "hidrogenio" if "hidrogenio" in header else "ar_ambiente" if "ar ambiente" in header else "desconhecida")
    review = Review(str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(), source, family,
                    len(pages), evidence_files=evidence_files or [], stage=stage)

    def add(rule, severity, title, page, evidence, expected):
        key = f"{source.get('sha256')}|{rule}|{page}|{title}"
        review.findings.append(Finding(hashlib.sha256(key.encode()).hexdigest()[:16], rule,
                                       severity, title, page, evidence.strip()[:1500], expected))

    if not pages or sum(len(t.strip()) for t in pages) < 100:
        add("EXT-01", "alerta", "PDF sem texto suficiente para revisão local", 1, "Texto insuficiente.",
            "Usar leitura manual ou IA opcional; confirmar os valores lidos de imagens.")
        return review
    if family == "desconhecida":
        add("EXT-02", "alerta", "Família não reconhecida pelo piloto", 1, pages[0][:300],
            "Revisão manual; nenhuma validação técnica desta família é declarada.")

    for index, (text, original) in enumerate(zip(texts, pages), 1):
        page_match = re.search(r"pagina\s+(\d+)\s+de\s+(\d+)", text)
        if page_match and (int(page_match[1]) != index or int(page_match[2]) != len(pages)):
            add("EVD-04", "bloqueante", "Paginação diverge do PDF recebido", index, page_match[0],
                "Conferir sequência e total das páginas; um anexo externo pode ter paginação independente.")
        if "farmacopeia brasileira" in text and re.search(r"8\s*[ªa°º]?\s*edi[cç][aã]o\s*[-–—]?\s*2024", text):
            add("NRM-04", "alerta", "Edição e ano da Farmacopeia incompatíveis", index,
                "Farmacopeia Brasileira, 8ª edição - 2024", "Conferir a referência usada: 7ª/2024, 8ª/2026 (Anvisa). Não trocar o método automaticamente.")
        if family == "ar_ambiente" and "sistema de distribuicao de ar comprimido" in text:
            add("TXT-02", "alerta", "Objeto do relatório inconsistente", index,
                "Cabeçalho: ar ambiente. Objetivo: sistema de distribuição de ar comprimido.",
                "Definir o objeto e confirmar o procedimento e a referência aplicáveis antes de aplicar limites.")
        if family == "ar_ambiente" and "bloquear o fluxo de ar do gas" in text:
            add("TXT-01", "alerta", "Procedimento de gás em relatório de ar ambiente", index,
                "Procedimento menciona bloquear o fluxo e conectar mangueira à saída de gás.",
                "Conferir se a coleta foi de ambiente ou de gás canalizado e adequar o documento.")
        if "9." in text and "monoxido de carbono" in text and "proposta:" in text:
            proposal = text.split("proposta:", 1)[1].split("procedimento:", 1)[0]
            if "contagem de particulas viaveis" in proposal:
                add("TXT-01", "alerta", "Objetivo de microbiologia na seção de gases", index,
                    proposal, "Descrever o objetivo de CO, CO2 e oxigênio na seção correspondente.")
        if family == "hidrogenio" and index > 2 and "sala limpa" in text and "definicoes" in text:
            add("TXT-01", "informativo", "Glossário possivelmente herdado de outro modelo", index,
                "Definições de sala limpa e partículas em relatório de hidrogênio.", "Conferir pertinência das definições ao escopo.")
        if "responsabilidade" in text and "neste protocolo" in text:
            add("TXT-03", "informativo", "Documento chamado de protocolo", index,
                "Referência a protocolo dentro do relatório.", "Adequar a nomenclatura sem inferir erro do ensaio.")

        # Captura unidades do valor, preservando sinal de censura e sem converter resultados.
        oxygen_values = list(re.finditer(r"oxigenio\s+(?:informativo\s+)?([<>≤≥]?\s*[\d.,]+)\s*(ppm|%)(?=\s|$)", text))
        suspicious = [m[0] for m in oxygen_values if m[2] == "ppm"]
        if family == "ar_comprimido_respiravel" and suspicious:
            add("UNI-01", "bloqueante", "Oxigênio com unidade/valor a confirmar", index, " | ".join(suspicious),
                "Conferir unidade e valor no laudo original. Não substituir ppm por % nem declarar segurança para respiração.")
        pattern = r"pureza de hidrogenio\s*([≥≤<>]=?|=)\s*([\d.,]+)\s*%\s*([\d.,]+)\s*%"
        for match in re.finditer(pattern, text):
            try:
                limit, value = decimal_pt(match[2]), decimal_pt(match[3])
            except InvalidOperation:
                add("CRT-03", "alerta", "Valor ou critério numérico malformado", index, match[0],
                    "Conferir a escrita e a extração do valor; nenhuma comparação foi executada.")
                continue
            passes = compare(value, match[1], limit)
            review.checks.append({"rule": "CRT-01", "page": index, "quantity": "pureza_hidrogenio",
                                  "operator": match[1], "limit": str(limit), "value": str(value), "unit": "%",
                                  "numeric_comparison": "atende" if passes else "nao_atende",
                                  "origin": "texto_pdf", "does_not_release_report": True})
            if not passes:
                add("CRT-01", "bloqueante", "Valor fora do critério escrito", index, match[0],
                    "Revisar a divergência entre resultado e critério do relatório.")
            elif value == limit:
                add("LIM-01", "alerta", "Resultado exatamente no limite", index, match[0],
                    "Comparação numérica atende ao limite inclusivo; conferir regra de decisão e evidência sem reprovar pela igualdade.")
        if "sumario" not in text and ("resultados obtidos" in text or "resultado obtido" in text):
            if "informativo" in text:
                review.checks.append({"rule": "CRT-04", "page": index, "mode": "informativo",
                                      "expected": "Não aprovar/reprovar numericamente sem critério acordado."})
                add("CRT-04", "informativo", "Resultados declarados como informativos", index,
                    "Tabela com critérios Informativo.", "Preservar o caráter informativo. Confirmar limites somente se a finalidade contratada exigir qualificação.")
            elif family == "hidrogenio" and not any(c.get("quantity") == "pureza_hidrogenio" for c in review.checks):
                add("EXT-03", "alerta", "Tabela de pureza não interpretada", index, original,
                    "Conferir manualmente comparador, valor e unidade; não adivinhar.")
        if "10 minutos" in text and re.search(r"100\s*lpm", text):
            review.checks.append({"rule": "CAL-01", "page": index, "formula": "10 min × 100 L/min = 1000 L = 1 m³",
                                  "result": "coerente_no_procedimento", "actual_collection_verified": False})

    # Uma referência a anexos nunca comprova a presença ou identidade desses anexos.
    annex_page = next((i for i, t in enumerate(texts, 1) if "anexo 1" in t and "relatorio de ensaio" in t), None)
    if annex_page:
        possibly_included = bool(evidence_files) or len(pages) > annex_page
        add("EVD-03", "alerta" if possibly_included else "bloqueante", "Anexos citados exigem conferência", annex_page,
            "Cita relatório de ensaio e certificados de calibração.",
            "Não localizados no pacote recebido; conferir e adicionar as evidências faltantes." if not possibly_included else
            "Há arquivos adicionais ou páginas após a lista de anexos. Conferir se contêm os laudos e certificados citados; não presumir ausência.")
    sample_dates = []
    for text in texts:
        if "especificacao" in text and "data de amostragem" in text:
            for date in re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", text):
                try:
                    sample_dates.append(datetime.strptime(date, "%d/%m/%Y"))
                except ValueError:
                    pass
    for page_no, text in enumerate(texts, 1):
        if "validade da" not in text or "calibracao" not in text:
            continue
        for instrument in re.finditer(r"\b([a-z]{2,5}-\d{3})\s+(.{1,220}?)\b(\d{2})/(\d{4})\b", text, re.S):
            month, year = int(instrument[3]), int(instrument[4])
            if not 1 <= month <= 12:
                add("INS-02", "alerta", "Data de calibração não interpretada", page_no, instrument[0], "Conferir a data no certificado original.")
                continue
            expired = any((d.year, d.month) > (year, month) for d in sample_dates)
            review.checks.append({"rule": "INS-02", "page": page_no, "instrument": instrument[1].upper(),
                                  "declared_expiry": f"{month:02}/{year}", "certificate_verified": False,
                                  "expired_by_declared_month": expired if sample_dates else None})
            if expired:
                add("INS-02", "bloqueante", "Calibração declarada anterior à coleta", page_no, instrument[0],
                    "Conferir certificado e rastreabilidade na data da amostragem; não aceitar apenas a data declarada.")
    approval_page = next((i for i in range(len(texts), 0, -1) if "aprovado por:" in texts[i - 1]), None)
    if approval_page:
        after = texts[approval_page - 1].split("aprovado por:")[-1]
        meaningful = re.sub(r"data:|nome/cargo|pagina\s+\d+\s+de\s+\d+|[\W\d_]", "", after)
        if not meaningful:
            add("ED-03", "alerta" if stage == "antes_da_emissao" else "informativo",
                "Campo de aprovação sem texto preenchido", approval_page, "Aprovado por: sem nome extraído.",
                "Verificar visualmente assinatura/marca gráfica e etapa documental; um campo vazio em rascunho não reprova o ensaio.")
    if family in {"ar_comprimido_respiravel", "ar_ambiente"}:
        add("REV-01", "informativo", "Confirmar marcação gráfica da conclusão", len(pages),
            "Checkboxes e marcas gráficas não são decididos pelo extrator de texto.",
            "O revisor deve conferir Cumpre/Não cumpre/Informativo na imagem. Critérios informativos não autorizam liberação.")
    review.audit.append({"at": review.created_at, "event": "revisao_local_criada", "rules_version": RULES_VERSION})
    return review


def review_pdf(path, evidence_paths=(), stage="antes_da_emissao"):
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("A revisão local recebe um relatório PDF.")
    before = sha256(path)
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("O PDF está protegido por senha.")
        if len(doc) > 500:
            raise ValueError("O piloto aceita até 500 páginas por relatório.")
        pages = [page.get_text() for page in doc]
    evidence = [{"name": Path(p).name, "sha256": sha256(p), "path": str(Path(p).resolve())} for p in evidence_paths]
    if sha256(path) != before:
        raise ValueError("O relatório mudou durante a leitura.")
    return analyze_pages(pages, {"name": path.name, "sha256": before, "path": str(path.resolve())}, evidence, stage)


class ReviewStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, review):
        target = self.root / (review.id + ".json")
        if not re.fullmatch(r"[a-f0-9-]{36}", review.id):
            raise ValueError("Identificador de revisão inválido.")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(review.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        return target

    def list(self):
        return sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    def load(self, path):
        path = Path(path).resolve()
        if path.parent != self.root.resolve():
            raise ValueError("Revisão fora da biblioteca local.")
        return Review.from_dict(json.loads(path.read_text(encoding="utf-8")))


def compare_reviews(previous, current):
    """Ausência de redetecção não equivale a correção confirmada."""
    def identity(review):
        value = review.source.get("report_number")
        if value:
            return value
        match = re.search(r"CCR-[A-Z]{3}\d{2}-\d+", review.source["name"], re.I)
        return match[0].upper() if match else None
    old_id, new_id = identity(previous), identity(current)
    if previous.id == current.id:
        raise ValueError("Selecione uma revisão anterior diferente da atual.")
    if previous.family != current.family or (old_id and new_id and old_id != new_id):
        raise ValueError("Os documentos parecem pertencer a relatórios diferentes. Selecione versões do mesmo relatório.")
    tracked = [f for f in previous.findings if f.tracked]
    if not tracked:
        raise ValueError("Marque os pontos pertinentes na revisão anterior antes de comparar.")
    available = list(current.findings)
    rows = []
    for old in tracked:
        match = next((f for f in available if f.origin == old.origin and f.rule == old.rule and normalized(f.title) == normalized(old.title)), None)
        if match:
            available.remove(match)
        rows.append({"state": "persiste" if match else "nao_redetectado", "title": old.title, "rule": old.rule,
                     "origin": old.origin, "previous_page": old.page, "current_page": match.page if match else None,
                     "previous_finding": old.id, "current_finding": match.id if match else None})
    rows.extend({"state": "novo", "title": f.title, "rule": f.rule, "origin": f.origin,
                 "previous_page": None, "current_page": f.page, "previous_finding": None, "current_finding": f.id}
                for f in available)
    return {"previous_review": previous.id, "current_review": current.id, "items": rows,
            "identity_confirmed": bool(old_id and new_id),
            "note": "Comparação de apontamentos por regra e título. Não redetectado exige confirmação humana; não significa correção comprovada. Sugestões da IA podem variar entre rodadas."}
