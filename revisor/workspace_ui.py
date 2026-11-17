"""Fluxo único: documentos, IA, conferência local e navegação por achado."""
import json
from datetime import datetime, timezone
from pathlib import Path
import threading
import sys

import pymupdf
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFileDialog, QListWidget, QListWidgetItem, QSpinBox,
    QPlainTextEdit, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QCheckBox, QScrollArea, QProgressBar, QMenu, QDialog)
from .auth import Auth, AuthError
from .corpus import Corpus, prepare, sha256
from .packet import build_packet, batches, local_review
from .review import ReviewStore, compare_reviews
from .export import export_json, export_pdf
from . import ai
from .theme import STYLE, logo_path
from .learning import ExampleStore
from .annotations import export_annotated
from .version import APP_VERSION
from .updates import check_update, stage_update, start_installer, UpdateError


class Worker(QThread):
    progress = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.cancel = threading.Event()
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.operation(self.progress.emit, self.cancel)
        except (AuthError, ValueError, OSError) as error:
            self.error = str(error)
        except Exception:
            self.error = "A operação não foi concluída. Confira os documentos e tente novamente. Nenhuma aprovação foi gerada."


class Window(QMainWindow):
    def __init__(self, data_dir):
        super().__init__()
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.auth = Auth(self.root)
        self.corpus = Corpus(self.root / "corpus")
        self.store = ReviewStore(self.root / "revisoes")
        self.examples = ExampleStore(self.root / "exemplos.sqlite3")
        self.entries = []
        self.review = None
        self.worker = None
        self.visible_findings = []
        self.active_entry = None
        self.ia_ready = False
        self.setWindowTitle("Celacanto · Revisão de documentos")
        self.resize(1480, 960)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(14)
        header = QHBoxLayout()
        brand = QLabel()
        brand.setObjectName("brandLogo")
        pix = QPixmap(str(logo_path()))
        if not pix.isNull():
            crop = pix.copy(int(pix.width()*.08), int(pix.height()*.32), int(pix.width()*.84), int(pix.height()*.36))
            brand.setPixmap(crop.scaled(205, 82, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.setWindowIcon(QIcon(pix))
        else:
            brand.setText("CELACANTO")
        header.addWidget(brand)
        titles = QVBoxLayout()
        screen_title = QLabel("Revisão assistida")
        screen_title.setObjectName("screenTitle")
        titles.addWidget(screen_title)
        subtitle = QLabel(f"Versão {APP_VERSION} · Documentos, IA e conferência em um só lugar")
        subtitle.setObjectName("subtitle")
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.update_button = QPushButton("Atualizações")
        self.update_button.clicked.connect(self.check_updates)
        header.addWidget(self.update_button)
        self.ai_state = QLabel("IA desconectada")
        self.ai_state.setObjectName("aiStatus")
        self.ai_state.setMaximumHeight(40)
        header.addWidget(self.ai_state)
        self.connect_button = QPushButton("Conectar ChatGPT")
        self.connect_button.setObjectName("connectAI")
        self.connect_button.clicked.connect(self.sign_in)
        header.addWidget(self.connect_button)
        self.account = QComboBox()
        self.account.setMaximumWidth(230)
        self.account.currentIndexChanged.connect(self.switch_account)
        header.addWidget(self.account)
        self.logout = QPushButton("Sair da conta")
        self.logout.clicked.connect(self.sign_out)
        header.addWidget(self.logout)
        root.addLayout(header)
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("＋ Adicionar documentos")
        self.add_button.setObjectName("addDocuments")
        self.add_button.clicked.connect(self.add_documents)
        toolbar.addWidget(self.add_button)
        toolbar_note = QLabel("Relatório completo + anexos. Adicione mais arquivos quando precisar.")
        toolbar_note.setWordWrap(True)
        toolbar_note.setObjectName("subtitle")
        toolbar.addWidget(toolbar_note, 1)
        self.use_ai = QCheckBox("IA na primeira leitura")
        self.use_ai.setToolTip("A IA lê o conjunto após sua confirmação; o software confere suas regras em seguida.")
        toolbar.addWidget(self.use_ai)
        self.models = QComboBox()
        self.models.setMinimumWidth(155)
        self.models.setMaximumWidth(240)
        self.models.addItem("Conecte para escolher o modelo", None)
        toolbar.addWidget(self.models)
        self.run = QPushButton("Iniciar revisão")
        self.run.setObjectName("primaryAction")
        self.run.clicked.connect(self.start_review)
        toolbar.addWidget(self.run)
        root.addLayout(toolbar)
        split = QSplitter()
        split.setHandleWidth(12)
        left = QWidget()
        left.setObjectName("documentsPanel")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 18, 16, 16)
        documents_heading = QLabel("01  DOCUMENTOS")
        documents_heading.setObjectName("panelHeading")
        ll.addWidget(documents_heading)
        self.files = QListWidget()
        self.files.setWordWrap(True)
        self.files.currentRowChanged.connect(self.select_document)
        ll.addWidget(self.files, 1)
        self.file_note = QLabel("Arraste os arquivos para cá ou use Adicionar documentos. O primeiro PDF será o principal.")
        self.file_note.setWordWrap(True)
        ll.addWidget(self.file_note)
        options = QPushButton("⋯ Opções dos documentos")
        menu = QMenu(options)
        menu.addAction("Usar selecionado como principal", self.set_primary)
        menu.addAction("Retirar selecionado do conjunto", self.remove_selected)
        options.setMenu(menu)
        ll.addWidget(options)
        ll.addWidget(QLabel("HISTÓRICO E VERSÕES"))
        self.history = QComboBox()
        ll.addWidget(self.history)
        reopen = QPushButton("Reabrir revisão")
        reopen.clicked.connect(self.load_history)
        ll.addWidget(reopen)
        compare_button = QPushButton("Comparar com a revisão selecionada")
        compare_button.clicked.connect(self.compare_history)
        ll.addWidget(compare_button)
        self.use_examples = QCheckBox("Usar exemplos confirmados na IA")
        ll.addWidget(self.use_examples)
        self.example_count = QLabel("Base local: nenhum exemplo contribuído nesta rodada.")
        self.example_count.setWordWrap(True)
        ll.addWidget(self.example_count)
        contribute = QPushButton("Contribuir para a base local")
        contribute.clicked.connect(self.contribute_examples)
        ll.addWidget(contribute)
        split.addWidget(left)
        center = QWidget()
        center.setObjectName("viewerPanel")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(16, 18, 16, 16)
        self.document_title = QLabel("Documento e anexos")
        self.document_title.setWordWrap(True)
        cl.addWidget(self.document_title)
        navigation = QHBoxLayout()
        previous = QPushButton("‹")
        previous.clicked.connect(lambda: self.page.setValue(self.page.value() - 1))
        navigation.addWidget(previous)
        navigation.addWidget(QLabel("Página"))
        self.page = QSpinBox()
        self.page.setRange(1, 1)
        self.page.valueChanged.connect(self.render_page)
        navigation.addWidget(self.page)
        self.page_total = QLabel("de 0")
        navigation.addWidget(self.page_total)
        following = QPushButton("›")
        following.clicked.connect(lambda: self.page.setValue(self.page.value() + 1))
        navigation.addWidget(following)
        navigation.addStretch(1)
        navigation.addWidget(QLabel("Zoom"))
        self.zoom = QSpinBox()
        self.zoom.setRange(30, 250)
        self.zoom.setSingleStep(10)
        self.zoom.setSuffix("%")
        self.zoom.setValue(80)
        self.zoom.valueChanged.connect(self.render_page)
        navigation.addWidget(self.zoom)
        cl.addLayout(navigation)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.preview = QLabel("Adicione o documento completo para começar.\nOs achados abrirão a página correspondente aqui.")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(420, 450)
        self.scroll.setWidget(self.preview)
        cl.addWidget(self.scroll, 1)
        split.addWidget(center)
        right = QWidget()
        right.setObjectName("findingsPanel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 18, 16, 16)
        findings_heading = QLabel("03  CONFERIR E DECIDIR")
        findings_heading.setObjectName("panelHeading")
        rl.addWidget(findings_heading)
        self.summary = QLabel("1. Adicionar documentos → 2. Iniciar revisão → 3. Conferir achados")
        self.summary.setObjectName("reviewSummary")
        self.summary.setWordWrap(True)
        rl.addWidget(self.summary)
        self.findings = QTableWidget(0, 4)
        self.findings.setHorizontalHeaderLabels(["Origem", "Pág.", "Apontamento", "Acompanhar"])
        self.findings.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.findings.setColumnWidth(0, 55)
        self.findings.setColumnWidth(1, 40)
        self.findings.setColumnWidth(3, 85)
        self.findings.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.findings.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.findings.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.findings.setAlternatingRowColors(True)
        self.findings.verticalHeader().hide()
        self.findings.itemSelectionChanged.connect(self.select_finding)
        rl.addWidget(self.findings, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(165)
        rl.addWidget(self.details)
        self.tracked = QCheckBox("Este ponto é pertinente · acompanhar na próxima versão")
        rl.addWidget(self.tracked)
        identity = QHBoxLayout()
        self.reviewer = QLineEdit()
        self.reviewer.setPlaceholderText("Nome do revisor")
        identity.addWidget(self.reviewer, 1)
        self.decision = QComboBox()
        for label, value in [("Pendente", "pendente"), ("Confirmado", "aceito"), ("Solicitar correção", "corrigir"), ("Descartar", "falso_positivo")]:
            self.decision.addItem(label, value)
        identity.addWidget(self.decision)
        rl.addLayout(identity)
        self.comment = QLineEdit()
        self.comment.setPlaceholderText("Justificativa para confirmar ou descartar; anotação para acompanhar")
        rl.addWidget(self.comment)
        save = QPushButton("Salvar apontamento")
        save.clicked.connect(self.save_tracking)
        rl.addWidget(save)
        export_bar = QHBoxLayout()
        pdf = QPushButton("PDF comentado")
        pdf.clicked.connect(lambda: self.export("pdf"))
        export_bar.addWidget(pdf)
        js = QPushButton("Dados para melhoria")
        js.clicked.connect(lambda: self.export("json"))
        export_bar.addWidget(js)
        rl.addLayout(export_bar)
        split.addWidget(right)
        split.setSizes([230, 620, 530])
        root.addWidget(split, 1)
        self.status = QLabel("Pronto. A revisão local funciona sem IA; nenhum arquivo é enviado sem confirmação.")
        self.status.setObjectName("footerStatus")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        bottom = QHBoxLayout()
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.hide()
        bottom.addWidget(self.busy, 1)
        self.cancel_button = QPushButton("Cancelar operação")
        self.cancel_button.clicked.connect(self.cancel_job)
        self.cancel_button.hide()
        bottom.addWidget(self.cancel_button)
        root.addLayout(bottom)
        self.setCentralWidget(body)
        self.input_controls = [self.add_button, self.run, self.use_ai, self.models, self.connect_button, self.update_button,
                               self.account, self.logout, options, reopen, compare_button, contribute,
                               self.use_examples, save, pdf, js]
        self.refresh_history()
        self.reload_accounts()
        if self.account.currentData():
            QTimer.singleShot(0, self.load_models)
        result_path = self.root / "update-result.json"
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                self.status.setText("Atualização concluída; sua biblioteca local foi preservada." if result.get("success") else
                                    "A atualização não foi concluída. " + result.get("message", "A versão anterior está disponível."))
            except (ValueError, OSError):
                pass

    def check_updates(self):
        self.status.setText("Consultando a versão publicada no GitHub…")
        def checked(release):
            if release is None:
                self.status.setText(f"Nenhuma atualização mais nova disponível. Versão atual: {APP_VERSION}.")
                return
            if not getattr(sys, "frozen", False):
                self.show_error("A atualização automática funciona no pacote Windows. Esta execução usa o código-fonte.")
                return
            message = (f"Versão disponível: {release.version}\nVersão atual: {APP_VERSION}\n\n"
                       f"Download: {release.size / 1024 / 1024:.1f} MB\n\n{release.notes[:4000]}\n\n"
                       "O programa será fechado e reaberto. Banco local, revisões e credenciais permanecem na biblioteca do usuário. "
                       "Será guardada uma cópia da versão anterior. Baixar e instalar agora?")
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Atualização disponível")
            dialog.setTextFormat(Qt.TextFormat.PlainText)
            dialog.setText(message)
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            if dialog.exec() != QMessageBox.StandardButton.Yes:
                self.status.setText("Atualização adiada. O programa atual continua disponível.")
                return
            def staged(source):
                try:
                    start_installer(source, Path(sys.executable).parent, self.root)
                    self.close()
                except (UpdateError, OSError) as error:
                    self.show_error(str(error))
            self.run_job(lambda progress, cancel: stage_update(release, self.root / "updates", progress, cancel), staged)
        self.run_job(lambda progress, cancel: check_update(), checked)

    def show_error(self, message):
        self.status.setText(message)
        QMessageBox.warning(self, "Confira esta etapa", message)

    def run_job(self, operation, done):
        if self.worker:
            return
        for control in self.input_controls:
            control.setEnabled(False)
        self.busy.show()
        self.cancel_button.show()
        worker = Worker(operation)
        self.worker = worker
        worker.progress.connect(self.status.setText)
        def finished():
            self.worker = None
            self.busy.hide()
            self.cancel_button.hide()
            for control in self.input_controls:
                control.setEnabled(True)
            if worker.error:
                self.show_error(worker.error)
            else:
                done(worker.result)
            worker.deleteLater()
        worker.finished.connect(finished)
        worker.start()

    def cancel_job(self):
        if self.worker:
            self.worker.cancel.set()
            self.status.setText("Cancelamento solicitado. Aguardando a etapa atual encerrar…")

    def reload_accounts(self):
        self.account.blockSignals(True)
        self.account.clear()
        self.account.addItem("Nova conta ChatGPT", None)
        for cid, label, active in self.auth.accounts():
            self.account.addItem(label, cid)
            if active:
                self.account.setCurrentIndex(self.account.count() - 1)
        self.account.blockSignals(False)

    def sign_in(self):
        selected = self.account.currentData()
        self.ai_state.setText("Aguardando login no navegador…")
        self.status.setText("Conclua o login e a autorização no navegador. Em seguida o programa verificará os modelos automaticamente.")
        def operation(progress, cancel):
            progress("Conectando ao ChatGPT; aguarde o navegador e conclua a autorização.")
            try:
                return {"message": self.auth.sign_in(selected, cancel)}
            except (AuthError, OSError) as error:
                return {"error": str(error)}
        def done(result):
            if result.get("error"):
                self.ia_ready = False
                self.use_ai.setChecked(False)
                self.ai_state.setText("Login não concluído")
                self.show_error(result["error"] + " Nenhuma análise de IA foi executada.")
                return
            self.reload_accounts()
            self.status.setText(result["message"])
            self.load_models()
        self.run_job(operation, done)

    def switch_account(self):
        cid = self.account.currentData()
        self.ia_ready = False
        self.use_ai.setChecked(False)
        self.models.clear()
        if cid:
            self.auth.select(cid)
            self.load_models()
        else:
            data = self.auth.load()
            data["active"] = None
            self.auth.save(data)
            self.ai_state.setText("IA desconectada")

    def load_models(self):
        self.ai_state.setText("Verificando acesso à IA…")
        def operation(progress, cancel):
            try:
                return dict(models=ai.models(self.auth))
            except AuthError as error:
                return dict(error=str(error))
        def done(result):
            self.models.clear()
            self.ia_ready = False
            if result.get("error"):
                self.ai_state.setText("IA indisponível · reconecte a conta")
                self.use_ai.setChecked(False)
                self.status.setText(result["error"] + " A revisão local continua disponível.")
                return
            for slug, label in result["models"]:
                self.models.addItem(label, slug)
            self.ia_ready = bool(result["models"])
            self.use_ai.setChecked(self.ia_ready)
            self.ai_state.setText("● IA pronta para revisar" if self.ia_ready else "Conta conectada, sem modelos disponíveis")
            self.status.setText("IA pronta. Adicione os documentos e clique em Iniciar revisão; o envio será confirmado antes da análise."
                                if self.ia_ready else "A conta não disponibilizou modelos. Reconecte ou use a revisão local.")
        self.run_job(operation, done)

    def sign_out(self):
        def done(message):
            self.ia_ready = False
            self.use_ai.setChecked(False)
            self.models.clear()
            self.reload_accounts()
            self.ai_state.setText("IA desconectada")
            self.status.setText(message)
        self.run_job(lambda progress, cancel: self.auth.sign_out(), done)

    def add_documents(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Adicionar relatório e anexos ao mesmo conjunto", "",
            "Documentos (*.pdf *.zip *.jpg *.jpeg *.png *.heic *.HEIC)")
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths):
        existing = {e[2] for e in self.entries}
        def operation(progress, cancel):
            selected_hashes = []
            for path in paths:
                progress(f"Adicionando {Path(path).name}…")
                selected_hashes.extend(self.corpus.import_file(path))
            by_hash = {e[2]: e for e in self.corpus.entries()}
            return [by_hash[digest] for digest in dict.fromkeys(selected_hashes)]
        def done(items):
            self.entries.extend(e for e in items if e[2] not in existing)
            self.refresh_files()
            self.status.setText("Documentos adicionados ao conjunto. Execute a revisão para incluir as novas informações; nenhum arquivo foi enviado.")
        self.run_job(operation, done)

    def refresh_files(self):
        self.files.blockSignals(True)
        self.files.clear()
        first_pdf = next((e[2] for e in self.entries if Path(e[3]).suffix.lower() == ".pdf"), None)
        for entry in self.entries:
            item = QListWidgetItem(("PRINCIPAL\n" if entry[2] == first_pdf else "ANEXO\n") + entry[1])
            item.setToolTip(entry[1])
            self.files.addItem(item)
        self.files.blockSignals(False)
        if self.entries:
            self.files.setCurrentRow(0)
        self.file_note.setText(f"{len(self.entries)} arquivo(s) no conjunto. Use o mesmo botão para adicionar anexos depois.")

    def set_primary(self):
        row = self.files.currentRow()
        if row >= 0 and Path(self.entries[row][3]).suffix.lower() == ".pdf":
            self.entries.insert(0, self.entries.pop(row))
            self.refresh_files()
            self.status.setText("Documento principal alterado. Execute uma nova revisão.")

    def remove_selected(self):
        row = self.files.currentRow()
        if row >= 0:
            self.entries.pop(row)
            self.active_entry = None
            self.preview.clear()
            self.refresh_files()
            self.status.setText("Arquivo retirado deste conjunto; a cópia local e o original foram preservados.")

    def select_document(self, row):
        if not 0 <= row < len(self.entries):
            return
        self.active_entry = self.entries[row]
        self.document_title.setText(self.active_entry[1])
        try:
            if Path(self.active_entry[3]).suffix.lower() == ".pdf":
                with pymupdf.open(self.active_entry[3]) as doc:
                    total = len(doc)
            else:
                total = 1
            self.page.setRange(1, max(1, total))
            self.page.setValue(1)
            self.page_total.setText(f"de {total}")
            self.render_page()
        except Exception:
            self.preview.setText("Não foi possível abrir este documento.")

    def render_page(self):
        if not self.active_entry:
            return
        try:
            import base64
            attachment = prepare(self.active_entry, self.page.value())
            pix = QPixmap()
            pix.loadFromData(base64.b64decode(attachment["data"].split(",", 1)[1]))
            width = int(760 * self.zoom.value() / 100)
            pix = pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
            self.preview.setMinimumSize(0, 0)
            self.preview.setPixmap(pix)
            self.preview.resize(pix.size())
        except Exception:
            self.preview.setText("Página indisponível ou arquivo alterado.")

    def start_review(self):
        wants_ai = self.use_ai.isChecked()
        model = self.models.currentData()
        if wants_ai and (not self.ia_ready or not model):
            self.show_error("A IA ainda não está pronta. Clique em Conectar ChatGPT e conclua a verificação, ou desmarque IA na primeira leitura.")
            return
        selected = list(self.entries)
        def prepared(packet):
            if wants_ai and self.use_examples.isChecked():
                from .review import normalized
                primary = next(d for d in packet["documents"] if d["kind"] == "pdf")
                header = normalized(next(p["text"] for p in packet["pages"] if p["document"] == primary["id"]))
                family = "ar_comprimido_respiravel" if "ar comprimido respiravel" in header else "hidrogenio" if "hidrogenio" in header else "ar_ambiente" if "ar ambiente" in header else "desconhecida"
                packet["examples"] = [{k: e[k] for k in ("rule", "title", "evidence", "expected", "comment", "decision")}
                                      for e in self.examples.examples(family)]
            if wants_ai and not self.confirm_send(packet):
                self.status.setText("Envio cancelado. Nenhum documento foi enviado à IA.")
                return
            self.run_packet(packet, model if wants_ai else None)
        self.run_job(lambda progress, cancel: build_packet(selected, progress, cancel), prepared)

    def confirm_send(self, packet):
        descriptions = "\n".join(f"• {d['name']} — {d['pages']} página(s)" for d in packet["documents"])
        images = sum("image" in p for p in packet["pages"])
        message = ("A IA fará a primeira leitura, seguida das regras do software. Serão enviados à OpenAI:\n\n" +
                   descriptions + f"\n\nTodas as {len(packet['pages'])} páginas entram na leitura: texto extraído e "
                   f"{images} página(s)/foto(s) completas como imagem, em {len(batches(packet))} parte(s). "
                   f"Inclui {len(packet.get('examples', []))} exemplo(s) confirmado(s) da base local. "
                   "O uso depende dos limites do plano. Autoriza esta revisão?")
        return QMessageBox.question(self, "Confirmar primeira leitura com IA", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def run_packet(self, packet, model=None):
        previous = self.review.id if self.review else None
        def operation(progress, cancel):
            suggestions, notes, ai_error = [], [], None
            if model:
                record = {"at": datetime.now(timezone.utc).isoformat(), "model": model,
                          "examples": len(packet.get("examples", [])),
                          "files": [{k: d[k] for k in ("name", "sha256", "pages")} for d in packet["documents"]]}
                def audit(status):
                    with (self.root / "envios.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(dict(record, status=status), ensure_ascii=False) + "\n")
                audit("autorizado")
                try:
                    suggestions, notes = ai.review_packet(self.auth, model, packet, progress, cancel)
                    audit("concluido")
                except AuthError as error:
                    audit("falhou")
                    if cancel.is_set():
                        raise ValueError("Revisão cancelada. Nenhuma resposta parcial foi aceita.")
                    ai_error = str(error)
            if cancel.is_set():
                raise ValueError("Revisão cancelada.")
            progress("Conferindo critérios e consistência com as regras locais…")
            review = local_review(packet)
            review.findings = suggestions + review.findings
            review.ai_model = model or ""
            review.ai_status = "falhou" if ai_error else "concluida" if model else "nao_utilizada"
            review.limitations.extend(notes)
            if ai_error:
                review.limitations.append("IA não concluída: " + ai_error)
            if model:
                review.limitations.append("A IA recebeu texto e imagem de todas as páginas em lotes. Leituras de imagem permanecem não confirmadas; relações entre lotes exigem conferência humana.")
            if previous:
                review.audit.append({"at": datetime.now(timezone.utc).isoformat(), "event": "nova_rodada", "previous_review": previous})
            self.store.save(review)
            return review
        def done(review):
            self.show_review(review)
            if review.ai_status == "falhou":
                self.show_error("A IA não concluiu a análise. Os achados mostrados são das regras locais. " +
                                next((x for x in review.limitations if x.startswith("IA não concluída:")), ""))
        self.run_job(operation, done)

    def show_review(self, review):
        self.review = review
        self.reviewer.setText(review.reviewer)
        self.visible_findings = list(review.findings)
        self.findings.blockSignals(True)
        self.findings.setRowCount(len(review.findings))
        for row, finding in enumerate(review.findings):
            for col, text in enumerate(["IA" if finding.origin == "ia" else "Regra", finding.page, finding.title, "Sim" if finding.tracked else "—"]):
                item = QTableWidgetItem(str(text))
                item.setToolTip(f"{finding.severity} · {finding.rule}")
                self.findings.setItem(row, col, item)
        self.findings.blockSignals(False)
        count_ai = sum(f.origin == "ia" for f in review.findings)
        label = {"concluida": "IA concluída + regras locais", "falhou": "IA falhou; somente regras locais", "nao_utilizada": "Revisão local; IA não utilizada"}[review.ai_status]
        self.summary.setText(f"{label}\n{count_ai} sugestões da IA · {len(review.findings)-count_ai} achados locais. Clique para abrir a página.")
        self.refresh_history()
        if review.findings:
            self.findings.selectRow(0)
            self.select_finding()
        else:
            self.details.clear()
        self.status.setText("Apontamentos salvos. Marque os pontos pertinentes para confrontar com a próxima versão.")

    def selected_finding(self):
        row = self.findings.currentRow()
        return self.visible_findings[row] if 0 <= row < len(self.visible_findings) else None

    def select_finding(self):
        finding = self.selected_finding()
        if not finding:
            return
        digest = finding.document_sha256 or self.review.source["sha256"]
        row = next((i for i, e in enumerate(self.entries) if e[2] == digest), None)
        if row is not None:
            self.files.setCurrentRow(row)
            self.page.setValue(finding.page)
            self.render_page()
        self.details.setPlainText(f"{'Sugestão da IA · confirmar' if finding.origin == 'ia' else 'Regra do software'}\n"
                                 f"{finding.severity} · {finding.rule} · página {finding.page}\n\n"
                                 f"{finding.evidence}\n\nConferir: {finding.expected}")
        self.tracked.setChecked(finding.tracked)
        self.decision.setCurrentIndex(max(0, self.decision.findData(finding.decision)))
        self.comment.setText(finding.comment)

    def save_tracking(self):
        finding = self.selected_finding()
        if not finding:
            return
        try:
            decision = self.decision.currentData()
            if decision != finding.decision or decision != "pendente":
                self.review.decide(finding.id, decision, self.comment.text(), self.reviewer.text())
            finding.tracked = self.tracked.isChecked()
            if decision in {"aceito", "corrigir"}:
                finding.tracked = True
            elif decision == "falso_positivo":
                finding.tracked = False
            finding.comment = self.comment.text().strip()
            self.review.audit.append({"at": datetime.now(timezone.utc).isoformat(), "event": "apontamento_atualizado",
                                      "finding": finding.id, "tracked": finding.tracked, "comment": finding.comment})
            self.store.save(self.review)
            row = self.findings.currentRow()
            self.show_review(self.review)
            self.findings.selectRow(row)
        except ValueError as error:
            self.show_error(str(error))

    def contribute_examples(self):
        if not self.review:
            self.show_error("Abra uma revisão e confirme os apontamentos pertinentes antes de contribuir.")
            return
        try:
            count = self.examples.contribute(self.review)
            total = len(self.examples.examples(self.review.family, limit=100000))
            self.example_count.setText(f"Base local desta família: {total} exemplo(s) confirmado(s).")
            self.status.setText(f"{count} exemplo(s) atualizado(s) na base local. Nenhum dado foi enviado à IA e nenhum modelo foi treinado.")
        except ValueError as error:
            self.show_error(str(error))

    def compare_history(self):
        if not self.review or not self.history.currentData():
            self.show_error("Execute a revisão atual e selecione no histórico a versão anterior que deseja comparar.")
            return
        try:
            previous = self.store.load(self.history.currentData())
            comparison = compare_reviews(previous, self.review)
            self.review.comparison = comparison
            self.store.save(self.review)
        except ValueError as error:
            self.show_error(str(error))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Comparação dos apontamentos")
        dialog.resize(900, 560)
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialog)
        note = QLabel(comparison["note"])
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTableWidget(len(comparison["items"]), 4)
        table.setHorizontalHeaderLabels(["Situação", "Apontamento", "Antes", "Agora"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        labels = {"persiste": "Ainda detectado", "nao_redetectado": "Não redetectado · confirmar", "novo": "Novo apontamento"}
        for row, item in enumerate(comparison["items"]):
            for col, text in enumerate([labels[item["state"]], item["title"], item["previous_page"] or "—", item["current_page"] or "—"]):
                table.setItem(row, col, QTableWidgetItem(str(text)))
        def navigate(row, _column):
            identifier = comparison["items"][row]["current_finding"]
            if identifier:
                index = next(i for i, f in enumerate(self.visible_findings) if f.id == identifier)
                self.findings.selectRow(index)
                dialog.accept()
        table.cellDoubleClicked.connect(navigate)
        layout.addWidget(table, 1)
        layout.addWidget(QLabel("Duplo clique em um apontamento atual para abrir sua página."))
        dialog.exec()

    def refresh_history(self):
        self.history.clear()
        for path in self.store.list():
            try:
                review = self.store.load(path)
                self.history.addItem(f"{review.source['name']} · {review.created_at[:16]}", str(path))
            except (ValueError, KeyError, TypeError):
                continue

    def load_history(self):
        path = self.history.currentData()
        if not path:
            return
        review = self.store.load(path)
        docs = review.documents or [review.source, *review.evidence_files]
        self.entries = [(0, d["name"], d["sha256"], d["path"]) for d in docs if d.get("path")]
        self.refresh_files()
        self.show_review(review)

    def export(self, kind):
        if not self.review:
            self.show_error("Execute ou reabra uma revisão antes de exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar parecer", f"parecer.{kind}", f"Arquivo (*.{kind})")
        if path:
            try:
                if kind == "pdf":
                    export_annotated(self.review, path)
                else:
                    self.examples.export(self.review, path)
                self.status.setText("Cópia comentada exportada sem alterar os originais." if kind == "pdf" else
                                    "JSON exportado com a revisão e os exemplos confirmados para melhoria do sistema.")
            except (OSError, ValueError) as error:
                self.show_error(str(error))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.worker:
            self.add_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])

    def closeEvent(self, event):
        if self.worker:
            self.cancel_job()
            event.ignore()
        else:
            event.accept()
