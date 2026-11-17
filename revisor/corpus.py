"""Biblioteca local; importar não envia dados nem treina modelos."""
import base64
import hashlib
import io
import sqlite3
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import pymupdf
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".heic"}
MAX_FILE = 100 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Corpus:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, name TEXT, digest TEXT UNIQUE, path TEXT)")

    @contextmanager
    def connect(self):
        database = sqlite3.connect(self.root / "catalogo.sqlite3")
        try:
            with database:
                yield database
        finally:
            database.close()

    def entries(self):
        with self.connect() as db:
            return db.execute("SELECT id, name, digest, path FROM files ORDER BY name").fetchall()

    def add_bytes(self, name, content):
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED or len(content) > MAX_FILE:
            raise ValueError("Formato não suportado ou arquivo acima de 100 MB.")
        digest = hashlib.sha256(content).hexdigest()
        target = self.root / (digest + suffix)
        if not target.exists():
            target.write_bytes(content)
        elif sha256(target) != digest:
            raise ValueError("Integridade da cópia local comprometida.")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO files(name,digest,path) VALUES(?,?,?)", (name, digest, str(target)))
        return digest

    def import_file(self, path):
        path = Path(path)
        if path.suffix.lower() != ".zip":
            if path.stat().st_size > MAX_FILE:
                raise ValueError("Arquivo acima de 100 MB.")
            return [self.add_bytes(path.name, path.read_bytes())]
        # Não extrai caminhos do ZIP; o destino é sempre o hash do conteúdo.
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > 1024 ** 3:
                raise ValueError("ZIP excede o limite de 2000 entradas ou 1 GB descompactado.")
            candidates = []
            for info in infos:
                name = PurePosixPath(info.filename.replace("\\", "/"))
                if info.is_dir() or name.suffix.lower() not in SUPPORTED:
                    continue
                if name.is_absolute() or ".." in name.parts or ":" in str(name):
                    raise ValueError("ZIP contém caminho inseguro.")
                if info.file_size > MAX_FILE or info.flag_bits & 1:
                    raise ValueError("ZIP contém arquivo grande demais ou criptografado.")
                candidates.append(info)
            return [self.add_bytes(PurePosixPath(info.filename).name, archive.read(info)) for info in candidates]


def prepare(entry, page=1):
    """Produz uma página/uma imagem. Nunca inclui páginas adjacentes."""
    _id, name, digest, path = entry
    if sha256(path) != digest:
        raise ValueError("O hash do arquivo não confere com o catálogo.")
    if Path(path).suffix == ".pdf":
        with pymupdf.open(path) as document:
            if not 1 <= page <= len(document):
                raise ValueError(f"Página inválida: o PDF tem {len(document)} páginas.")
            pixmap = document[page - 1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    else:
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
        page = 1
    image.thumbnail((2400, 2400))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90)
    return {"name": name, "sha256": digest, "page": page,
            "data": "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()}
