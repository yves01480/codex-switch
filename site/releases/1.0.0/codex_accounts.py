#!/usr/bin/env python3
# codex-accounts managed v1
"""Portable, independent Codex CLI account homes. Python 3.9+, macOS/Linux."""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile

VERSION = "1.0.0"
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


def fail(message):
    raise ValueError(message)


def number(value):
    if not re.fullmatch(r"[1-9][0-9]?", str(value)):
        fail("Account numbers/counts must be integers from 1 to 99.")
    return int(value)


def home_path(value):
    path = Path(value).expanduser().resolve()
    if HOME not in path.parents:
        fail(f"Account/install paths must be below HOME: {path}")
    return path


def validate_target(path, managed=False):
    home_path(path)
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
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


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
            fail("Another install/add is running. Try again after it finishes.")
        yield


def load(required=False):
    validate_target(REGISTRY)
    if not REGISTRY.exists():
        if required:
            fail("Run install --accounts N first.")
        return {"version": 1, "home_base": str(BASE), "accounts": {}}
    data = json.loads(REGISTRY.read_text())
    if not isinstance(data, dict) or data.get("version") != 1:
        fail("Unsupported registry format; no files changed.")
    accounts = data.get("accounts")
    if not isinstance(accounts, dict):
        fail("Malformed account registry.")
    home_path(data["home_base"])
    paths = []
    for key, value in accounts.items():
        number(key)
        if not isinstance(value, str) or not Path(value).is_absolute():
            fail(f"Invalid home for account {key}.")
        paths.append(str(home_path(value)))
    if len(paths) != len(set(paths)):
        fail("Two accounts cannot share one CODEX_HOME.")
    return data


def initial_config():
    return ('cli_auth_credentials_store = "file"\n\n'
            '# HOME is not a project: do not import the default account config.\n'
            f'[projects.{json.dumps(str(HOME), ensure_ascii=False)}]\n'
            'trust_level = "untrusted"\n')


def wrapper(arguments):
    # Resolve Python at invocation time; no machine-specific Python version path.
    command = " ".join(shlex.quote(x) for x in [str(LIB), *arguments])
    return f'#!/bin/sh\n{MARKER}\nexec python3 {command} "$@"\n'


def shell_plans():
    plans = []
    # Do not create bash_profile when absent: that would suppress an existing
    # bash_login/profile. Amend whichever login file bash actually selects.
    login = next((HOME / n for n in (".bash_profile", ".bash_login", ".profile")
                  if (HOME / n).exists()), HOME / ".profile")
    for path in dict.fromkeys([HOME / ".zshenv", HOME / ".bashrc", login]):
        validate_target(path)
        old = path.read_text() if path.exists() else ""
        if PATH_MARKER not in old:
            plans.append((path, old + "\n" + PATH_BLOCK,
                          (path.stat().st_mode & 0o777) if path.exists() else 0o644))
    return plans


def install(args, add=False):
    with lock():
        data = load(required=add)
        accounts = data["accounts"]
        highest = max(map(int, accounts), default=0)
        count = number(highest + 1 if add else args.accounts)
        if count < highest:
            fail(f"Cannot reduce the count below {highest}; existing accounts are preserved.")
        base = home_path(args.home_base or data["home_base"])
        adopted = {}
        for item in args.adopt:
            key, sep, value = item.partition("=")
            n = number(key)
            if not sep or not value or n > count or key in adopted:
                fail("Use --adopt NUMBER=PATH once per account, within the account count.")
            path = home_path(value)
            if not path.is_dir():
                fail(f"Adopted home does not exist: {path}")
            adopted[key] = str(path)
        for n in range(1, count + 1):
            key = str(n)
            path = adopted.get(key, str(home_path(base / f"account-{n}")))
            if key in accounts and key in adopted and accounts[key] != path:
                fail(f"Account {n} already has a different home; refusing to reassign it.")
            accounts.setdefault(key, path)
        homes = [home_path(p) for p in accounts.values()]
        for path in homes:
            validate_target(path / "config.toml")
            for reserved in (STATE, BIN, LIB.parent):
                if path == reserved or path in reserved.parents or reserved in path.parents:
                    fail(f"Account home overlaps installer files: {path}")
        if len(homes) != len(set(homes)):
            fail("Two accounts cannot share one CODEX_HOME.")
        # A parent account may contain sessions/auth for a child account.
        for i, path in enumerate(homes):
            if any(path in other.parents or other in path.parents for other in homes[i + 1:]):
                fail("Account homes must not be nested inside one another.")
        data["home_base"] = str(base)
        outputs = [(LIB, Path(__file__).read_text(), 0o600),
                   (BIN / "codex-accounts", wrapper([]), 0o755)]
        outputs += [(BIN / f"codex{k}", wrapper(["run", k]), 0o755) for k in accounts]
        # Validate every known conflict before replacing any installed file.
        for path, _, _ in outputs:
            validate_target(path, managed=True)
        configs = []
        for path in homes:
            if path.exists() and not path.is_dir():
                fail(f"Account home is not a directory: {path}")
            config = path / "config.toml"
            if not config.exists():
                validate_target(config)
                configs.append((config, initial_config(), 0o600))
        shells = shell_plans() if args.shell_setup else []
        for path, _, _ in shells:
            validate_target(path.with_name(path.name + ".before-codex-accounts"))
        for path in homes:
            if not path.exists():
                path.mkdir(parents=True, mode=0o700)
        for path, text, mode in outputs + configs:
            atomic_write(path, text, mode)
        # Commit registry after launchers exist; an interrupted install is rerunnable.
        atomic_write(REGISTRY, json.dumps(data, indent=2) + "\n", 0o600)
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
    key = str(number(args.number))
    data = load(required=True)
    if key not in data["accounts"]:
        fail(f"Account {key} is not installed.")
    path = home_path(data["accounts"][key])
    if not path.is_dir():
        fail(f"Account home missing: {path}. Re-run install to restore its directory.")
    if not shutil.which("codex"):
        fail("Codex CLI is not installed/on PATH. Install Codex CLI first.")
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(path)
    # Never check auth.json: Codex owns login, keyring, refresh and logout.
    os.execvpe("codex", ["codex", *args.arguments], environment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "add"):
        p = sub.add_parser(name)
        if name == "install":
            p.add_argument("--accounts", required=True, type=number)
        p.add_argument("--home-base")
        p.add_argument("--adopt", action="append", default=[])
        p.add_argument("--shell-setup", action="store_true",
                       help="Add ~/.local/bin to zsh/bash startup files (with backups).")
    sub.add_parser("list")
    p = sub.add_parser("run")
    p.add_argument("number", type=number)
    p.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command in ("install", "add"):
        install(args, add=args.command == "add")
    elif args.command == "run":
        run(args)
    else:
        for key, value in sorted(load(required=True)["accounts"].items(), key=lambda x: int(x[0])):
            print(f"codex{key}\t{value}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"codex-accounts: {exc}", file=sys.stderr)
        sys.exit(2)
