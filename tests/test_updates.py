import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from revisor.updates import (ASSET_NAME, Release, UpdateError, apply_files, check_update,
    ensure_target, parse_release, stage_update, validate_package, version_tuple)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def metadata(self):
        return {"tag_name": "v1.2.0", "draft": False, "prerelease": False, "body": "Nova versão",
                "assets": [{"name": ASSET_NAME, "size": 123, "digest": "sha256:" + "a" * 64,
                "browser_download_url": "https://github.com/AlfaMoreira/analisador-relatorios/releases/download/v1.2.0/" + ASSET_NAME}]}

    def archive(self, extras=None):
        path = self.root / "release.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("RevisorCelacanto/RevisorCelacanto.exe", b"test-executable")
            archive.writestr("RevisorCelacanto/_internal/python312.dll", b"test-runtime")
            for name, value in (extras or {}).items():
                archive.writestr(name, value)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_stable_semantic_version_order(self):
        self.assertGreater(version_tuple("v1.10.0"), version_tuple("1.9.9"))
        with self.assertRaises(UpdateError):
            version_tuple("latest")

    def test_new_release_and_older_version(self):
        self.assertEqual(parse_release(self.metadata(), "1.1.0").version, "1.2.0")
        self.assertIsNone(parse_release(self.metadata(), "1.2.0"))

    def test_untrusted_download_and_missing_digest_rejected(self):
        data = self.metadata()
        data["assets"][0]["browser_download_url"] = "https://other.example/release.zip"
        with self.assertRaises(UpdateError):
            parse_release(data, "1.0.0")
        data = self.metadata()
        data["assets"][0].pop("digest")
        with self.assertRaises(UpdateError):
            parse_release(data, "1.0.0")

    def test_no_published_release_does_not_break_application(self):
        with patch("requests.get", return_value=MagicMock(status_code=404)):
            self.assertIsNone(check_update())

    def test_valid_archive_and_corrupted_hash(self):
        archive, digest = self.archive()
        validate_package(archive, digest)
        with self.assertRaises(UpdateError):
            validate_package(archive, "0" * 64)

    def test_zip_traversal_and_windows_path_tricks_rejected(self):
        for name in ["../escape.exe", "RevisorCelacanto/../escape.exe", "RevisorCelacanto/.. /escape.exe", "RevisorCelacanto/CON.txt"]:
            archive, digest = self.archive({name: b"bad"})
            with self.subTest(name=name), self.assertRaises(UpdateError):
                validate_package(archive, digest)

    def test_download_checks_hash_and_stages_without_installing(self):
        archive, digest = self.archive()
        payload = archive.read_bytes()
        release = Release("1.2.0", "https://github.com/AlfaMoreira/analisador-relatorios/releases/download/v1.2.0/" + ASSET_NAME,
                          digest, len(payload), "Notas")
        response = MagicMock(ok=True, url="https://release-assets.githubusercontent.com/test")
        response.iter_content.return_value = [payload]
        response.__enter__.return_value = response
        with patch("requests.get", return_value=response):
            staged = stage_update(release, self.root / "updates")
        self.assertEqual((staged / "RevisorCelacanto.exe").read_bytes(), b"test-executable")

    def installation(self):
        source = self.root / "stage" / "RevisorCelacanto"
        target = self.root / "program" / "RevisorCelacanto"
        data = self.root / "data"
        for directory in (source, target, data):
            directory.mkdir(parents=True)
        (source / "RevisorCelacanto.exe").write_bytes(b"new")
        (target / "RevisorCelacanto.exe").write_bytes(b"old")
        (source / "new.dll").write_bytes(b"new-library")
        (data / "credentials.dpapi").write_bytes(b"protected-credentials")
        (data / "history.sqlite3").write_bytes(b"local-history")
        return source, target, data

    def test_apply_preserves_user_data_and_backups_previous_version(self):
        source, target, data = self.installation()
        launcher = MagicMock()
        backup = apply_files(source, target, data, verify=lambda _target: None, launcher=launcher)
        self.assertEqual((target / "RevisorCelacanto.exe").read_bytes(), b"new")
        self.assertEqual((backup / "RevisorCelacanto.exe").read_bytes(), b"old")
        self.assertEqual((data / "credentials.dpapi").read_bytes(), b"protected-credentials")
        self.assertEqual((data / "history.sqlite3").read_bytes(), b"local-history")
        launcher.assert_called_once()

    def test_failed_startup_rolls_back_only_application_files(self):
        source, target, data = self.installation()
        def fail(_target):
            raise RuntimeError("Falha simulada de abertura")
        with self.assertRaises(UpdateError):
            apply_files(source, target, data, verify=fail, launcher=MagicMock())
        self.assertEqual((target / "RevisorCelacanto.exe").read_bytes(), b"old")
        self.assertFalse((target / "new.dll").exists())
        self.assertEqual((data / "history.sqlite3").read_bytes(), b"local-history")

    def test_data_inside_program_directory_blocks_automatic_replacement(self):
        source, target, data = self.installation()
        with self.assertRaises(UpdateError):
            ensure_target(target, source, target / "dados")


if __name__ == "__main__":
    unittest.main()
