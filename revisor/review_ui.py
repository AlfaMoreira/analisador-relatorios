"""Tela de revisão, decisões e pareceres locais."""
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QLineEdit, QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QMessageBox)
from .review import ReviewStore, review_pdf
from .corpus import sha256
from .export import export_json, export_pdf


class ReviewPanel(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.store = ReviewStore(host.root / "revisoes")
        self.review = None
        self.report_path = None
        self.evidence_paths = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Revisão local · Piloto para três famílias · Não autoriza emissão ou uso do sistema"))
        bar = QHBoxLayout()
        self.open_report = QPushButton("Abrir relatório PDF…")
        self.open_report.clicked.connect(self.choose_report)
        bar.addWidget(self.open_report)
        self.evidence_button = QPushButton("Selecionar evidências…")
        self.evidence_button.clicked.connect(self.choose_evidence)
        bar.addWidget(self.evidence_button)
        self.stage = QComboBox()
        self.stage.addItem("Antes da emissão", "antes_da_emissao")
        self.stage.addItem("Rascunho", "rascunho")
        bar.addWidget(self.stage)
        self.run = QPushButton("Executar conferência local")
        self.run.clicked.connect(self.run_review)
        bar.addWidget(self.run)
        layout.addLayout(bar)
        self.inputs = QLabel("Selecione um relatório. Nenhum dado é enviado à IA nesta aba.")
        self.inputs.setWordWrap(True)
        layout.addWidget(self.inputs)
        history_bar = QHBoxLayout()
        self.history = QComboBox()
        history_bar.addWidget(self.history, 1)
        load = QPushButton("Reabrir revisão")
        load.clicked.connect(self.load_selected)
        history_bar.addWidget(load)
        self.reviewer = QLineEdit()
        self.reviewer.setPlaceholderText("Nome do revisor para registrar decisões")
        history_bar.addWidget(self.reviewer, 1)
        layout.addLayout(history_bar)
        split = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        self.summary = QLabel("Nenhuma revisão executada.")
        self.summary.setWordWrap(True)
        ll.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Nível", "Regra", "Pág.", "Achado", "Decisão"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.select_finding)
        ll.addWidget(self.table, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        ll.addWidget(self.details)
        decision_bar = QHBoxLayout()
        self.decision = QComboBox()
        for value in ("pendente", "aceito", "corrigir", "falso_positivo"):
            self.decision.addItem(value.replace("_", " "), value)
        decision_bar.addWidget(self.decision)
        self.comment = QLineEdit()
        self.comment.setPlaceholderText("Justificativa obrigatória ao decidir")
        decision_bar.addWidget(self.comment, 1)
        save = QPushButton("Registrar decisão")
        save.clicked.connect(self.save_decision)
        decision_bar.addWidget(save)
        ll.addLayout(decision_bar)
        link_bar = QHBoxLayout()
        self.evidence_combo = QComboBox()
        link_bar.addWidget(self.evidence_combo, 1)
        self.role = QComboBox()
        self.role.addItems(["laudo", "certificado", "outra evidencia"])
        link_bar.addWidget(self.role)
        link = QPushButton("Associar ao achado")
        link.clicked.connect(self.link_evidence)
        link_bar.addWidget(link)
        ll.addLayout(link_bar)
        split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Página de origem · conferir também marcas e assinaturas"))
        self.preview = QLabel("Selecione um achado para ver a página.")
        self.preview.setMinimumSize(270, 360)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(self.preview, 1)
        split.addWidget(right)
        split.setSizes([760, 360])
        layout.addWidget(split, 1)
        exports = QHBoxLayout()
        pdf = QPushButton("Exportar parecer PDF…")
        pdf.clicked.connect(lambda: self.export("pdf"))
        exports.addWidget(pdf)
        js = QPushButton("Exportar dados JSON…")
        js.clicked.connect(lambda: self.export("json"))
        exports.addWidget(js)
        layout.addLayout(exports)
        self.refresh_history()

    def notify(self, text):
        self.host.show_error(text)

    def choose_report(self):
        path, _ = QFileDialog.getOpenFileName(self, "Relatório para revisão", "", "Relatório (*.pdf)")
        if path:
            self.report_path = path
            self.update_inputs()

    def choose_evidence(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Evidências deste relatório", "", "Evidências (*.pdf *.png *.jpg *.jpeg *.heic *.HEIC)")
        if paths:
            self.evidence_paths = paths
            self.update_inputs()

    def update_inputs(self):
        self.inputs.setText(f"Relatório: {Path(self.report_path).name if self.report_path else 'não selecionado'} | "
                            f"Evidências selecionadas: {len(self.evidence_paths)}. Novas seleções só entram ao executar a conferência.")

    def run_review(self):
        if not self.report_path:
            self.notify("Selecione um relatório PDF.")
            return
        report, evidence, stage = self.report_path, list(self.evidence_paths), self.stage.currentData()
        def operation():
            review = review_pdf(report, evidence, stage)
            self.store.save(review)
            return review
        self.host.run_job(operation, self.show_review)

    def refresh_history(self):
        self.history.clear()
        for path in self.store.list():
            try:
                review = self.store.load(path)
                self.history.addItem(f"{review.source['name']} · {review.created_at[:16]}", str(path))
            except (ValueError, TypeError, KeyError):
                continue

    def load_selected(self):
        if not self.history.currentData():
            return
        try:
            self.show_review(self.store.load(self.history.currentData()))
        except (OSError, ValueError, KeyError):
            self.notify("Não foi possível reabrir esta revisão.")

    def show_review(self, review):
        self.review = review
        self.report_path = review.source.get("path")
        self.evidence_paths = [item["path"] for item in review.evidence_files if item.get("path")]
        self.stage.setCurrentIndex(max(0, self.stage.findData(review.stage)))
        self.update_inputs()
        self.reviewer.setText(review.reviewer)
        self.table.setRowCount(len(review.findings))
        for row, finding in enumerate(review.findings):
            for col, value in enumerate([finding.severity, finding.rule, finding.page, finding.title, finding.decision]):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        counts = {level: sum(f.severity == level for f in review.findings) for level in ("bloqueante", "alerta", "informativo")}
        pending = sum(f.decision == "pendente" for f in review.findings)
        self.summary.setText(f"{review.source['name']} | {review.family} | {len(review.findings)} achados: "
                             f"{counts['bloqueante']} bloqueantes, {counts['alerta']} alertas, {counts['informativo']} informativos. "
                             f"{pending} decisões pendentes. Nenhuma liberação automática.")
        self.evidence_combo.clear()
        for evidence in review.evidence_files:
            self.evidence_combo.addItem(evidence["name"], evidence["sha256"])
        self.refresh_history()
        selected_history = self.history.findData(str(self.store.root / (review.id + ".json")))
        if selected_history >= 0:
            self.history.setCurrentIndex(selected_history)
        if review.findings:
            self.table.selectRow(0)
        self.host.status.setText("Revisão salva localmente. Confira as evidências e registre suas decisões.")

    def selected(self):
        row = self.table.currentRow()
        return self.review.findings[row] if self.review and 0 <= row < len(self.review.findings) else None

    def select_finding(self):
        finding = self.selected()
        if not finding:
            return
        evidence_names = {e["sha256"]: e["name"] for e in self.review.evidence_files}
        linked = "; ".join(f"{evidence_names.get(link['sha256'], 'arquivo não identificado')} ({link['role']})"
                           for link in self.review.evidence_links.get(finding.id, [])) or "nenhuma"
        self.details.setPlainText(f"{finding.title}\n\nOrigem: página {finding.page}\n{finding.evidence}\n\n"
                                 f"Conferência esperada: {finding.expected}\n\nAssociações: "
                                 f"{linked}")
        self.decision.setCurrentIndex(max(0, self.decision.findData(finding.decision)))
        self.comment.setText(finding.comment)
        try:
            path = self.review.source["path"]
            if sha256(path) != self.review.source["sha256"]:
                raise ValueError("Original alterado.")
            with pymupdf.open(path) as document:
                pix = document[finding.page - 1].get_pixmap(matrix=pymupdf.Matrix(0.85, 0.85), alpha=False)
            qt_pix = QPixmap()
            qt_pix.loadFromData(pix.tobytes("png"))
            self.preview.setPixmap(qt_pix.scaled(360, 510, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            self.preview.setText("Original indisponível ou alterado. A revisão salva permanece no histórico.")

    def save_decision(self):
        finding = self.selected()
        if not finding:
            return
        try:
            self.review.decide(finding.id, self.decision.currentData(), self.comment.text(), self.reviewer.text())
            self.store.save(self.review)
            row = self.table.currentRow()
            self.show_review(self.review)
            self.table.selectRow(row)
        except ValueError as error:
            self.notify(str(error))

    def link_evidence(self):
        finding = self.selected()
        digest = self.evidence_combo.currentData()
        if not finding or not digest or not self.reviewer.text().strip():
            self.notify("Selecione achado, evidência e informe o revisor.")
            return
        link = {"sha256": digest, "role": self.role.currentText(), "reviewer": self.reviewer.text().strip()}
        links = self.review.evidence_links.setdefault(finding.id, [])
        if link not in links:
            links.append(link)
            self.review.audit.append(dict(link, event="evidencia_associada", finding=finding.id,
                                          at=datetime.now(timezone.utc).isoformat()))
            self.store.save(self.review)
        self.select_finding()
        self.host.status.setText("Associação registrada. A identidade e o conteúdo da evidência ainda exigem conferência humana.")

    def export(self, kind):
        if not self.review:
            self.notify("Execute ou reabra uma revisão antes de exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar parecer de revisão", f"parecer.{kind}", f"Arquivo (*.{kind})")
        if not path:
            return
        try:
            (export_pdf if kind == "pdf" else export_json)(self.review, path)
            self.host.status.setText("Parecer exportado. Pendências e decisões constam no documento; não há liberação automática.")
        except (ValueError, OSError) as error:
            self.notify(str(error))
