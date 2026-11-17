"""Gera instalador por usuário a partir do pacote Windows já verificado."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from revisor.version import APP_VERSION


def build(dist, compiler):
    dist = Path(dist).resolve()
    package = dist / "RevisorCelacanto"
    if not (package / "RevisorCelacanto.exe").is_file() or not (package / "_internal" / "python312.dll").is_file():
        raise ValueError("Gere o pacote Windows completo antes do instalador.")
    if not compiler or not Path(compiler).is_file():
        raise ValueError("Compilador Inno Setup 6 não encontrado. Informe --compiler CAMINHO_ISCC.")
    subprocess.run([str(compiler), "/DAppVersion=" + APP_VERSION, "/DPackageDir=" + str(package),
                    "/DOutputPath=" + str(dist), str(Path(__file__).with_name("RevisorCelacanto.iss"))], check=True)
    output = dist / "RevisorCelacanto-Instalador.exe"
    if not output.is_file():
        raise ValueError("O compilador não gerou o instalador esperado.")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--compiler", default=shutil.which("ISCC") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
    args = parser.parse_args()
    print(build(args.dist, args.compiler))


if __name__ == "__main__":
    main()
