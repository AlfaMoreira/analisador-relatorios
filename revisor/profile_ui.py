"""Cadastro local de critérios com aprovação explícita e importação/exportação."""
import json
from datetime import date
from pathlib import Path
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QPlainTextEdit, QCheckBox, QPushButton, QLabel, QFileDialog, QMessageBox)
from .profiles import FAMILIES


class ProfileDialog(QDialog):
    def __init__(self, store, parent=None, initial=None):
        super().__init__(parent)
        self.store = store
        self.saved_id = None
        self.setWindowTitle("Critérios e análise crítica por cliente")
        self.resize(850, 760)
        layout = QVBoxLayout(self)
        note = QLabel("Cadastre critérios acordados e suas fontes. Versões salvas não são sobrescritas.\n"
                      "Para aprovar ou mudar um perfil existente, informe uma nova versão.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.fields = {}
        for key, label, default in [("client_id", "Identificador do cliente", ""), ("client_name", "Nome do cliente", ""),
            ("contract", "Contrato / escopo", ""), ("version", "Versão do perfil", "1"),
            ("valid_from", "Vigente desde (AAAA-MM-DD)", date.today().isoformat()),
            ("valid_until", "Vigente até (opcional)", ""), ("approved_by", "Responsável pela aprovação", "")]:
            field = QLineEdit(default)
            self.fields[key] = field
            form.addRow(label, field)
        self.family = QComboBox()
        self.family.addItems(FAMILIES)
        form.addRow("Família", self.family)
        layout.addLayout(form)
        layout.addWidget(QLabel("Análise crítica do escopo (dado de referência, não instruções da IA)"))
        self.analysis = QPlainTextEdit()
        self.analysis.setMaximumHeight(80)
        layout.addWidget(self.analysis)
        layout.addWidget(QLabel("Critérios em JSON — importe um perfil ou preencha o modelo abaixo"))
        self.criteria = QPlainTextEdit(json.dumps([{"id": "DOC-01", "parameter": "Identificação do ensaio",
            "requirement": "Descreva aqui o requisito acordado", "source": "Identifique contrato ou referência e edição",
            "section": "Identifique a seção", "applicability": "Descreva quando se aplica"}], ensure_ascii=False, indent=2))
        layout.addWidget(self.criteria, 1)
        self.approved = QCheckBox("Confirmo que os critérios foram conferidos e aprovados pelo responsável identificado")
        layout.addWidget(self.approved)
        actions = QHBoxLayout()
        for label, callback in [("Importar JSON", self.import_json), ("Exportar JSON", self.export_json), ("Salvar nova versão", self.save)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        if initial:
            self.fill(initial)

    def fill(self, data):
        for key, field in self.fields.items():
            field.setText(str(data.get(key, "")))
        self.family.setCurrentText(data.get("family", FAMILIES[0]))
        self.analysis.setPlainText(data.get("critical_analysis", ""))
        self.criteria.setPlainText(json.dumps(data.get("criteria", []), ensure_ascii=False, indent=2))
        # Importação ou cópia não substitui a confirmação de aprovação.
        self.approved.setChecked(False)

    def data(self):
        try:
            criteria = json.loads(self.criteria.toPlainText())
        except ValueError:
            raise ValueError("JSON dos critérios inválido. Confira aspas, vírgulas e colchetes.") from None
        return dict({k: f.text().strip() for k, f in self.fields.items()}, family=self.family.currentText(),
            critical_analysis=self.analysis.toPlainText(), criteria=criteria,
            status="aprovado" if self.approved.isChecked() else "rascunho")

    def import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar perfil local", "", "JSON (*.json)")
        if path:
            try:
                if Path(path).stat().st_size > 100000:
                    raise ValueError("Arquivo muito grande para um perfil.")
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                from .profiles import validate_profile
                self.fill(validate_profile(data))
            except (ValueError, OSError, TypeError) as error:
                QMessageBox.warning(self, "Perfil não importado", str(error))

    def export_json(self):
        try:
            from .profiles import validate_profile
            data = validate_profile(self.data())
            path, _ = QFileDialog.getSaveFileName(self, "Exportar perfil", "criterios.json", "JSON (*.json)")
            if path:
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Confira os critérios", str(error))

    def save(self):
        try:
            self.saved_id = self.store.save(self.data())
            self.accept()
        except ValueError as error:
            QMessageBox.warning(self, "Confira os critérios", str(error))
