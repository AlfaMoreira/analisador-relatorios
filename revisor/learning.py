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
    return [{"family": review.family, "rule": f.rule, "title": f.title,
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
            db.commit()

    def contribute(self, review):
        examples = confirmed_examples(review)
        if not examples:
            raise ValueError("Informe o revisor e confirme os apontamentos com justificativa antes de contribuir para a base local.")
        with closing(sqlite3.connect(self.path)) as db:
            for example in examples:
                key = hashlib.sha256(f"{example['source_sha256']}|{example['rule']}|{example['title']}|{example['page']}".encode()).hexdigest()
                db.execute("INSERT OR REPLACE INTO examples VALUES(?,?,?,?)", (key, review.family,
                    json.dumps(example, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
            db.commit()
        return len(examples)

    def examples(self, family, limit=8):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute("SELECT data FROM examples WHERE family=? ORDER BY updated DESC LIMIT ?", (family, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def export(self, review, path):
        from .export import protect_originals
        protect_originals(review, path)
        payload = {"schema": "celacanto.contribuicoes.v1", "family": review.family,
                   "automatic_model_training": False, "confirmed_examples": confirmed_examples(review),
                   "review": review.to_dict()}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return Path(path)
