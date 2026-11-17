"""Empacota a pasta Windows e publica release imutável pelo GitHub CLI."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import zipfile
from revisor.version import APP_VERSION


def package_release(dist):
    dist = Path(dist)
    application = dist / "RevisorCelacanto"
    if not (application / "RevisorCelacanto.exe").is_file():
        raise ValueError("Pacote Windows ainda não foi gerado.")
    installer = dist / "RevisorCelacanto-Instalador.exe"
    if not installer.is_file():
        raise ValueError("Instalador Windows ainda não foi gerado e testado.")
    archive = dist / "RevisorCelacanto-Windows.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in application.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(dist))
    checksum = dist / "SHA256SUMS.txt"
    lines = []
    for asset in (archive, installer):
        digest = hashlib.sha256()
        with asset.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        lines.append(digest.hexdigest() + "  " + asset.name + "\n")
    checksum.write_text("".join(lines), encoding="utf-8")
    return archive, installer, checksum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    dist = Path(args.dist)
    archive, installer, checksum = package_release(dist)
    notes = dist / "release-notes.md"
    notes.write_text(f"Piloto Celacanto {APP_VERSION}\n\nNovo RevisorCelacanto-Instalador.exe: instala para o usuário atual, "
                     "cria atalho no menu Iniciar e oferece atalho na área de trabalho. "
                     "Não precisa instalar Python nem executar como administrador. "
                     "Não cria serviço nem inicialização automática com o Windows. "
                     "Biblioteca, histórico, critérios e credenciais ficam separados e são preservados na desinstalação. "
                     "Instalação, reinstalação, abertura e desinstalação são verificadas antes da publicação. "
                     "O ZIP portátil continua disponível e mantém as atualizações pelo aplicativo. "
                     "O instalador facilita a distribuição; não promete redução de RAM ou CPU. "
                     "Pacote Windows com atualizador integrado. "
                     "Preserva banco local, histórico e credenciais. Ainda requer revisão humana, validação com documentos completos "
                     "e teste de login/inferência reais. Não autoriza emissão técnica.\n", encoding="utf-8")
    if args.publish:
        tag = "v" + APP_VERSION
        exists = subprocess.run(["gh", "release", "view", tag], capture_output=True)
        if exists.returncode == 0:
            print("Esta versão já foi publicada. Aumente APP_VERSION para a próxima release.")
            return
        subprocess.run(["gh", "release", "create", tag, str(archive), str(installer), str(checksum), "--target",
                        os.environ["GITHUB_SHA"], "--title", "Celacanto " + APP_VERSION,
                        "--notes-file", str(notes)], check=True)


if __name__ == "__main__":
    main()
