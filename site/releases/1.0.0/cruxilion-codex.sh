#!/bin/sh
# cruxilion-codex managed installer v1
set -eu

VERSION=1.0.0
BASE=https://install.cruxilion.com
MANAGER_SHA256=981d92ebf3e616d33bc802bb370ac153a02e5a89bc72d39d50372d1830d28b2f
accounts=
update=0

usage() {
    cat <<'EOF'
Usage: cruxilion-codex.sh [--accounts N | N] [--update]
  N: 1-99 accounts. Default: preserve installed count, otherwise 2.
  --update: download and run the current HTTPS installer.
  --help: show this help without downloading anything.

Requires macOS/Linux, Python 3.9+ and curl.
If Codex is absent, npm is used to install it into ~/.local (no sudo).
Existing accounts and credentials are preserved. Sign in with codexN login.
EOF
}

die() { printf '%s\n' "cruxilion-codex: $*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --update) update=1; shift ;;
        --accounts)
            [ "$#" -ge 2 ] || die '--accounts requires a number.'
            [ -z "$accounts" ] || die 'Specify the account count only once.'
            accounts=$2; shift 2 ;;
        [1-9]|[1-9][0-9])
            [ -z "$accounts" ] || die 'Specify the account count only once.'
            accounts=$1; shift ;;
        *) die "Unknown argument: $1 (use --help)." ;;
    esac
done
if [ -n "$accounts" ]; then
    case "$accounts" in [1-9]|[1-9][0-9]) ;; *) die 'Account count must be 1-99.' ;; esac
fi
case "$(uname -s)" in Darwin|Linux) ;; *) die 'Supported systems: macOS and Linux.' ;; esac
command -v python3 >/dev/null 2>&1 || die 'Install Python 3.9+: macOS: brew install python; Ubuntu/Debian: sudo apt-get install python3'
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || die 'Python 3.9 or newer is required.'
command -v curl >/dev/null 2>&1 || die 'Install curl first.'

REGISTRY="$HOME/.config/codex-accounts/registry.json"
if [ -z "$accounts" ]; then
    accounts=$(python3 - "$REGISTRY" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
if p.exists():
    d = json.loads(p.read_text())
    a = d['accounts']
    if d.get('version') != 1 or not isinstance(a, dict):
        raise SystemExit('Unsupported account registry')
    n = max((int(k) for k in a), default=2)
    if not 1 <= n <= 99:
        raise SystemExit('Invalid account registry')
    print(n)
else:
    print(2)
PY
    )
fi

# Check our own destination before downloading/installing anything.
python3 - <<'PY'
from pathlib import Path
p = Path.home() / '.local/bin/cruxilion-codex.sh'
for parent in p.parents:
    if (parent.exists() or parent.is_symlink()) and not parent.is_dir():
        raise SystemExit(f'Parent is not a directory: {parent}')
if p.is_symlink() or (p.exists() and (not p.is_file() or
        '# cruxilion-codex managed installer v1' not in p.read_text().splitlines()[:2])):
    raise SystemExit(f'Refusing to replace an unrelated file: {p}')
PY

temp=$(mktemp -d "${TMPDIR:-/tmp}/cruxilion-codex.XXXXXXXX")
trap 'rm -rf "$temp"' 0
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
download() {
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        --connect-timeout 15 --max-time 120 --output "$2" "$1"
}

if [ "$update" -eq 1 ]; then
    download "$BASE/cruxilion-codex.sh" "$temp/update.sh"
    sh "$temp/update.sh" --accounts "$accounts"
    exit 0
fi

printf 'Installing Cruxilion Codex accounts %s (%s accounts)…\n' "$VERSION" "$accounts"
download "$BASE/releases/$VERSION/codex_accounts.py" "$temp/manager.py"
python3 - "$temp/manager.py" "$MANAGER_SHA256" <<'PY'
import hashlib, pathlib, sys
if hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest() != sys.argv[2]:
    raise SystemExit('Manager checksum mismatch; installation stopped.')
PY
download "$BASE/releases/$VERSION/cruxilion-codex.sh" "$temp/installer.sh"
# POSIX shell syntax check before retaining the downloaded launcher.
sh -n "$temp/installer.sh"

PATH="$HOME/.local/bin:$PATH"
export PATH
if ! command -v codex >/dev/null 2>&1; then
    command -v npm >/dev/null 2>&1 || die 'Codex needs npm. macOS: brew install node; Ubuntu/Debian: sudo apt-get install nodejs npm. Then rerun this installer.'
    npm install --global --prefix "$HOME/.local" @openai/codex
    command -v codex >/dev/null 2>&1 || die 'npm completed but codex was not installed.'
fi

set -- install --accounts "$accounts" --shell-setup
if [ ! -e "$REGISTRY" ]; then
    if [ -d "$HOME/.codex" ]; then
        set -- "$@" --adopt "1=$HOME/.codex"
    fi
    if [ "$accounts" -ge 2 ] && [ -d "$HOME/.codex-personal" ]; then
        set -- "$@" --adopt "2=$HOME/.codex-personal"
    fi
fi
python3 "$temp/manager.py" "$@"
python3 - "$temp/installer.sh" <<'PY'
import os, pathlib, sys, tempfile
source = pathlib.Path(sys.argv[1]).read_bytes()
if b'# cruxilion-codex managed installer v1' not in source.splitlines()[:2]:
    raise SystemExit('Invalid installer marker')
path = pathlib.Path.home() / '.local/bin/cruxilion-codex.sh'
if path.is_symlink() or (path.exists() and
        b'# cruxilion-codex managed installer v1' not in path.read_bytes().splitlines()[:2]):
    raise SystemExit(f'Refusing to replace an unrelated file: {path}')
fd, temporary = tempfile.mkstemp(prefix='.cruxilion-codex.', dir=str(path.parent))
try:
    with os.fdopen(fd, 'wb') as f:
        os.fchmod(f.fileno(), 0o755)
        f.write(source)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
printf '\nReady. Open a new terminal, or run:\n  export PATH="$HOME/.local/bin:$PATH"\n'
printf '\nSign in to each account with codex1 login, codex2 login, etc.\n'
printf 'Manage: codex-accounts list | codex-accounts add\nUpdate: cruxilion-codex.sh --update\n'
