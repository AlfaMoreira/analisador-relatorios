import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from release_windows import package_release
from installer.build_installer import build


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = self.root / "RevisorCelacanto"
        (self.package / "_internal").mkdir(parents=True)
        (self.package / "RevisorCelacanto.exe").write_bytes(b"synthetic application")
        (self.package / "_internal" / "python312.dll").write_bytes(b"synthetic runtime")

    def tearDown(self):
        self.temp.cleanup()

    def test_release_publishes_two_assets_with_independent_checksums(self):
        (self.root / "RevisorCelacanto-Instalador.exe").write_bytes(b"synthetic installer")
        archive, installer, checksum = package_release(self.root)
        entries = [line.split("  ") for line in checksum.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({name for _, name in entries}, {archive.name, installer.name})
        for digest, name in entries:
            self.assertEqual(digest, hashlib.sha256((self.root / name).read_bytes()).hexdigest())
        with zipfile.ZipFile(archive) as zipped:
            self.assertIn("RevisorCelacanto/RevisorCelacanto.exe", zipped.namelist())
            self.assertNotIn(installer.name, zipped.namelist())

    def test_release_refuses_missing_installer(self):
        with self.assertRaises(ValueError):
            package_release(self.root)

    def test_build_checks_runtime_and_compiler_before_running(self):
        compiler = self.root / "compiler.exe"
        with patch("installer.build_installer.subprocess.run") as compile_process:
            with self.assertRaises(ValueError):
                build(self.root, compiler)
            compile_process.assert_not_called()
            compiler.touch()
            (self.package / "_internal" / "python312.dll").unlink()
            with self.assertRaises(ValueError):
                build(self.root, compiler)
            compile_process.assert_not_called()

    def test_compiler_receives_paths_as_distinct_arguments(self):
        compiler = self.root / "compiler with spaces.exe"
        compiler.touch()
        def compile_stub(command, check):
            self.assertEqual(command[0], str(compiler))
            self.assertIn("/DPackageDir=" + str(self.root.resolve() / "RevisorCelacanto"), command)
            (self.root / "RevisorCelacanto-Instalador.exe").write_bytes(b"compiled")
        with patch("installer.build_installer.subprocess.run", side_effect=compile_stub):
            self.assertTrue(build(self.root, compiler).is_file())
