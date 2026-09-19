# Security policy

Codex Switch manages local profile directories. It must never read, copy, upload,
print, commit, or parse Codex credentials.

## Data that must stay local

- `auth.json`, access tokens, API keys, browser sessions, and keychain material
- `registry.json` from a real user machine; it can contain local paths and optional
  expected-email labels
- profile directories, session history, logs, and caches

The test suite uses a temporary HOME and a fake `codex` executable. Do not replace
that fake data with a real account while testing or debugging.

## Deletion model

`remove` and `del` only disable a profile. `purge PROFILE --yes` is destructive and
is permitted only for a disabled profile that this manager created and marked. It
must refuse adopted and legacy profiles.

## Reporting a vulnerability

Do not include credentials, `auth.json`, or copied terminal output containing tokens
in an issue. Report the affected version, operating system, safe reproduction steps,
and the expected versus actual behavior to the maintainer through a private channel.
