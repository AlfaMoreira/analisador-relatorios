"""Empacota a pasta Windows e publica release imutável pelo GitHub CLI."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import zipfile
from revisor.version import APP_VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    dist = Path(args.dist)
    application = dist / "RevisorCelacanto"
    if not (application / "RevisorCelacanto.exe").is_file():
        raise SystemExit("Pacote Windows ainda não foi gerado.")
    archive = dist / "RevisorCelacanto-Windows.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in application.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(dist))
    checksum = dist / "SHA256SUMS.txt"
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n", encoding="utf-8")
    notes = dist / "release-notes.md"
    notes.write_text(f"Piloto Celacanto {APP_VERSION}\n\nAo selecionar um apontamento, o visualizador destaca em amarelo "
                     "a evidência literal encontrada na página e navega até a primeira área. "
                     "Destaque acompanha zoom e rotação; originais preservados. "
                     "Indicações organizadas em ponto, arquivo/página, prioridade, origem, evidência e ação recomendada. "
                     "A IA passa a fornecer uma citação literal separada da explicação. "
                     "Trechos não localizáveis e imagens sem texto recebem aviso, sem marcação inventada. "
                     "A cópia PDF comentada usa a mesma localização literal. "
                     "Pacote Windows com atualizador integrado. "
                     "Preserva banco local, histórico e credenciais. Ainda requer revisão humana, validação com documentos completos "
                     "e teste de login/inferência reais. Não autoriza emissão técnica.\n", encoding="utf-8")
    if args.publish:
        tag = "v" + APP_VERSION
        exists = subprocess.run(["gh", "release", "view", tag], capture_output=True)
        if exists.returncode == 0:
            print("Esta versão já foi publicada. Aumente APP_VERSION para a próxima release.")
            return
        subprocess.run(["gh", "release", "create", tag, str(archive), str(checksum), "--target",
                        os.environ["GITHUB_SHA"], "--title", "Celacanto " + APP_VERSION,
                        "--notes-file", str(notes)], check=True)


if __name__ == "__main__":
    main()
