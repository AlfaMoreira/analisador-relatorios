"""Exemplos confirmados, locais; contribuição não ajusta pesos do ChatGPT."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone


def confirmed_examples(review):
    if not review.reviewer.strip():
        return []
    return [{"client_id": review.client_id, "contract": review.contract,
             "family": review.family, "rule": f.rule, "title": f.title,
             "evidence": f.evidence, "expected": f.expected, "comment": f.comment,
             "decision": f.decision, "reviewer": review.reviewer,
             "source_sha256": f.document_sha256 or review.source["sha256"], "page": f.page}
            for f in review.findings if f.decision in {"aceito", "corrigir", "falso_positivo"} and f.comment.strip()]


class ExampleStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS examples (id TEXT PRIMARY KEY, family TEXT, data TEXT, updated TEXT)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(examples)")}
            migrating = "client_id" not in columns or "contract" not in columns
            for column in ("client_id", "contract"):
                if column not in columns:
                    db.execute(f"ALTER TABLE examples ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            if migrating:
                for key, raw in db.execute("SELECT id,data FROM examples").fetchall():
                    example = json.loads(raw)
                    db.execute("UPDATE examples SET client_id=?,contract=? WHERE id=?",
                               (example.get("client_id", ""), example.get("contract", ""), key))
            db.execute("CREATE INDEX IF NOT EXISTS examples_scope ON examples(family,client_id,contract,updated)")
            db.commit()

    def contribute(self, review):
        examples = confirmed_examples(review)
        if not examples:
            raise ValueError("Informe o revisor e confirme os apontamentos com justificativa antes de contribuir para a base local.")
        with closing(sqlite3.connect(self.path)) as db:
            for example in examples:
                key = hashlib.sha256(f"{review.client_id}|{review.contract}|{example['source_sha256']}|{example['rule']}|{example['title']}|{example['page']}".encode()).hexdigest()
                db.execute("INSERT OR REPLACE INTO examples(id,family,data,updated,client_id,contract) VALUES(?,?,?,?,?,?)", (key, review.family,
                    json.dumps(example, ensure_ascii=False), datetime.now(timezone.utc).isoformat(), review.client_id, review.contract))
            db.commit()
        return len(examples)

    def examples(self, family, limit=8, client_id="", contract="", query=""):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT data FROM examples WHERE family=? AND client_id=? AND contract=? ORDER BY updated DESC",
                              (family, client_id, contract)).fetchall()
        from .review import normalized
        import re
        tokens = set(re.findall(r"\w{4,}", normalized(query)))
        selected, seen = [], set()
        for row in rows:
            example = json.loads(row[0])
            if example.get("client_id", "") != client_id or example.get("contract", "") != contract:
                continue
            fingerprint = (example["rule"], normalized(example["title"]), example["decision"], example["comment"])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            content = normalized(" ".join(str(example.get(k, "")) for k in ("title", "evidence", "expected", "comment")))
            score = len(tokens & set(re.findall(r"\w{4,}", content)))
            selected.append((score, example))
        selected.sort(key=lambda item: -item[0])
        return [e for _, e in selected[:limit]]

    def export(self, review, path):
        from .export import protect_originals
        protect_originals(review, path)
        payload = {"schema": "celacanto.contribuicoes.v1", "family": review.family,
                   "automatic_model_training": False, "confirmed_examples": confirmed_examples(review),
                   "review": review.to_dict()}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return Path(path)
