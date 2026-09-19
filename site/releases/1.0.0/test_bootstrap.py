"""Offline installer integration tests; fake HTTPS downloads, no real tokens."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from test_accounts import AccountsTest

HERE = Path(__file__).resolve().parent
BOOTSTRAP = HERE / "cruxilion-codex.sh"


class BootstrapTest(unittest.TestCase):
    setUp = AccountsTest.setUp
    tearDown = AccountsTest.tearDown
    registry = AccountsTest.registry

    def prepare(self):
        curl = self.bin / "curl"
        curl.write_text(f"#!{sys.executable}\n" + '''import os, pathlib, sys
args = sys.argv[1:]
assert args[-1].startswith('https://install.cruxilion.com/')
assert args[args.index('--proto')+1] == '=https'
assert args[args.index('--proto-redir')+1] == '=https'
name = args[-1].rsplit('/', 1)[-1]
assert name in ('codex_accounts.py', 'cruxilion-codex.sh')
data = (pathlib.Path(os.environ['BOOTSTRAP_FIXTURES']) / name).read_bytes()
if os.environ.get('CORRUPT_DOWNLOAD') and name == 'codex_accounts.py':
    data += b'corrupted'
pathlib.Path(args[args.index('--output')+1]).write_bytes(data)
''')
        curl.chmod(0o755)
        self.env["BOOTSTRAP_FIXTURES"] = str(HERE)
        temp = self.home / "temps"
        temp.mkdir()
        self.env["TMPDIR"] = str(temp)

    def boot(self, *args, ok=True):
        r = subprocess.run(["/bin/sh", str(BOOTSTRAP), *args], env=self.env,
                           cwd=self.home, capture_output=True, text=True)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        else:
            self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(list((self.home / "temps").iterdir()), [])
        return r

    def test_install_reinstall_update_preserves_count(self):
        self.prepare()
        self.boot("--accounts", "3")
        before = self.registry()
        self.boot()
        self.boot("--update")
        self.assertEqual(self.registry(), before)
        self.boot("2", ok=False)
        self.assertEqual(self.registry(), before)
        installed = self.home / ".local/bin/cruxilion-codex.sh"
        self.assertTrue(os.access(installed, os.X_OK))

    def test_adopts_legacy_without_copying_tokens(self):
        self.prepare()
        for name in (".codex", ".codex-personal"):
            p = self.home / name
            p.mkdir()
            (p / "auth.json").write_text("TEST ONLY")
        self.boot()
        for n, name in (("1", ".codex"), ("2", ".codex-personal")):
            self.assertEqual(self.registry()["accounts"][n], str(self.home / name))
            self.assertEqual((self.home / name / "auth.json").read_text(), "TEST ONLY")

    def test_corrupt_download_and_unrelated_installer(self):
        self.prepare()
        self.env["CORRUPT_DOWNLOAD"] = "1"
        r = self.boot(ok=False)
        self.assertIn("checksum mismatch", r.stderr)
        self.assertFalse((self.home / ".config/codex-accounts/registry.json").exists())
        del self.env["CORRUPT_DOWNLOAD"]
        p = self.home / ".local/bin/cruxilion-codex.sh"
        p.parent.mkdir(parents=True)
        p.write_text("unrelated")
        self.boot(ok=False)
        self.assertEqual(p.read_text(), "unrelated")

    def test_missing_codex_installs_with_user_npm_prefix(self):
        self.prepare()
        code = (self.bin / "codex").read_text()
        (self.bin / "codex").unlink()
        (self.bin / "python3").symlink_to(sys.executable)
        self.env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.env["FAKE_CODEX_SOURCE"] = code
        npm = self.bin / "npm"
        npm.write_text(f"#!{sys.executable}\n" + '''import os, pathlib, sys
assert sys.argv[1:] == ['install', '--global', '--prefix', os.environ['HOME']+'/.local', '@openai/codex']
p = pathlib.Path.home()/'.local/bin/codex'
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(os.environ['FAKE_CODEX_SOURCE'])
p.chmod(0o755)
''')
        npm.chmod(0o755)
        self.boot("1")
        self.assertTrue((self.home / ".local/bin/codex").exists())


if __name__ == "__main__":
    unittest.main(defaultTest="BootstrapTest")
