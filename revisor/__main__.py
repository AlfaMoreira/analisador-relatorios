import argparse
import os
from pathlib import Path
import sys
from PySide6.QtCore import QLockFile, QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from .workspace_ui import Window


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(Path(os.environ.get("LOCALAPPDATA", ".")) / "Celacanto" / "AnalisadorRelatorios"))
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        from .profiles import FAMILIES, load_skill
        for family in FAMILIES:
            load_skill(family)
    app = QApplication(sys.argv[:1])
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(Path(args.data_dir) / "app.lock"))
    if not lock.tryLock(0):
        QMessageBox.warning(None, "Aplicativo já aberto", "Esta biblioteca já está aberta em outra instância.")
        return 1
    window = Window(args.data_dir)
    window.show()
    if args.smoke:
        QTimer.singleShot(500, window.close)
    result = app.exec()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
