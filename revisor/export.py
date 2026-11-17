"""Parecer de revisão: achados e decisões, sem aprovação do ensaio."""
from html import escape
import json
from pathlib import Path
import pymupdf
from .corpus import sha256


def check_text(check):
    if check["rule"] == "CRT-01":
        number = lambda value: str(value).replace(".", ",")
        return (f"Página {check['page']}: pureza de hidrogênio {number(check['value'])}{check['unit']}; "
                f"critério {check['operator']} {number(check['limit'])}{check['unit']}. "
                f"Comparação numérica: {check['numeric_comparison'].replace('_', ' ')}. Não libera o relatório.")
    if check["rule"] == "CAL-01":
        return f"Página {check['page']}: {check['formula']}. Coerente no procedimento; volume efetivamente coletado não conferido."
    if check["rule"] == "CRT-04":
        return f"Página {check['page']}: resultados informativos. Sem critério acordado, não há aprovação ou reprovação numérica."
    if check["rule"] == "INS-02":
        status = {True: "anterior à coleta", False: "não anterior ao mês da coleta", None: "sem data de coleta interpretada"}[check['expired_by_declared_month']]
        return (f"Página {check['page']}: instrumento {check['instrument']}, validade declarada {check['declared_expiry']} "
                f"({status}). Certificado original ainda não conferido.")
    return f"Página {check.get('page', '?')}: {check['rule']} - conferir os dados estruturados no JSON."


def protect_originals(review, target):
    target = Path(target).resolve()
    for source in [review.source, *review.evidence_files]:
        if not source.get("path"):
            continue
        original = Path(source["path"]).resolve()
        if target == original:
            raise ValueError("O parecer não pode sobrescrever um arquivo original.")
        if not original.is_file() or sha256(original) != source["sha256"]:
            raise ValueError("Um original está indisponível ou foi alterado desde a revisão. Reabra e confira os arquivos.")


def export_json(review, target):
    target = Path(target)
    protect_originals(review, target)
    target.write_text(json.dumps(review.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def export_pdf(review, target):
    target = Path(target)
    protect_originals(review, target)
    esc = lambda value: escape(str(value))
    parts = ["<h1>CELACANTO</h1><h2>Parecer de revisão documental</h2>",
             "<p class='notice'>PILOTO - NÃO AUTORIZA EMISSÃO OU USO DO SISTEMA</p>",
             f"<p><b>Relatório:</b> {esc(review.source['name'])}<br>"
             f"<b>Família:</b> {esc(review.family)} | <b>Páginas:</b> {review.page_count}<br>"
             f"<b>Revisor:</b> {esc(review.reviewer or 'não informado')}<br>"
             f"<b>Etapa:</b> {esc(review.stage)} | <b>Regras:</b> {esc(review.rules_version)}<br>"
             f"<b>IA:</b> {esc(review.ai_status)} | <b>Modelo:</b> {esc(review.ai_model or 'não utilizado')}<br>"
             f"<b>Criação UTC:</b> {esc(review.created_at)}</p>",
             "<p>Este parecer registra achados locais e decisões humanas. Não substitui laudos, certificados, "
             "avaliação normativa ou decisão de emissão. Valores de imagens não entram nas contas.</p>",
             f"<p><b>SHA-256 do original:</b><br>{esc(review.source['sha256'][:32])}<br>{esc(review.source['sha256'][32:])}</p>",
             "<h2>Achados e decisões</h2>"]
    for finding in review.findings:
        origin_name = next((d["name"] for d in review.documents if d["sha256"] == finding.document_sha256), review.source["name"])
        parts.append(f"<div class='finding'><h3>{esc(finding.rule)} | {esc(finding.severity)} | página {finding.page}</h3>"
                     f"<p><b>Origem:</b> {esc('IA - sugestão não confirmada' if finding.origin == 'ia' else 'Regra local')} | {esc(origin_name)}</p>"
                     f"<p><b>{esc(finding.title)}</b><br><b>Evidência:</b> {esc(finding.evidence)}<br>"
                     f"<b>Conferência esperada:</b> {esc(finding.expected)}<br>"
                     f"<b>Decisão:</b> {esc(finding.decision)}<br><b>Justificativa:</b> {esc(finding.comment or 'pendente')}</p></div>")
        parts.append(f"<p><b>Acompanhar na próxima versão:</b> {'sim' if finding.tracked else 'não marcado'}</p>")
    if not review.findings:
        parts.append("<p>Nenhum achado nas regras aplicadas. Isso não comprova conformidade.</p>")
    parts.append("<h2>Verificações locais</h2>")
    for check in review.checks:
        parts.append("<p>" + esc(check_text(check)) + "</p>")
    parts.append("<h2>Evidências fornecidas</h2>")
    if not review.evidence_files:
        parts.append("<p>Nenhum arquivo de evidência adicional selecionado nesta revisão.</p>")
    for evidence in review.evidence_files:
        digest = evidence["sha256"]
        parts.append(f"<p>{esc(evidence['name'])}<br>SHA-256: {esc(digest[:32])}<br>{esc(digest[32:])}</p>")
    parts.append("<h2>Associações declaradas pelo revisor</h2>")
    names = {e['sha256']: e['name'] for e in review.evidence_files}
    if not review.evidence_links:
        parts.append("<p>Nenhuma associação registrada.</p>")
    for finding in review.findings:
        for link in review.evidence_links.get(finding.id, []):
            parts.append(f"<p>{esc(finding.rule)}: {esc(names.get(link['sha256'], 'arquivo não identificado'))} "
                         f"({esc(link['role'])}), associado por {esc(link['reviewer'])}.</p>")
    if review.comparison:
        parts.append("<h2>Comparação com a revisão anterior</h2>")
        parts.append("<p>" + esc(review.comparison["note"]) + "</p>")
        labels = {"persiste": "Ainda detectado", "nao_redetectado": "Não redetectado - confirmar", "novo": "Novo apontamento"}
        for item in review.comparison["items"]:
            parts.append(f"<p><b>{esc(labels[item['state']])}:</b> {esc(item['title'])} "
                         f"(página anterior {esc(item['previous_page'] or '-')}; atual {esc(item['current_page'] or '-')}).</p>")
    parts.append("<h2>Referências e limites</h2>")
    for reference in review.references:
        parts.append(f"<p><b>{esc(reference['title'])}</b><br>{esc(reference['scope'])}<br>"
                     f"Consulta: {esc(reference['checked_at'])}</p>")
        for url in reference["urls"]:
            parts.append(f"<p><a href='{esc(url)}'>{esc(url)}</a></p>")
    for limitation in review.limitations:
        parts.append("<p>" + esc(limitation) + "</p>")
    parts.append("<h2>Trilha de revisão</h2>")
    for event in review.audit:
        if event.get("event") == "revisao_local_criada":
            message = f"{event['at'][:19]} UTC - Revisão local criada com regras {review.rules_version}."
        elif event.get("event") == "evidencia_associada":
            message = f"{event['at'][:19]} UTC - {event['reviewer']} associou evidência como {event['role']}."
        elif event.get("event") == "apontamento_atualizado":
            message = f"{event['at'][:19]} UTC - Apontamento {'marcado para acompanhamento' if event['tracked'] else 'desmarcado'}. {event.get('comment', '')}"
        elif event.get("event") == "nova_rodada":
            message = f"{event['at'][:19]} UTC - Nova rodada vinculada à revisão anterior. Decisões anteriores não foram transferidas automaticamente."
        else:
            message = (f"{event['at'][:19]} UTC - {event.get('reviewer', '')}: "
                       f"{event.get('before', '')} para {event.get('after', '')}. {event.get('comment', '')}")
        parts.append("<p>" + esc(message) + "</p>")
    story = pymupdf.Story(html="".join(parts), user_css="""
        body { font-family: sans-serif; font-size: 9.7pt; color: #243449; }
        h1 { color: #123c6d; font-size: 22pt; margin-bottom: 3pt; }
        h2 { color: #123c6d; font-size: 14pt; margin-top: 12pt; page-break-after: avoid; }
        h3 { font-size: 11pt; color: #00489c; margin-top: 7pt; margin-bottom: 3pt; }
        p { margin-top: 3pt; margin-bottom: 7pt; overflow-wrap: anywhere; }
        .notice { color: #a12d26; font-weight: bold; }
        .finding { border-bottom: 1px solid #cbd5e1; page-break-inside: avoid; }
    """)
    box = pymupdf.Rect(0, 0, 595, 842)
    writer = pymupdf.DocumentWriter(str(target))
    try:
        story.write(writer, lambda _number, _filled: (box, pymupdf.Rect(42, 42, 553, 792), None))
    finally:
        writer.close()
    with pymupdf.open(target) as document:
        for index, page in enumerate(document, 1):
            page.insert_text((42, 818), f"Revisao humana | Piloto | Pagina {index} de {len(document)}", fontsize=8, color=(0.2, 0.3, 0.4))
        document.saveIncr()
    return target
