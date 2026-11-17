"""Empacota sem capturar DLLs de outros programas presentes no PATH."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distpath", default="dist")
    parser.add_argument("--workpath", default=str(Path(os.environ.get("LOCALAPPDATA", ".")) / "Celacanto" / "build"))
    args = parser.parse_args()
    project = Path(__file__).resolve().parent
    work = Path(args.workpath).resolve()
    work.mkdir(parents=True, exist_ok=True)
    old_path = os.environ.get("PATH", "")
    system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    os.environ["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(system / "System32"), str(system)])
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(work / "cache")
    try:
        from PyInstaller.__main__ import run
        run(["--noconfirm", "--clean", "--onedir", "--windowed", "--name", "RevisorCelacanto",
             "--add-data", str(project / "assets") + os.pathsep + "assets",
             "--add-data", str(project / "revisor" / "skills") + os.pathsep + "revisor/skills",
             "--distpath", str(Path(args.distpath).resolve()), "--workpath", str(work),
             "--specpath", str(work), str(project / "app.py")])
    finally:
        os.environ["PATH"] = old_path


if __name__ == "__main__":
    main()
