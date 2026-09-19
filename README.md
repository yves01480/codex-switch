# Codex Switch

在 macOS 與 Linux 上管理多個獨立 Codex CLI profile。每個 `codexN` 固定使用自己的 `CODEX_HOME`，因此可以同時執行，不需要交換 `auth.json`。

這是非官方社群工具，不隸屬於 OpenAI。它不會讀取、複製、上傳、列印或解析登入 token。

## 推薦安裝

公開安裝站：`https://install.cruxilion.com`

```sh
curl -fsSL https://install.cruxilion.com/cruxilion-codex.sh -o /tmp/cruxilion-codex.sh
sh /tmp/cruxilion-codex.sh --accounts 2
export PATH="$HOME/.local/bin:$PATH"
codex1 login
codex2 login
```

需要 macOS / Linux、Python 3.9+ 與 curl。若尚未安裝 Codex CLI，而系統已有 npm，安裝器會以使用者權限安裝到 `~/.local`。

## 日常使用

```sh
codex-switch status
codex-switch add codex3 third@example.com
codex-switch label codex1 first@example.com
codex3 login
codex-switch remove codex3
codex-switch enable codex3
codex-switch purge codex3 --yes
```

- `remove` / `del` 只停用 profile，資料與登入狀態保留。
- `purge PROFILE --yes` 才會永久刪除，而且只允許處理本工具建立、已停用、仍有完整歸屬記錄的 profile。
- `codex-switch` 與 `codex-accounts` 是同一支管理程式的兩個名稱。

## 更新

HTTPS 安裝使用者：

```sh
cruxilion-codex.sh --update
```

Git clone 使用者：

```sh
git pull --ff-only
python3 codex_accounts.py install --accounts 2 --shell-setup
```

更新不會在背景自行進行，也不會搬移或讀取登入憑證。

## 既有帳號與資料

若要明確採用既有 `~/.codex`、`~/.codex-personal`：

```sh
python3 codex_accounts.py install --accounts 2 \
  --adopt "1=$HOME/.codex" \
  --adopt "2=$HOME/.codex-personal" \
  --shell-setup
```

| 用途 | 預設位置 |
| --- | --- |
| 管理程式 | `~/.local/lib/codex-accounts/manager.py` |
| 指令 | `~/.local/bin/codex-switch`、`codex-accounts`、`codex1` 等 |
| 帳號清單 | `~/.config/codex-accounts/registry.json` |
| 新 profile | `~/.local/share/codex-accounts/account-N` |

`registry.json` 可能包含本機路徑與 email 標籤，絕不可提交到 Git。

## 測試

```sh
python3 test_accounts.py
python3 test_bootstrap.py
sh -n cruxilion-codex.sh
```

測試使用暫存 HOME 與假的 Codex CLI，不會讀取真實登入資料。

請閱讀 [SECURITY.md](SECURITY.md)。安裝站部署方式見 [DEPLOY.md](DEPLOY.md)。本專案採 MIT License。
