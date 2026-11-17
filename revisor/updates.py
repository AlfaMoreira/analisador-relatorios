"""Atualizações de releases GitHub; sem modificar a biblioteca do usuário."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, unquote
import uuid
import zipfile

from .version import APP_VERSION

REPOSITORY = "AlfaMoreira/analisador-relatorios"
ASSET_NAME = "RevisorCelacanto-Windows.zip"
EXE_NAME = "RevisorCelacanto.exe"
MAX_DOWNLOAD = 500 * 1024 * 1024


class UpdateError(ValueError):
    pass


def version_tuple(version):
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", version):
        raise UpdateError("A versão publicada não tem um identificador estável reconhecido.")
    return tuple(int(n) for n in version.lstrip("v").split("."))


@dataclass
class Release:
    version: str
    url: str
    sha256: str
    size: int
    notes: str


def parse_release(data, current=APP_VERSION):
    if data.get("draft") or data.get("prerelease"):
        return None
    version = data.get("tag_name", "")
    if version_tuple(version) <= version_tuple(current):
        return None
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if not asset:
        raise UpdateError("A nova versão ainda não tem o pacote Windows disponível.")
    url = asset.get("browser_download_url", "")
    parsed = urlsplit(url)
    expected = f"/{REPOSITORY}/releases/download/{version}/{ASSET_NAME}"
    if parsed.scheme != "https" or parsed.hostname != "github.com" or unquote(parsed.path) != expected or parsed.query:
        raise UpdateError("O download não corresponde ao repositório oficial do aplicativo.")
    digest = asset.get("digest", "")
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
        raise UpdateError("O GitHub não forneceu a verificação de integridade do pacote. A atualização não será instalada.")
    size = asset.get("size", 0)
    if type(size) is not int or not 0 < size <= MAX_DOWNLOAD:
        raise UpdateError("O tamanho do pacote de atualização é inválido.")
    return Release(version.lstrip("v"), url, digest.split(":", 1)[1].lower(), size, str(data.get("body", ""))[:12000])


def check_update(current=APP_VERSION):
    import requests
    try:
        response = requests.get(f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "RevisorCelacanto/" + current}, timeout=25)
        if response.status_code == 404:
            return None
        if response.status_code == 403:
            raise UpdateError("O GitHub limitou a consulta de versões. Tente novamente mais tarde.")
        if not response.ok:
            raise UpdateError("Não foi possível consultar a versão publicada no GitHub.")
        return parse_release(response.json(), current)
    except requests.RequestException:
        raise UpdateError("Sem conexão com o GitHub. O programa e o banco local continuam disponíveis.") from None


def validate_package(archive, expected_digest):
    digest = hashlib.sha256()
    with Path(archive).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected_digest:
        raise UpdateError("O pacote baixado não passou na verificação de integridade.")
    try:
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > 2 * 1024 ** 3:
                raise UpdateError("O conteúdo do pacote excede os limites de atualização.")
            seen = set()
            for entry in entries:
                name = PurePosixPath(entry.filename.replace("\\", "/"))
                if name.is_absolute() or ".." in name.parts or ":" in str(name) or not name.parts or name.parts[0] != "RevisorCelacanto":
                    raise UpdateError("O pacote contém um caminho inesperado.")
                if any(part.rstrip(" .") != part or part.split(".", 1)[0].upper() in
                       {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
                       for part in name.parts):
                    raise UpdateError("O pacote contém um nome de arquivo não permitido no Windows.")
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise UpdateError("O pacote não pode conter links de arquivos.")
                lowered = str(name).lower()
                if lowered in seen:
                    raise UpdateError("O pacote contém caminhos duplicados.")
                seen.add(lowered)
            required = {"revisorcelacanto/revisorcelacanto.exe", "revisorcelacanto/_internal/python312.dll"}
            if not required.issubset(seen):
                raise UpdateError("O pacote Windows está incompleto.")
    except zipfile.BadZipFile:
        raise UpdateError("O pacote baixado não é um ZIP válido.") from None


def stage_update(release, updates_dir, progress=lambda _message: None, cancel=None):
    import requests
    root = Path(updates_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stage = root / (release.version + "-" + uuid.uuid4().hex[:10])
    stage.mkdir()
    archive = stage / "download.zip"
    total = 0
    try:
        with requests.get(release.url, stream=True, timeout=(15, 60)) as response:
            if not response.ok:
                raise UpdateError("Não foi possível baixar o pacote Windows.")
            host = urlsplit(response.url).hostname or ""
            if host != "github.com" and not host.endswith(".githubusercontent.com"):
                raise UpdateError("O download foi redirecionado para um destino não reconhecido.")
            with archive.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    if cancel and cancel.is_set():
                        raise UpdateError("Atualização cancelada. A versão instalada foi preservada.")
                    total += len(block)
                    if total > release.size or total > MAX_DOWNLOAD:
                        raise UpdateError("O download excedeu o tamanho informado pelo GitHub.")
                    stream.write(block)
                    progress(f"Baixando atualização: {total * 100 // release.size}%")
        if total != release.size:
            raise UpdateError("O download terminou incompleto.")
        validate_package(archive, release.sha256)
        progress("Pacote verificado. Preparando atualização…")
        # Todos os caminhos foram validados antes da extração.
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(stage)
        return stage / "RevisorCelacanto"
    except requests.RequestException:
        raise UpdateError("O download foi interrompido. A versão instalada não foi alterada.") from None


def ensure_target(target, source, data_dir):
    target, source, data_dir = Path(target).resolve(), Path(source).resolve(), Path(data_dir).resolve()
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()
    home = Path.home().resolve()
    if target == Path(target.anchor) or target == home or target == system or target.is_relative_to(system):
        raise UpdateError("A pasta de instalação selecionada não é permitida.")
    if target == source or source.is_relative_to(target) or target.is_relative_to(source):
        raise UpdateError("A pasta temporária e a instalação precisam estar separadas.")
    if data_dir == target or data_dir.is_relative_to(target):
        raise UpdateError("O banco local está dentro da instalação. Separe a biblioteca antes de atualizar automaticamente.")
    if not (target / EXE_NAME).is_file() or not (source / EXE_NAME).is_file():
        raise UpdateError("A pasta não contém o executável esperado.")
    return target, source, data_dir


def wait_for_process(pid, timeout=60):
    if not pid:
        return
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return
    try:
        if kernel.WaitForSingleObject(handle, timeout * 1000) != 0:
            raise UpdateError("O programa anterior não foi fechado a tempo. A instalação não foi alterada.")
    finally:
        kernel.CloseHandle(handle)


def apply_files(source, target, data_dir, verify=None, launcher=None):
    target, source, data_dir = ensure_target(target, source, data_dir)
    backup = source.parent / ("backup-" + uuid.uuid4().hex[:10])
    backup.mkdir()
    copied, created = [], []
    files = [p for p in source.rglob("*") if p.is_file()]
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise UpdateError("A pasta temporária contém um link inesperado.")
        destination = (target / path.relative_to(source)).resolve()
        if not destination.is_relative_to(target):
            raise UpdateError("Um destino está fora da pasta de instalação.")
    try:
        for path in files:
            relative = path.relative_to(source)
            destination = target / relative
            if destination.exists():
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, saved)
                copied.append(relative)
            else:
                created.append(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        if verify is None:
            with tempfile.TemporaryDirectory(dir=source.parent, prefix="verificacao-") as temporary:
                result = subprocess.run([str(target / EXE_NAME), "--smoke", "--data-dir", temporary], timeout=40)
                if result.returncode:
                    raise UpdateError("A nova versão não passou no teste de abertura.")
        else:
            verify(target)
    except Exception as error:
        for relative in copied:
            shutil.copy2(backup / relative, target / relative)
        for relative in created:
            path = (target / relative).resolve()
            if path.is_relative_to(target) and path.is_file():
                path.unlink()
        raise UpdateError("Atualização revertida; a versão anterior foi preservada. " + str(error)) from None
    if launcher:
        launcher(target, data_dir)
    else:
        subprocess.Popen([str(target / EXE_NAME), "--data-dir", str(data_dir)], cwd=target)
    return backup


def start_installer(staged, target, data_dir):
    target, staged, data_dir = ensure_target(target, staged, data_dir)
    probe = target / (".update-probe-" + uuid.uuid4().hex)
    try:
        probe.write_text("verificacao", encoding="utf-8")
        probe.unlink()
    except OSError:
        raise UpdateError("Sem permissão para atualizar esta pasta. Use uma pasta de programa gravável pelo seu usuário.") from None
    plan = staged.parent / "install-plan.json"
    plan.write_text(json.dumps({"source": str(staged), "target": str(target), "data_dir": str(data_dir),
                                "wait_pid": os.getpid()}), encoding="utf-8")
    subprocess.Popen([str(staged / EXE_NAME), "--apply-update", str(plan)], cwd=staged)


def apply_plan(path):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        wait_for_process(int(plan["wait_pid"]))
        backup = apply_files(plan["source"], plan["target"], plan["data_dir"], launcher=lambda _target, _data: None)
        result = {"success": True, "backup": str(backup)}
    except Exception as error:
        result = {"success": False, "message": str(error)}
    result["at"] = datetime.now(timezone.utc).isoformat()
    (Path(plan["data_dir"]) / "update-result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    subprocess.Popen([str(Path(plan["target"]) / EXE_NAME), "--data-dir", plan["data_dir"]], cwd=plan["target"])
    return 0 if result["success"] else 1
