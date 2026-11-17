from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StartupTests(unittest.TestCase):
    def test_window_opens_and_closes_cleanly_without_login(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run([sys.executable, "-m", "revisor", "--smoke", "--data-dir", root],
                cwd=Path(__file__).resolve().parent.parent, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
