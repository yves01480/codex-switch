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

    def account(self, number):
        return self.registry()["accounts"][str(number)]

    def test_fresh_launch_login_args_cwd_exit_and_isolation(self):
        self.cli("install", "--accounts", "2")
        for n in (1, 2):
            command = self.home / f".local/bin/codex{n}"
            args = ["login", "--device-auth", 'space $HOME " quote', "中文"]
            r = subprocess.run([str(command), *args], env=self.env, cwd=self.home,
                               text=True, capture_output=True)
            data = json.loads(r.stdout)
            self.assertEqual(data["args"], args)
            self.assertEqual(data["home"], self.account(n)["home"])
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
        self.assertEqual(self.account(3)["home"], str(custom / "account-3"))
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
        self.assertEqual(self.account(1)["home"], str(a))

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

    def test_add_status_and_label_keep_auth_private(self):
        self.cli("install", "--accounts", "2")
        self.cli("add", "codex3", "third@example.com")
        profile = self.account(3)
        self.assertEqual(profile["expected_email"], "third@example.com")
        self.assertEqual(profile["origin"], "manager-created")
        self.assertTrue(profile["enabled"])
        self.assertTrue((Path(profile["home"]) / ".codex-accounts-managed").is_file())
        self.cli("add", "codex2", ok=False)
        self.cli("add", "codex5", ok=False)
        self.cli("add", "codex4", "bad email", ok=False)
        self.cli("label", "codex1", "first@example.com")
        status = self.cli("status")
        self.assertIn("codex1\tenabled\texpected: first@example.com", status.stdout)
        self.assertIn("codex3\tenabled\texpected: third@example.com", status.stdout)
        self.assertIn('"args": ["login", "status"]', status.stdout)
        self.assertNotIn("auth.json", status.stdout)

    def test_codex_switch_alias_uses_the_same_manager(self):
        self.cli("install", "--accounts", "1")
        switch = self.home / ".local/bin/codex-switch"
        self.assertTrue(os.access(switch, os.X_OK))
        result = subprocess.run([str(switch), "status", "codex1"], env=self.env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("codex1\tenabled", result.stdout)

    def test_remove_enable_and_purge_manager_created_profile(self):
        self.cli("install", "--accounts", "1")
        home = Path(self.account(1)["home"])
        launcher = self.home / ".local/bin/codex1"
        self.cli("remove", "codex1")
        self.assertFalse(self.account(1)["enabled"])
        self.assertTrue(home.is_dir())
        self.assertTrue(launcher.exists())
        self.cli("run", "codex1", "--version", ok=False)
        disabled = self.cli("status", "1")
        self.assertIn("codex1\tdisabled", disabled.stdout)
        self.cli("enable", "1")
        self.assertTrue(self.account(1)["enabled"])
        self.cli("del", "1")
        self.cli("purge", "codex1", ok=False)
        self.assertTrue(home.is_dir())
        self.cli("purge", "codex1", "--yes")
        self.assertFalse(home.exists())
        self.assertFalse(launcher.exists())
        self.assertEqual(self.registry()["accounts"], {})

    def test_purge_rejects_adopted_and_migrated_legacy_profiles(self):
        adopted = self.home / "adopted"
        adopted.mkdir()
        self.cli("install", "--accounts", "1", "--adopt", f"1={adopted}")
        self.cli("remove", "1")
        self.cli("purge", "1", "--yes", ok=False)
        self.assertTrue(adopted.is_dir())

        legacy_home = self.home / "legacy"
        legacy_home.mkdir()
        registry = self.home / ".config/codex-accounts/registry.json"
        registry.write_text(json.dumps({
            "version": 1,
            "home_base": str(self.home / "profiles"),
            "accounts": {"1": str(legacy_home)},
        }))
        self.cli("remove", "1")
        migrated = self.account(1)
        self.assertEqual(self.registry()["version"], 2)
        self.assertEqual(migrated["origin"], "legacy-unknown")
        self.cli("purge", "1", "--yes", ok=False)
        self.assertTrue(legacy_home.is_dir())

    def test_install_refuses_to_claim_an_unregistered_existing_default_home(self):
        existing = self.home / ".local/share/codex-accounts/account-1"
        existing.mkdir(parents=True)
        sentinel = existing / "keep-me"
        sentinel.write_text("unrelated data")
        marker = existing / ".codex-accounts-managed"
        marker.write_text(json.dumps({"profile": "1", "version": 1}))
        self.cli("install", "--accounts", "1", ok=False)
        self.assertEqual(sentinel.read_text(), "unrelated data")
        self.assertTrue(marker.exists())
        self.assertFalse((self.home / ".config/codex-accounts/registry.json").exists())
        self.cli("install", "--accounts", "1", "--adopt", f"1={existing}")
        self.assertEqual(self.account(1)["origin"], "adopted")

    def test_install_recovers_a_missing_marker_after_registry_write_interruption(self):
        self.cli("install", "--accounts", "1")
        home = Path(self.account(1)["home"])
        marker = home / ".codex-accounts-managed"
        # Model an interruption after the registry commit but before the marker.
        marker.unlink()
        self.cli("install", "--accounts", "1")
        self.assertEqual(self.account(1)["origin"], "manager-created")
        self.assertEqual(self.account(1)["managed_home"], str(home))
        self.assertTrue(marker.is_file())
        self.cli("remove", "codex1")
        self.cli("purge", "codex1", "--yes")
        self.assertFalse(home.exists())

    def test_purge_uses_immutable_manager_created_home(self):
        old_base = self.home / "old-profiles"
        new_base = self.home / "new-profiles"
        self.cli("install", "--accounts", "1", "--home-base", str(old_base))
        first_home = Path(self.account(1)["home"])
        self.cli("add", "codex2", "--home-base", str(new_base))
        self.assertEqual(self.registry()["home_base"], str(new_base))
        self.cli("remove", "codex1")
        self.cli("purge", "codex1", "--yes")
        self.assertFalse(first_home.exists())
        self.assertIn("2", self.registry()["accounts"])


if __name__ == "__main__":
    unittest.main()
