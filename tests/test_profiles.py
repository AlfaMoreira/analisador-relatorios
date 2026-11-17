import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import json
from revisor.profiles import ProfileStore, validate_profile, applicable, load_skill
from revisor.context import prepare_context, snapshot
from revisor.learning import ExampleStore
from revisor.review import Review, Finding, analyze_pages, compare_reviews
from revisor.ai import review_packet


def profile(client="cliente-a"):
    return {"client_id": client, "client_name": "Cliente sintético", "contract": "escopo-1", "family": "hidrogenio",
            "version": "1", "status": "aprovado", "approved_by": "Revisor de teste", "valid_from": "2026-01-01",
            "valid_until": "2026-12-31", "criteria": [{"id": "P-01", "parameter": "Pureza",
            "requirement": "Confrontar o limite acordado", "source": "Contrato sintético v1", "section": "2",
            "applicability": "Ensaio sintético", "operator": ">=", "limit": "99.9", "unit": "%"}]}


def packet():
    return {"documents": [{"id": "D1", "name": "sintetico.pdf", "sha256": "a", "path": "unused", "kind": "pdf", "pages": 1}],
            "pages": [{"document": "D1", "name": "sintetico.pdf", "sha256": "a", "page": 1,
                       "text": "Relatorio de Hidrogenio. Pureza e unidade do resultado."}]}


def scope(client="cliente-a"):
    return {"client_id": client, "contract": "escopo-1", "family": "hidrogenio", "reference_date": "2026-11-17"}


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_immutable_profile_and_new_version_preserve_previous(self):
        store = ProfileStore(self.root / "criteria.sqlite3")
        original = profile()
        first = store.save(original)
        self.assertEqual(store.save(original), first)
        changed = copy.deepcopy(original)
        changed["criteria"][0]["limit"] = "99.95"
        with self.assertRaises(ValueError):
            store.save(changed)
        changed["version"] = "2"
        store.save(changed)
        self.assertEqual(len(store.list()), 2)
        self.assertEqual(next(p for p in store.list() if p["version"] == "1")["criteria"][0]["limit"], "99.9")

    def test_profile_requires_source_approval_and_finite_numeric_limit(self):
        for mutate in (lambda p: p.update(approved_by=""), lambda p: p["criteria"][0].update(source=""),
                       lambda p: p["criteria"][0].update(limit="NaN"), lambda p: p["criteria"][0].update(unit="")):
            p = profile()
            mutate(p)
            with self.assertRaises(ValueError):
                validate_profile(p)

    def test_wrong_client_contract_family_date_and_draft_rejected(self):
        for args in [("cliente-b", "escopo-1", "hidrogenio", "2026-11-17"),
                     ("cliente-a", "outro", "hidrogenio", "2026-11-17"),
                     ("cliente-a", "escopo-1", "ar_ambiente", "2026-11-17"),
                     ("cliente-a", "escopo-1", "hidrogenio", "2027-01-01")]:
            with self.assertRaises(ValueError):
                applicable(profile(), *args)
        p = profile()
        p["status"] = "rascunho"
        with self.assertRaises(ValueError):
            applicable(p, "cliente-a", "escopo-1", "hidrogenio", "2026-11-17")

    def test_examples_isolate_clients_contracts_and_legacy_records(self):
        store = ExampleStore(self.root / "examples.sqlite3")
        for client, contract in [("cliente-a", "escopo-1"), ("cliente-b", "escopo-1"), ("cliente-a", "outro"), ("", "")]:
            r = analyze_pages(["Relatorio de Hidrogenio " * 8])
            r.client_id, r.contract = client, contract
            r.findings = [Finding("f", "TXT-01", "alerta", "Conferir pureza", 1, "Pureza", "Conferir unidade")]
            r.decide("f", "corrigir", "Unidade confirmada", "Revisor")
            store.contribute(r)
        matches = store.examples("hidrogenio", client_id="cliente-a", contract="escopo-1")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["client_id"], "cliente-a")
        self.assertEqual(len(store.examples("hidrogenio")), 1)

    def test_context_does_not_send_legacy_or_other_client_examples(self):
        examples = ExampleStore(self.root / "examples.sqlite3")
        prepared = prepare_context(packet(), scope(), profile(), examples)
        self.assertEqual(prepared["examples"], [])
        self.assertIn("hidrogenio.md", " ".join(prepared["skill"]["files"]))
        record = snapshot(prepared)
        self.assertNotIn("instructions", record["skill"])
        self.assertNotIn("text", record["pages"][0])
        self.assertEqual(record["criteria_profile"]["criteria"][0]["limit"], "99.9")

    def test_old_sqlite_schema_is_migrated_without_losing_examples(self):
        import sqlite3
        from contextlib import closing
        path = self.root / "legacy.sqlite3"
        example = {"family": "hidrogenio", "rule": "TXT-01", "title": "Exemplo antigo", "decision": "corrigir",
                   "comment": "Confirmado", "evidence": "Texto", "expected": "Conferir"}
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE examples (id TEXT PRIMARY KEY,family TEXT,data TEXT,updated TEXT)")
            db.execute("INSERT INTO examples VALUES(?,?,?,?)", ("old", "hidrogenio", json.dumps(example), "2026-01-01"))
            db.commit()
        store = ExampleStore(path)
        self.assertEqual(store.examples("hidrogenio")[0]["title"], "Exemplo antigo")
        self.assertEqual(store.examples("hidrogenio", client_id="cliente-a"), [])
        self.assertEqual(len(ExampleStore(path).examples("hidrogenio")), 1)

    def test_context_keeps_conflicting_criteria_and_does_not_invent_resolution(self):
        p = profile()
        p["criteria"].append(dict(p["criteria"][0], id="P-02", limit="99.99"))
        prepared = prepare_context(packet(), scope(), p)
        with patch("revisor.ai.analyze", return_value='{"achados": []}') as infer:
            review_packet(MagicMock(), "test-model", prepared)
        prompt = infer.call_args.args[2]
        self.assertIn("P-01", prompt)
        self.assertIn("P-02", prompt)
        self.assertIn("decisão humana", prompt)

    def test_skill_family_routing_and_hash_changes_when_reference_changes(self):
        hydrogen = load_skill("hidrogenio")
        ambient = load_skill("ar_ambiente")
        self.assertNotEqual(hydrogen["sha256"], ambient["sha256"])
        self.assertEqual(len(hydrogen["files"]), 2)
        self.assertNotIn("ar_ambiente.md", " ".join(hydrogen["files"]))

    def test_ai_audit_distinguishes_attempted_and_completed_batches_on_failure(self):
        from revisor.auth import AuthError
        prepared = prepare_context(packet(), scope(), profile())
        prepared["pages"] = [dict(prepared["pages"][0], page=i + 1, image="data:image/jpeg;base64,eA==") for i in range(5)]
        prepared["documents"][0]["pages"] = 5
        with patch("revisor.ai.analyze", side_effect=['{"achados": []}', AuthError("Falha de teste")]):
            with self.assertRaises(AuthError):
                review_packet(MagicMock(), "test-model", prepared)
        execution = snapshot(prepared)["ai_execution"]
        self.assertEqual(len(execution["attempted"]), 2)
        self.assertEqual(len(execution["completed"]), 1)
        self.assertEqual(execution["completed"][0]["pages"][-1]["page"], 4)

    def test_old_reviews_load_and_new_context_roundtrips(self):
        review = analyze_pages(["Relatorio de Hidrogenio " * 8])
        old = review.to_dict()
        for key in ("client_id", "contract", "review_context"):
            old.pop(key)
        self.assertEqual(Review.from_dict(old).client_id, "")
        review.review_context = snapshot(prepare_context(packet(), scope(), profile()))
        self.assertEqual(Review.from_dict(json.loads(json.dumps(review.to_dict()))).review_context, review.review_context)

    def test_comparison_rejects_other_client_and_requires_explicit_correction(self):
        old = analyze_pages(["Relatorio de Hidrogenio " * 8])
        new = analyze_pages(["Relatorio de Hidrogenio " * 8])
        old.client_id, new.client_id = "cliente-a", "cliente-b"
        old.findings = [Finding("f", "TXT-01", "alerta", "Conferir dado", 1, "Evidência", "Conferir", tracked=True)]
        with self.assertRaises(ValueError):
            compare_reviews(old, new)
        new.client_id = old.client_id
        new.comparison = compare_reviews(old, new)
        self.assertEqual(new.comparison["items"][0]["state"], "nao_redetectado")
        new.documents = [{"sha256": "new", "pages": 1}]
        with self.assertRaises(ValueError):
            new.confirm_correction("f", "Revisor", "", "new", 1)
        with self.assertRaises(ValueError):
            new.confirm_correction("f", "Revisor", "Conferido", "old", 1)
        new.confirm_correction("f", "Revisor", "Conferido na versão corrigida", "new", 1)
        self.assertEqual(compare_reviews(old, new)["items"][0]["state"], "correcao_confirmada")


if __name__ == "__main__":
    unittest.main()
