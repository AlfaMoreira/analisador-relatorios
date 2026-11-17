"""Perfis imutáveis de critérios por cliente, contrato e versão."""
from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

FAMILIES = ("hidrogenio", "ar_comprimido_respiravel", "ar_ambiente", "desconhecida")


def validate_profile(data):
    if not isinstance(data, dict):
        raise ValueError("O perfil deve ser um objeto JSON.")
    data = json.loads(json.dumps(data, ensure_ascii=False))
    for key in ("client_id", "client_name", "contract", "family", "version", "valid_from", "status"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"Preencha {key} no perfil de critérios.")
        data[key] = data[key].strip()
    if data["family"] not in FAMILIES or data["status"] not in {"rascunho", "aprovado"}:
        raise ValueError("Família ou estado do perfil inválido.")
    try:
        start = date.fromisoformat(data["valid_from"])
        end = date.fromisoformat(data["valid_until"]) if data.get("valid_until") else None
    except (ValueError, TypeError):
        raise ValueError("Use datas de vigência no formato AAAA-MM-DD.") from None
    if end and end < start:
        raise ValueError("O fim da vigência é anterior ao início.")
    for key in ("approved_by", "critical_analysis", "valid_until"):
        if key in data and not isinstance(data[key], str):
            raise ValueError(f"O campo {key} deve ser texto.")
    if data["status"] == "aprovado" and not data.get("approved_by", "").strip():
        raise ValueError("Identifique o responsável pela aprovação do perfil.")
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 40:
        raise ValueError("Cadastre entre 1 e 40 critérios por perfil.")
    ids = set()
    for item in criteria:
        if not isinstance(item, dict):
            raise ValueError("Cada critério deve ser um objeto JSON.")
        for key in ("id", "parameter", "requirement", "source", "section", "applicability"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"Preencha {key} em cada critério.")
        if item["id"] in ids:
            raise ValueError("Identificadores de critérios repetidos.")
        ids.add(item["id"])
        if data["status"] == "aprovado" and any(item[k].startswith(("Descreva aqui", "Identifique ", "Descreva quando"))
                                               for k in ("requirement", "source", "section", "applicability")):
            raise ValueError("Substitua as orientações do modelo pelos critérios reais antes de aprovar.")
        if item.get("operator") and item["operator"] not in {">", ">=", "<", "<=", "=", "informativo"}:
            raise ValueError("Operador de critério inválido.")
        if item.get("operator") in {">", ">=", "<", "<=", "="}:
            from decimal import Decimal, InvalidOperation
            try:
                value = Decimal(str(item["limit"]))
                if not value.is_finite() or not str(item.get("unit", "")).strip():
                    raise ValueError()
            except (KeyError, ValueError, InvalidOperation):
                raise ValueError("Critério numérico exige limite decimal finito e unidade. Use ponto decimal no JSON.") from None
    if len(json.dumps(data, ensure_ascii=False)) > 24000:
        raise ValueError("Perfil excede o limite de 24 mil caracteres; divida por escopo.")
    return data


class ProfileStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, identity TEXT UNIQUE, data TEXT, created TEXT)")
            db.commit()

    def save(self, data):
        data = validate_profile(data)
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        identity = json.dumps([data[k] for k in ("client_id", "contract", "family", "version")])
        with closing(sqlite3.connect(self.path)) as db:
            old = db.execute("SELECT id FROM profiles WHERE identity=?", (identity,)).fetchone()
            if old and old[0] != digest:
                raise ValueError("Esta versão já existe. Crie uma nova versão para preservar o histórico, inclusive ao aprovar rascunhos.")
            db.execute("INSERT OR IGNORE INTO profiles VALUES(?,?,?,?)", (digest, identity, payload, datetime.now(timezone.utc).isoformat()))
            db.commit()
        return digest

    def list(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [dict(json.loads(row[1]), profile_id=row[0]) for row in
                    db.execute("SELECT id,data FROM profiles ORDER BY created DESC")]


def applicable(profile, client_id, contract, family, reference_date):
    if not profile:
        return
    if profile["client_id"] != client_id or profile["contract"] != contract or profile["family"] != family:
        raise ValueError("O perfil não corresponde ao cliente, contrato ou família selecionados.")
    if profile["status"] != "aprovado":
        raise ValueError("O perfil é rascunho. Aprove uma nova versão antes de usar na revisão.")
    day = date.fromisoformat(reference_date)
    if day < date.fromisoformat(profile["valid_from"]) or (profile.get("valid_until") and day > date.fromisoformat(profile["valid_until"])):
        raise ValueError("O perfil não está vigente na data de referência informada.")


def load_skill(family):
    root = Path(__file__).parent / "skills" / "revisar-relatorios"
    paths = [root / "SKILL.md"]
    if family in FAMILIES and family != "desconhecida":
        paths.append(root / "references" / (family + ".md"))
    contents = [(p.relative_to(root).as_posix(), p.read_text(encoding="utf-8")) for p in paths]
    digest = hashlib.sha256(json.dumps(contents, ensure_ascii=False).encode()).hexdigest()
    return {"name": "revisar-relatorios", "version": "1.0.0", "sha256": digest,
            "files": [p for p, _ in contents], "instructions": "\n\n".join(t for _, t in contents)}
