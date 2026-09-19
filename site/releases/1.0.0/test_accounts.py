"""Offline integration tests: never use a real auth file or real Codex process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).with_name("codex_accounts.py")


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex accounts '")
        self.home = Path(self.temp.name).resolve()
        self.bin = self.home / "mock-bin"
        self.bin.mkdir()
        mock = self.bin / "codex"
        mock.write_text(f"#!{sys.executable}\nimport os,sys,json\n"
                        "print(json.dumps({'home':os.environ['CODEX_HOME'],"
                        "'args':sys.argv[1:],'cwd':os.getcwd()}))\n"
                        "sys.exit(7 if '--test-exit' in sys.argv else 0)\n")
        mock.chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": "/wrong",
                    "PATH": f"{self.home}/.local/bin:{self.bin}:" + os.environ["PATH"]}

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SOURCE), *args], env=self.env,
                                cwd=self.home, text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def registry(self):
        return json.loads((self.home / ".config/codex-accounts/registry.json").read_text())

    def test_fresh_launch_login_args_cwd_exit_and_isolation(self):
        self.cli("install", "--accounts", "2")
        for n in (1, 2):
            command = self.home / f".local/bin/codex{n}"
            args = ["login", "--device-auth", 'space $HOME " quote', "中文"]
            r = subprocess.run([str(command), *args], env=self.env, cwd=self.home,
                               text=True, capture_output=True)
            data = json.loads(r.stdout)
            self.assertEqual(data["args"], args)
            self.assertEqual(data["home"], self.registry()["accounts"][str(n)])
            self.assertEqual(data["cwd"], str(self.home))
            self.assertFalse((Path(data["home"]) / "auth.json").exists())
            self.assertIn('trust_level = "untrusted"',
                          (Path(data["home"]) / "config.toml").read_text())
        r = subprocess.run([str(command), "--test-exit"], env=self.env, capture_output=True)
        self.assertEqual(r.returncode, 7)

    def test_adopt_reinstall_add_keep_config_and_auth(self):
        legacy = self.home / ".codex"
        legacy.mkdir()
        (legacy / "config.toml").write_text('model = "existing"\n')
        (legacy / "auth.json").write_text("FAKE TEST AUTH")
        custom = self.home / "custom-base"
        self.cli("install", "--accounts", "2", "--adopt", f"1={legacy}",
                 "--home-base", str(custom))
        original = self.registry()
        self.cli("install", "--accounts", "2")
        self.assertEqual(self.registry(), original)
        self.cli("add")
        self.assertEqual(self.registry()["accounts"]["3"], str(custom / "account-3"))
        self.assertEqual((legacy / "auth.json").read_text(), "FAKE TEST AUTH")
        self.assertEqual((legacy / "config.toml").read_text(), 'model = "existing"\n')
        self.cli("install", "--accounts", "2", ok=False)
        self.assertEqual(len(self.registry()["accounts"]), 3)

    def test_conflict_preflight_no_partial_install(self):
        target = self.home / ".local/bin/codex2"
        target.parent.mkdir(parents=True)
        target.write_text("unrelated file")
        self.cli("install", "--accounts", "2", ok=False)
        self.assertEqual(target.read_text(), "unrelated file")
        self.assertFalse(target.with_name("codex1").exists())
        self.assertFalse((self.home / ".local/lib/codex-accounts/manager.py").exists())

    def test_conflict_add_preserves_registry(self):
        self.cli("install", "--accounts", "1")
        old = self.registry()
        (self.home / ".local/bin/codex2").write_text("unrelated")
        self.cli("add", ok=False)
        self.assertEqual(self.registry(), old)

    def test_ancestor_conflict_and_reserved_home_preflight(self):
        target = self.home / ".local/bin"
        target.parent.mkdir()
        target.write_text("not a directory")
        self.cli("install", "--accounts", "2", ok=False)
        self.assertFalse((self.home / ".local/lib/codex-accounts/manager.py").exists())
        self.assertFalse((self.home / ".local/share/codex-accounts/account-1").exists())
        target.unlink()
        target.mkdir()
        self.cli("install", "--accounts", "1", "--adopt", f"1={target}", ok=False)
        self.assertFalse((self.home / ".local/lib/codex-accounts/manager.py").exists())

    def test_reject_duplicate_nested_and_remapped_homes(self):
        a = self.home / "a"
        (a / "child").mkdir(parents=True)
        for b in (a, a / "child"):
            self.cli("install", "--accounts", "2", "--adopt", f"1={a}",
                     "--adopt", f"2={b}", ok=False)
        self.cli("install", "--accounts", "1", "--adopt", f"1={a}")
        other = self.home / "other"
        other.mkdir()
        self.cli("install", "--accounts", "1", "--adopt", f"1={other}", ok=False)
        self.assertEqual(self.registry()["accounts"]["1"], str(a))

    def test_dangling_parent_preflight(self):
        target = self.home / ".local/bin"
        target.parent.mkdir()
        target.symlink_to(self.home / "missing-bin", target_is_directory=True)
        self.cli("install", "--accounts", "2", ok=False)
        self.assertFalse((self.home / ".local/lib/codex-accounts/manager.py").exists())
        self.assertFalse((self.home / ".local/share/codex-accounts/account-1").exists())

    def test_shell_setup_preserves_login_profile_and_is_idempotent(self):
        profile = self.home / ".profile"
        profile.write_text("export KEEP_EXISTING=yes\n")
        self.cli("install", "--accounts", "1", "--shell-setup")
        first = profile.read_text()
        self.cli("install", "--accounts", "1", "--shell-setup")
        self.assertEqual(first, profile.read_text())
        self.assertFalse((self.home / ".bash_profile").exists())
        self.assertEqual((self.home / ".profile.before-codex-accounts").read_text(),
                         "export KEEP_EXISTING=yes\n")
        subprocess.run(["/bin/sh", "-n", str(profile)], check=True)

    def test_unknown_number_bad_count_and_symlink_conflict(self):
        for count in ("0", "100", "01", "-1"):
            self.cli("install", "--accounts", count, ok=False)
        target = self.home / ".local/bin/codex1"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.home / "missing")
        self.cli("install", "--accounts", "1", ok=False)
        self.assertTrue(target.is_symlink())


if __name__ == "__main__":
    unittest.main()
