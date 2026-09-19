# Codex Switch

在 macOS 與 Linux 上管理多個獨立 Codex CLI profile（資料目錄）的輕量工具。每個 `codexN` 都固定使用自己的 `CODEX_HOME`，因此可以同時執行，不需要交換 `auth.json`。

這是非官方社群工具，不隸屬於 OpenAI。它不會讀取、複製、上傳、列印或驗證登入 token（登入憑證）。

## 安裝

需要 Python 3.9+、Git 與已安裝的 [Codex CLI](https://developers.openai.com/codex/cli)。

```sh
git clone https://github.com/yves01480/codex-switch.git
cd codex-switch
python3 codex_accounts.py install --accounts 2 --shell-setup
export PATH="$HOME/.local/bin:$PATH"
codex1 login
codex2 login
```

把 `2` 改成所需帳號數。`--shell-setup` 會備份並更新 zsh/bash 的啟動設定，讓新開啟的終端機能找到這些指令。

已有 `~/.codex` 或 `~/.codex-personal` 時，可明確採用它們而不搬移登入資料：

```sh
python3 codex_accounts.py install --accounts 2 \
  --adopt "1=$HOME/.codex" \
  --adopt "2=$HOME/.codex-personal" \
  --shell-setup
```

## 日常使用

```sh
codex-switch status
codex-switch label codex1 first@example.com
codex-switch add codex3 third@example.com
codex3 login
codex-switch remove codex3
codex-switch enable codex3
codex-switch purge codex3 --yes
```

- `status` 顯示 profile、選填的 email 標籤與 `codex login status` 結果；email 只是本機標籤，不會從 token 判讀。
- `add` 必須依序新增：有 `codex1`、`codex2` 時，下一個只能是 `codex3`。支援到 `codex99`。
- `remove` 或 `del` 只停用 profile，保留資料與登入狀態；`enable` 可復原。
- `purge PROFILE --yes` 才會永久刪除資料，且僅限本工具建立、已停用、並仍保有完整歸屬記錄的 profile。採用的既有目錄及舊版 registry 一律不能 purge。

`codex-switch` 與 `codex-accounts` 是同一支管理程式的兩個名稱。各帳號可直接執行：

```sh
codex1
codex2 resume
codex4 login
```

## 更新

在 clone 的資料夾拉取已審閱的版本，再重跑安裝指令即可。這不會搬移或讀取憑證：

```sh
git pull --ff-only
python3 codex_accounts.py install --accounts 2 --shell-setup
```

工具不會自行從網路下載或執行更新程式。

## 本機資料

| 用途 | 預設位置 |
| --- | --- |
| 管理程式 | `~/.local/lib/codex-accounts/manager.py` |
| 全域指令 | `~/.local/bin/codex-switch`、`codex-accounts`、`codex1` 等 |
| 帳號清單 | `~/.config/codex-accounts/registry.json` |
| 新 profile | `~/.local/share/codex-accounts/account-N` |

`registry.json` 可能包含本機路徑與 email 標籤，權限是 0600（僅目前使用者可讀寫），絕不可提交到 Git。

## 測試

```sh
python3 test_accounts.py
```

測試使用暫存 HOME 和假的 Codex CLI，不會讀取任何實際登入資料。

## 安全與授權

請閱讀 [SECURITY.md](SECURITY.md)。本專案採用 [MIT License](LICENSE)。
