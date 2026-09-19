#!/usr/bin/env python3
# codex-accounts managed v1
"""Portable, independent Codex CLI profiles. Python 3.9+, macOS/Linux."""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

VERSION = "1.1.0"
# Keep the original marker so upgrades can safely replace v1 launchers.
MARKER = "# codex-accounts managed v1"
HOME = Path.home().resolve()
STATE = HOME / ".config/codex-accounts"
REGISTRY = STATE / "registry.json"
LIB = HOME / ".local/lib/codex-accounts/manager.py"
BIN = HOME / ".local/bin"
BASE = HOME / ".local/share/codex-accounts"
PATH_MARKER = "# >>> codex-accounts PATH >>>"
PATH_BLOCK = '''# >>> codex-accounts PATH >>>
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
# <<< codex-accounts PATH <<<
'''
MANAGED_HOME_MARKER = ".codex-accounts-managed"
ORIGINS = {"adopted", "legacy-unknown", "manager-created"}


def fail(message):
    raise ValueError(message)


def number(value):
    if not re.fullmatch(r"[1-9][0-9]?", str(value)):
        fail("Account numbers/counts must be integers from 1 to 99.")
    return int(value)


def profile_number(value):
    text = str(value)
    match = re.fullmatch(r"(?:codex)?([1-9][0-9]?)", text)
    if not match:
        fail("Profiles must be written as codex1..codex99 (or 1..99 where allowed).")
    return number(match.group(1))


def expected_email(value):
    if value is None:
        return None
    value = value.strip()
    if (not value or len(value) > 254 or any(ord(char) < 32 for char in value)
            or any(char.isspace() for char in value) or "@" not in value
            or value.startswith("@") or value.endswith("@")):
        fail("Expected email must be a single-line email address.")
    return value


def home_path(value):
    path = Path(value).expanduser().resolve()
    if HOME not in path.parents:
        fail(f"Account/install paths must be below HOME: {path}")
    return path


def validate_no_symlink_components(path):
    raw_path = Path(path).expanduser()
    # Resolve() hides both final and dangling symlinks, so inspect every supplied
    # component before converting it to the canonical path used by the manager.
    for component in (raw_path, *raw_path.parents):
        if component.is_symlink():
            fail(f"Refusing to use a symlinked path component: {component}")
        if component == HOME:
            break


def paths_overlap(first, second):
    return first == second or first in second.parents or second in first.parents


def validate_target(path, managed=False):
    raw_path = Path(path).expanduser()
    path = home_path(raw_path)
    validate_no_symlink_components(raw_path)
    for parent in path.parents:
        if (parent.exists() or parent.is_symlink()) and not parent.is_dir():
            fail(f"Parent path is not a directory: {parent}")
    if path.is_symlink():
        fail(f"Refusing to replace a symlink: {path}")
    if path.exists():
        if not path.is_file():
            fail(f"Not a regular file: {path}")
        if managed and MARKER not in path.read_text().splitlines()[:2]:
            fail(f"Refusing to replace an unrelated file: {path}")


def atomic_write(path, text, mode):
    validate_target(path)
    path = home_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def registry_text(data):
    return json.dumps(data, indent=2) + "\n"


@contextlib.contextmanager
def lock():
    home_path(STATE)
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / "install.lock"
    validate_target(path)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("Another profile change is running. Try again after it finishes.")
        yield


def empty_registry():
    return {"version": 2, "home_base": str(BASE), "accounts": {}}


def migrate_v1(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        fail("Unsupported registry format; no files changed.")
    accounts = data.get("accounts")
    if not isinstance(accounts, dict):
        fail("Malformed account registry.")
    migrated = empty_registry()
    migrated["home_base"] = data.get("home_base")
    for key, value in accounts.items():
        migrated["accounts"][key] = {
            "enabled": True,
            "expected_email": None,
            "home": value,
            "managed_home": None,
            # v1 cannot prove how this directory was created, so it is never purgeable.
            "origin": "legacy-unknown",
        }
    return migrated


def normalize_v2(data):
    # v2 before managed_home existed cannot prove its manager-created directories
    # were not supplied by a user. Downgrade that provenance rather than guessing.
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if isinstance(accounts, dict):
        for record in accounts.values():
            if isinstance(record, dict) and "managed_home" not in record:
                if record.get("origin") == "manager-created":
                    record["origin"] = "legacy-unknown"
                record["managed_home"] = None
    return data


def validate_registry(data):
    if not isinstance(data, dict) or data.get("version") != 2:
        fail("Unsupported registry format; no files changed.")
    if not isinstance(data.get("home_base"), str):
        fail("Malformed account registry home base.")
    validate_no_symlink_components(data["home_base"])
    home_path(data["home_base"])
    accounts = data.get("accounts")
    if not isinstance(accounts, dict):
        fail("Malformed account registry.")
    homes = []
    for key, record in accounts.items():
        number(key)
        if not isinstance(record, dict):
            fail(f"Invalid profile record for codex{key}.")
        home = record.get("home")
        if not isinstance(home, str) or not Path(home).is_absolute():
            fail(f"Invalid home for codex{key}.")
        validate_no_symlink_components(home)
        resolved = home_path(home)
        if type(record.get("enabled")) is not bool:
            fail(f"Invalid enabled state for codex{key}.")
        if record.get("origin") not in ORIGINS:
            fail(f"Invalid origin for codex{key}.")
        managed_home = record.get("managed_home")
        if record["origin"] == "manager-created":
            if not isinstance(managed_home, str) or not Path(managed_home).is_absolute():
                fail(f"Invalid managed home for codex{key}.")
            validate_no_symlink_components(managed_home)
            if home_path(managed_home) != resolved:
                fail(f"Managed home mismatch for codex{key}.")
        elif managed_home is not None:
            fail(f"Only manager-created profiles may have a managed home: codex{key}.")
        email = record.get("expected_email")
        if email is not None and (not isinstance(email, str) or expected_email(email) != email):
            fail(f"Invalid expected email for codex{key}.")
        homes.append(resolved)
    if len(homes) != len(set(homes)):
        fail("Two accounts cannot share one CODEX_HOME.")
    for home in homes:
        for reserved in (STATE, BIN, LIB, LIB.parent):
            if paths_overlap(home, reserved):
                fail(f"Account home overlaps installer files: {home}")
    for index, home in enumerate(homes):
        if any(paths_overlap(home, other) for other in homes[index + 1:]):
            fail("Account homes must not be nested inside one another.")


def load(required=False):
    validate_target(REGISTRY)
    if not REGISTRY.exists():
        if required:
            fail("Run install --accounts N first.")
        return empty_registry()
    data = json.loads(REGISTRY.read_text())
    if isinstance(data, dict) and data.get("version") == 1:
        data = migrate_v1(data)
    elif isinstance(data, dict) and data.get("version") == 2:
        data = normalize_v2(data)
    validate_registry(data)
    return data


def sorted_accounts(data):
    return sorted(data["accounts"].items(), key=lambda item: int(item[0]))


def profile_record(data, selector):
    key = str(profile_number(selector))
    try:
        return key, data["accounts"][key]
    except KeyError:
        fail(f"Profile codex{key} is not installed.")


def account_home(record):
    return home_path(record["home"])


def initial_config():
    return ('cli_auth_credentials_store = "file"\n\n'
            '# HOME is not a project: do not import the default account config.\n'
            f'[projects.{json.dumps(str(HOME), ensure_ascii=False)}]\n'
            'trust_level = "untrusted"\n')


def wrapper(arguments):
    # Resolve Python at invocation time; no machine-specific Python version path.
    command = " ".join(shlex.quote(item) for item in [str(LIB), *arguments])
    return f'#!/bin/sh\n{MARKER}\nexec python3 {command} "$@"\n'


def shell_plans():
    plans = []
    # Do not create bash_profile when absent: that would suppress an existing
    # bash_login/profile. Amend whichever login file bash actually selects.
    login = next((HOME / name for name in (".bash_profile", ".bash_login", ".profile")
                  if (HOME / name).exists()), HOME / ".profile")
    for path in dict.fromkeys([HOME / ".zshenv", HOME / ".bashrc", login]):
        validate_target(path)
        old = path.read_text() if path.exists() else ""
        if PATH_MARKER not in old:
            plans.append((path, old + "\n" + PATH_BLOCK,
                          (path.stat().st_mode & 0o777) if path.exists() else 0o644))
    return plans


def parse_adoptions(items, count):
    adopted = {}
    for item in items:
        key, separator, value = item.partition("=")
        number(key)
        if not separator or not value or int(key) > count or key in adopted:
            fail("Use --adopt NUMBER=PATH once per account, within the account count.")
        validate_no_symlink_components(value)
        path = home_path(value)
        if not path.is_dir():
            fail(f"Adopted home must be an existing non-symlink directory: {path}")
        adopted[key] = str(path)
    return adopted


def write_managed_marker(home, key):
    atomic_write(home / MANAGED_HOME_MARKER,
                 json.dumps({"profile": key, "version": 1}) + "\n", 0o600)


def install(args, add=False):
    with lock():
        data = load(required=add)
        accounts = data["accounts"]
        highest = max((int(key) for key in accounts), default=0)
        count = number(highest + 1 if add else args.accounts)
        if count < highest:
            fail(f"Cannot reduce the count below {highest}; existing accounts are preserved.")
        requested_name = getattr(args, "name", None)
        if requested_name is not None and requested_name != f"codex{count}":
            fail(f"Next profile name must be exactly codex{count}.")
        supplied_email = getattr(args, "expected_email", None)
        if supplied_email is not None and getattr(args, "email", None) is not None:
            fail("Use either the positional expected email or --expected-email, not both.")
        supplied_email = expected_email(supplied_email or getattr(args, "email", None))
        base_value = args.home_base or data["home_base"]
        validate_no_symlink_components(base_value)
        base = home_path(base_value)
        adopted = parse_adoptions(args.adopt, count)
        marker_homes = []
        for number_value in range(1, count + 1):
            key = str(number_value)
            path = adopted.get(key, str(home_path(base / f"account-{number_value}")))
            if key in accounts:
                if key in adopted and accounts[key]["home"] != path:
                    fail(f"Profile codex{key} already has a different home; refusing to reassign it.")
                # The registry is the ownership record. A crash after it was
                # atomically committed but before the marker was written is safe
                # to repair on a later install; a marker alone is not proof.
                if accounts[key]["origin"] == "manager-created":
                    marker_homes.append(key)
                continue
            if key not in adopted and Path(path).exists():
                # A plaintext marker is forgeable and cannot prove provenance.
                # Existing directories therefore always require explicit adoption.
                fail(f"Refusing to claim existing directory as manager-created: {path}. "
                     f"Use --adopt {key}={path} instead.")
            accounts[key] = {
                "enabled": True,
                "expected_email": supplied_email if add and number_value == count else None,
                "home": path,
                "managed_home": path if key not in adopted else None,
                "origin": "adopted" if key in adopted else "manager-created",
            }
            if key not in adopted:
                marker_homes.append(key)
        data["home_base"] = str(base)
        validate_registry(data)
        outputs = [(LIB, Path(__file__).read_text(), 0o600),
                   (BIN / "codex-accounts", wrapper([]), 0o755),
                   (BIN / "codex-switch", wrapper([]), 0o755)]
        outputs += [(BIN / f"codex{key}", wrapper(["run", key]), 0o755)
                    for key, _ in sorted_accounts(data)]
        # Validate every known conflict before replacing any installed file.
        for path, _, _ in outputs:
            validate_target(path, managed=True)
        configs = []
        homes = {key: account_home(record) for key, record in sorted_accounts(data)}
        for key, home in homes.items():
            if home.exists() and not home.is_dir():
                fail(f"Account home is not a directory: {home}")
            config = home / "config.toml"
            if not config.exists():
                validate_target(config)
                configs.append((config, initial_config(), 0o600))
            if key in marker_homes:
                validate_target(home / MANAGED_HOME_MARKER)
        shells = shell_plans() if args.shell_setup else []
        for path, _, _ in shells:
            validate_target(path.with_name(path.name + ".before-codex-accounts"))
        for home in homes.values():
            if not home.exists():
                home.mkdir(parents=True, mode=0o700)
        for path, text, mode in outputs + configs:
            atomic_write(path, text, mode)
        # The registry is the provenance record. Commit it before its marker: a
        # crash in the small window before marker creation can be safely repaired
        # on reinstall, while an unregistered directory is never claimed.
        atomic_write(REGISTRY, registry_text(data), 0o600)
        for key in marker_homes:
            write_managed_marker(homes[key], key)
        for path, text, mode in shells:
            if path.exists():
                backup = path.with_name(path.name + ".before-codex-accounts")
                if not backup.exists():
                    atomic_write(backup, path.read_text(), mode)
            atomic_write(path, text, mode)
    print(f"Installed codex-accounts {VERSION}: codex1 .. codex{count}")
    print('For this terminal: export PATH="$HOME/.local/bin:$PATH"')
    print(f"Then sign in separately: codex{count} login")
    if not shutil.which("codex"):
        print("Codex CLI is not on PATH yet. Install it before signing in.")


def run(args):
    data = load(required=True)
    key, record = profile_record(data, args.profile)
    if not record["enabled"]:
        fail(f"Profile codex{key} is disabled. Run enable codex{key} to restore it.")
    home = account_home(record)
    if not home.is_dir():
        fail(f"Account home missing: {home}. Re-run install to restore its directory.")
    executable = shutil.which("codex")
    if not executable:
        fail("Codex CLI is not installed/on PATH. Install Codex CLI first.")
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(home)
    # Never check auth.json: Codex owns login, keyring, refresh and logout.
    os.execvpe(executable, ["codex", *args.arguments], environment)


def clean_status_text(text):
    text = " ".join(text.split())
    return text[:240] + ("…" if len(text) > 240 else "")


def status(args):
    data = load(required=True)
    if args.profile is None:
        records = sorted_accounts(data)
    else:
        records = [profile_record(data, args.profile)]
    executable = shutil.which("codex")
    healthy = True
    for key, record in records:
        state = "enabled" if record["enabled"] else "disabled"
        email = record["expected_email"] or "not set"
        print(f"codex{key}\t{state}\texpected: {email}")
        home = account_home(record)
        if not home.is_dir():
            print("  auth: profile home is missing")
            healthy = False
            continue
        if not executable:
            print("  auth: Codex CLI is not on PATH")
            healthy = False
            continue
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(home)
        try:
            result = subprocess.run([executable, "login", "status"], env=environment,
                                    text=True, capture_output=True, check=False, timeout=10)
        except subprocess.TimeoutExpired:
            print("  auth: status check timed out")
            healthy = False
            continue
        except OSError as exc:
            print(f"  auth: unable to start Codex CLI ({exc})")
            healthy = False
            continue
        output = clean_status_text(result.stdout or result.stderr)
        if result.returncode == 0:
            print(f"  auth: {output or 'status returned no details'}")
        else:
            print(f"  auth: unavailable ({output or f'exit {result.returncode}'})")
            healthy = False
    return healthy


def list_profiles():
    data = load(required=True)
    for key, record in sorted_accounts(data):
        # Preserve the v1 list shape for scripts that consume the second column as a path.
        print(f"codex{key}\t{record['home']}")


def label(args):
    with lock():
        data = load(required=True)
        key, record = profile_record(data, args.profile)
        record["expected_email"] = expected_email(args.email)
        atomic_write(REGISTRY, registry_text(data), 0o600)
    print(f"Set expected email for codex{key}. This label is not login verification.")


def set_enabled(args, enabled):
    with lock():
        data = load(required=True)
        key, record = profile_record(data, args.profile)
        changed = record["enabled"] != enabled
        record["enabled"] = enabled
        atomic_write(REGISTRY, registry_text(data), 0o600)
    if changed:
        action = "Enabled" if enabled else "Disabled"
        print(f"{action} codex{key}. Its profile data and login state were preserved.")
    else:
        print(f"codex{key} is already {'enabled' if enabled else 'disabled'}.")


def managed_marker_matches(home, key):
    marker = home / MANAGED_HOME_MARKER
    if marker.is_symlink() or not marker.is_file():
        return False
    try:
        data = json.loads(marker.read_text())
    except (OSError, ValueError, TypeError):
        return False
    return data == {"profile": key, "version": 1}


def tombstone_path(path, purpose):
    for index in range(100):
        candidate = path.with_name(f".{path.name}.codex-accounts-{purpose}-{os.getpid()}-{index}")
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    fail(f"Unable to reserve a safe {purpose} location beside {path}.")


def purge(args):
    if not args.yes:
        fail(f"Refusing to purge {args.profile} without explicit --yes.")
    with lock():
        data = load(required=True)
        key, record = profile_record(data, args.profile)
        if record["enabled"]:
            fail(f"Disable codex{key} with remove before purging it.")
        if record["origin"] != "manager-created":
            fail(f"codex{key} was not proven manager-created and cannot be purged.")
        home = account_home(record)
        expected_home = home_path(record["managed_home"])
        if home != expected_home or home.is_symlink() or not home.is_dir():
            fail(f"codex{key} is not a safe managed profile directory.")
        if not managed_marker_matches(home, key):
            fail(f"codex{key} has no matching manager ownership marker; refusing to purge.")
        launcher = BIN / f"codex{key}"
        if launcher.exists() or launcher.is_symlink():
            validate_target(launcher, managed=True)
        home_tombstone = tombstone_path(home, "purge")
        launcher_tombstone = tombstone_path(launcher, "purge") if launcher.exists() else None
        os.replace(home, home_tombstone)
        try:
            if launcher_tombstone is not None:
                os.replace(launcher, launcher_tombstone)
            del data["accounts"][key]
            atomic_write(REGISTRY, registry_text(data), 0o600)
        except BaseException:
            if launcher_tombstone is not None and launcher_tombstone.exists():
                os.replace(launcher_tombstone, launcher)
            if home_tombstone.exists():
                os.replace(home_tombstone, home)
            raise
    try:
        shutil.rmtree(home_tombstone)
        if launcher_tombstone is not None and launcher_tombstone.exists():
            os.unlink(launcher_tombstone)
    except OSError as exc:
        print(f"Purged codex{key} from the registry, but cleanup needs attention: {exc}",
              file=sys.stderr)
        return False
    print(f"Purged codex{key} and its manager-created profile data.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--accounts", required=True, type=number)
    install_parser.add_argument("--home-base")
    install_parser.add_argument("--adopt", action="append", default=[])
    install_parser.add_argument("--shell-setup", action="store_true",
                                help="Add ~/.local/bin to zsh/bash startup files (with backups).")
    add_parser = sub.add_parser("add", help="Create exactly the next sequential profile.")
    add_parser.add_argument("name", nargs="?", help="Optional exact next name, e.g. codex3.")
    add_parser.add_argument("email", nargs="?", help="Optional expected-email label.")
    add_parser.add_argument("--expected-email")
    add_parser.add_argument("--home-base")
    add_parser.add_argument("--adopt", action="append", default=[])
    add_parser.add_argument("--shell-setup", action="store_true",
                            help="Add ~/.local/bin to zsh/bash startup files (with backups).")
    status_parser = sub.add_parser("status", help="Check each profile through codex login status.")
    status_parser.add_argument("profile", nargs="?")
    sub.add_parser("list", help="List registered profile homes without checking credentials.")
    label_parser = sub.add_parser("label", help="Set a local expected-email label for a profile.")
    label_parser.add_argument("profile")
    label_parser.add_argument("email")
    for name in ("enable", "remove"):
        command_parser = sub.add_parser(name, aliases=["del"] if name == "remove" else [])
        command_parser.add_argument("profile")
    purge_parser = sub.add_parser("purge", help="Permanently delete a disabled manager-created profile.")
    purge_parser.add_argument("profile")
    purge_parser.add_argument("--yes", action="store_true")
    run_parser = sub.add_parser("run", help="Run Codex with a selected profile.")
    run_parser.add_argument("profile")
    run_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command in ("install", "add"):
        install(args, add=args.command == "add")
    elif args.command == "run":
        run(args)
    elif args.command == "status":
        if not status(args):
            sys.exit(1)
    elif args.command == "list":
        list_profiles()
    elif args.command == "label":
        label(args)
    elif args.command == "enable":
        set_enabled(args, True)
    elif args.command in ("remove", "del"):
        set_enabled(args, False)
    elif args.command == "purge" and not purge(args):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"codex-accounts: {exc}", file=sys.stderr)
        sys.exit(2)
