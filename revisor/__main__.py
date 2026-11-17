import argparse
import json
import os
from pathlib import Path
import sys
import threading
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QListWidget, QListWidgetItem, QSpinBox,
    QPlainTextEdit, QMessageBox, QSplitter, QTabWidget)

from .auth import Auth, AuthError
from .corpus import Corpus, prepare
from . import ai


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    def run(self):
        try:
            self.done.emit(self.operation())
        except (AuthError, ValueError) as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("A operação falhou. Confira os arquivos, as dependências e o acesso ao cofre Windows.")


class Window(QMainWindow):
    def __init__(self, data_dir):
        super().__init__()
        self.setWindowTitle("Celacanto · Analisador de Relatórios")
        self.resize(1240, 850)
        self.root = Path(data_dir)
        self.auth = Auth(self.root)
        self.corpus = Corpus(self.root / "corpus")
        self.worker = None
        self.cancel = threading.Event()
        self.attachments = []
        self.setStyleSheet("QMainWindow {background:#f2f5f9;} QWidget {font-size:14px;} "
            "QPushButton {padding:9px; border:1px solid #a5b8ce; border-radius:5px; background:white;} "
            "QPushButton:disabled {color:#8b8b8b;} QPlainTextEdit,QListWidget {background:white; border:1px solid #c9d4e2;} "
            "QLabel {color:#123c6d;} QComboBox {padding:6px;}")
        body = QWidget()
        layout = QVBoxLayout(body)
        title = QLabel("CELACANTO  /  Conferência assistida de relatórios")
        title.setStyleSheet("font-size:23px; font-weight:bold; padding:12px;")
        layout.addWidget(title)
        layout.addWidget(QLabel("IA opcional · Os originais são preservados · A decisão de emitir é humana"))
        bar = QHBoxLayout()
        self.accounts = QComboBox()
        bar.addWidget(self.accounts, 1)
        self.login = QPushButton("Continue with ChatGPT")
        self.login.clicked.connect(self.sign_in)
        bar.addWidget(self.login)
        self.add_account = QPushButton("Adicionar conta")
        self.add_account.clicked.connect(lambda: self.sign_in(new=True))
        bar.addWidget(self.add_account)
        self.logout = QPushButton("Sair")
        self.logout.clicked.connect(lambda: self.run_job(self.auth.sign_out, self.after_auth))
        bar.addWidget(self.logout)
        self.models = QComboBox()
        bar.addWidget(self.models, 1)
        self.refresh = QPushButton("Carregar modelos")
        self.refresh.clicked.connect(self.refresh_models)
        bar.addWidget(self.refresh)
        layout.addLayout(bar)
        splitter = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Biblioteca local de referências"))
        self.import_button = QPushButton("Importar PDF, fotos ou ZIP…")
        self.import_button.clicked.connect(self.import_files)
        ll.addWidget(self.import_button)
        ll.addWidget(QLabel("Importar não envia arquivos nem treina o modelo."))
        self.files = QListWidget()
        self.files.currentItemChanged.connect(self.preview)
        ll.addWidget(self.files, 1)
        pagebar = QHBoxLayout()
        pagebar.addWidget(QLabel("Página do PDF:"))
        self.page = QSpinBox()
        self.page.setRange(1, 10000)
        self.page.valueChanged.connect(self.preview)
        pagebar.addWidget(self.page)
        self.add_page = QPushButton("Adicionar ao envio")
        self.add_page.clicked.connect(self.attach)
        pagebar.addWidget(self.add_page)
        ll.addLayout(pagebar)
        self.image = QLabel("Selecione uma referência para visualizar")
        self.image.setMinimumSize(300, 240)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self.image)
        splitter.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Páginas selecionadas para esta consulta (máximo 8)"))
        self.queue = QListWidget()
        self.queue.setMaximumHeight(115)
        rl.addWidget(self.queue)
        self.clear = QPushButton("Limpar seleção de envio")
        self.clear.clicked.connect(self.clear_queue)
        rl.addWidget(self.clear)
        self.question = QPlainTextEdit()
        self.question.setPlaceholderText("Descreva a conferência desejada e o papel de cada referência…")
        self.question.setMaximumHeight(100)
        rl.addWidget(self.question)
        self.send = QPushButton("Consultar IA com confirmação de envio…")
        self.send.setStyleSheet("background:#00489c; color:white; font-weight:bold; padding:12px;")
        self.send.clicked.connect(self.analyze)
        rl.addWidget(self.send)
        rl.addWidget(QLabel("Sugestões da IA · valores não confirmados · sem liberação automática"))
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        rl.addWidget(self.result, 1)
        splitter.addWidget(right)
        layout.addWidget(splitter, 1)
        self.status = QLabel("Offline. O login e as consultas são opcionais.")
        layout.addWidget(self.status)
        self.stop = QPushButton("Cancelar login")
        self.stop.clicked.connect(self.cancel.set)
        self.stop.setVisible(False)
        layout.addWidget(self.stop)
        from .review_ui import ReviewPanel
        tabs = QTabWidget()
        self.review_panel = ReviewPanel(self)
        tabs.addTab(self.review_panel, "Revisão local e parecer")
        tabs.addTab(body, "IA e biblioteca de referências")
        self.setCentralWidget(tabs)
        self.controls = [self.accounts, self.login, self.add_account, self.logout, self.models,
                         self.refresh, self.import_button, self.add_page, self.clear, self.send, self.question,
                         self.files, self.page, self.review_panel]
        self.accounts.currentIndexChanged.connect(self.change_account)
        self.reload_accounts()
        self.reload_files()

    def run_job(self, operation, done):
        if self.worker and self.worker.isRunning():
            return
        for widget in self.controls:
            widget.setEnabled(False)
        self.status.setText("Operação em andamento…")
        self.worker = Worker(operation)
        self.worker.done.connect(done)
        self.worker.failed.connect(lambda message: self.show_error(message))
        self.worker.finished.connect(self.unlock)
        self.worker.start()

    def unlock(self):
        for widget in self.controls:
            widget.setEnabled(True)
        self.stop.setVisible(False)

    def show_error(self, message):
        self.status.setText(message)
        QMessageBox.warning(self, "Operação não concluída", message)

    def reload_accounts(self):
        self.accounts.blockSignals(True)
        self.accounts.clear()
        self.accounts.addItem("Nenhuma conta selecionada", None)
        for cid, email, active in self.auth.accounts():
            self.accounts.addItem(f"{email} · {cid[-8:]}", cid)
            if active:
                self.accounts.setCurrentIndex(self.accounts.count() - 1)
        self.accounts.blockSignals(False)

    def change_account(self):
        cid = self.accounts.currentData()
        self.models.clear()
        if cid:
            self.auth.select(cid)
        else:
            data = self.auth.load()
            data["active"] = None
            self.auth.save(data)

    def sign_in(self, _checked=False, new=False):
        self.cancel.clear()
        selected = None if new else self.accounts.currentData()
        self.run_job(lambda: self.auth.sign_in(selected, self.cancel), self.after_auth)
        self.stop.setVisible(True)

    def after_auth(self, message):
        self.reload_accounts()
        self.models.clear()
        self.status.setText(message)

    def refresh_models(self):
        def done(items):
            self.models.clear()
            for slug, label in items:
                self.models.addItem(label, slug)
            self.status.setText(f"{len(items)} modelos disponíveis para a conta selecionada.")
        self.run_job(lambda: ai.models(self.auth), done)

    def reload_files(self):
        self.files.clear()
        for entry in self.corpus.entries():
            item = QListWidgetItem(entry[1])
            item.setToolTip("SHA-256: " + entry[2])
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.files.addItem(item)

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Importar referências", "", "Referências (*.zip *.pdf *.jpg *.jpeg *.png *.heic *.HEIC)")
        if not paths:
            return
        def operation():
            for path in paths:
                self.corpus.import_file(path)
            return "Referências importadas localmente. Nenhum arquivo enviado."
        def done(message):
            self.reload_files()
            self.status.setText(message)
        self.run_job(operation, done)

    def selected_page(self):
        item = self.files.currentItem()
        if not item:
            raise ValueError("Selecione um arquivo da biblioteca.")
        return prepare(item.data(Qt.ItemDataRole.UserRole), self.page.value())

    def preview(self, *_args):
        if not self.files.currentItem():
            return
        try:
            import base64
            attachment = self.selected_page()
            pixmap = QPixmap()
            pixmap.loadFromData(base64.b64decode(attachment["data"].split(",", 1)[1]))
            self.image.setPixmap(pixmap.scaled(440, 270, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            self.image.setText("Página indisponível. Confira o número e o arquivo.")

    def attach(self):
        try:
            attachment = self.selected_page()
            if len(self.attachments) >= 8:
                raise ValueError("Selecione no máximo 8 páginas por consulta.")
            if any((a["sha256"], a["page"]) == (attachment["sha256"], attachment["page"]) for a in self.attachments):
                return
            self.attachments.append(attachment)
            self.queue.addItem(f"{attachment['name']} · página {attachment['page']}")
        except ValueError as exc:
            self.show_error(str(exc))

    def clear_queue(self):
        self.attachments.clear()
        self.queue.clear()

    def analyze(self):
        model = self.models.currentData()
        question = self.question.toPlainText().strip()
        if not model or not question or not self.attachments:
            self.show_error("Carregue e selecione um modelo, descreva a consulta e adicione as páginas ao envio.")
            return
        names = "\n".join(f"• {a['name']} — página {a['page']}" for a in self.attachments)
        message = ("Serão enviados à OpenAI o texto da consulta e as imagens destas páginas:\n\n" + names +
                   "\n\nO uso está sujeito aos limites do seu plano. Autoriza esta consulta?")
        if QMessageBox.question(self, "Confirmar envio à OpenAI", message,
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                               QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        attachments = list(self.attachments)
        entry = dict(at=datetime.now(timezone.utc).isoformat(), model=model,
                     account=self.accounts.currentData(), status="autorizado",
                     sources=[{k: v for k, v in a.items() if k != "data"} for a in attachments])
        self.result.clear()
        def audit(status):
            with (self.root / "envios.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(dict(entry, status=status), ensure_ascii=False) + "\n")
        def operation():
            audit("autorizado")
            try:
                response = ai.analyze(self.auth, model, question, attachments)
            except Exception:
                audit("falhou")
                raise
            audit("concluido")
            return response
        def done(response):
            self.result.setPlainText("RASCUNHO — VALORES NÃO CONFIRMADOS\n\n" + response)
            self.status.setText("Consulta concluída. Confira cada sugestão com os originais.")
        self.run_job(operation, done)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel.set()
            self.status.setText("Aguarde a operação terminar antes de fechar. O login foi cancelado, se estava em andamento.")
            event.ignore()
        else:
            event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(Path(os.environ.get("LOCALAPPDATA", ".")) / "Celacanto" / "AnalisadorRelatorios"))
    parser.add_argument("--smoke", action="store_true", help="Abre e fecha a interface sem fazer login ou enviar dados")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    # Um processo por biblioteca evita corrida na rotação dos refresh tokens.
    from PySide6.QtCore import QLockFile
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(Path(args.data_dir) / "app.lock"))
    if not lock.tryLock(0):
        QMessageBox.warning(None, "Aplicativo já aberto", "Esta biblioteca já está aberta em outra instância.")
        return 1
    window = Window(args.data_dir)
    window.show()
    if args.smoke:
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
