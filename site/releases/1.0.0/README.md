# Codex 多帳號管理工具

macOS / Linux，Python 3.9 以上，支援 zsh / bash。只需攜帶 `codex_accounts.py`；不需要額外 Python 套件。每個 `codexN` 固定自己的 `CODEX_HOME`，可以同時執行，不交換 `auth.json`。

## HTTPS 自動安裝（推薦）

```sh
curl -fsSL https://install.cruxilion.com/cruxilion-codex.sh -o /tmp/cruxilion-codex.sh
sh /tmp/cruxilion-codex.sh --accounts 2
export PATH="$HOME/.local/bin:$PATH"
codex1 login
codex2 login
```

把 `2` 改成所需帳號數。安裝器會驗證管理程式 SHA-256、建立啟動器及 PATH 設定。若 Codex CLI 不存在且已有 npm，會自動安裝到 `~/.local`，不使用 sudo。若缺少 Python 3.9+ 或 npm，會顯示補裝指令。

首次安裝會沿用已存在的 `~/.codex`、`~/.codex-personal` 作為帳號 1、2；不複製憑證。重新安裝時沿用 registry，省略帳號數則保留原數量。

安裝後可直接執行：

```sh
cruxilion-codex.sh --accounts 5  # 擴充／修復啟動器
cruxilion-codex.sh --update      # 從 HTTPS 下載最新版安裝器，保留帳號數
```

新電腦需要先用完整下載網址取得安裝器，之後才有 `cruxilion-codex.sh` 這個指令。伺服器只提供程式檔案，各帳號仍在自己的電腦登入。

## 新電腦安裝

先安裝 Python 3.9+ 與 [Codex CLI](https://developers.openai.com/codex/cli)。若已安裝 Node.js，可用：

```sh
npm install -g @openai/codex
```

把本資料夾帶到新電腦，在資料夾中執行：

```sh
python3 codex_accounts.py install --accounts 2 --shell-setup
export PATH="$HOME/.local/bin:$PATH"
codex1 login
codex2 login
```

在各次登入時選擇對應帳號。安裝包不包含憑證，也不從舊電腦自動匯入登入資料。

`--shell-setup` 會備份並更新預設 zsh/bash 啟動檔，讓之後開啟的 Terminal、iTerm、VS Code 終端可找到指令。已開啟的 terminal 先執行上面的 `export`。自訂 `ZDOTDIR`、fish 或其他 shell，請自行把 `~/.local/bin` 加到 PATH。

## 日常使用與維護

```sh
codex1                          # 開啟帳號 1
codex2 resume                  # 帳號 2 自己的歷史紀錄
codex-accounts list            # 列出編號與資料目錄，不讀取登入 token
codex-accounts add             # 在現有最大編號後新增一個
codex3 login                   # 新帳號自行登入
codex-accounts install --accounts 5  # 擴充到 5 個；保留現有帳號
codex-accounts --version
```

帳號數範圍 1–99。重新安裝相同數量可修復啟動器；指定比現有最大編號小的數量會拒絕執行，避免誤刪帳號。工具不提供刪除或重新指定現有帳號目錄的指令。

取得新版腳本後更新：

```sh
python3 /path/to/new/codex_accounts.py install --accounts 5 --shell-setup
```

數量填目前需要的數量。此指令更新管理工具與啟動器，保留既有設定和憑證。也可使用上方的 `cruxilion-codex.sh --update` 下載更新；工具不會在背景自行更新。

## 路徑與既有帳號

| 用途 | 預設路徑 |
|---|---|
| 管理程式 | `~/.local/lib/codex-accounts/manager.py` |
| 全域指令 | `~/.local/bin/codex-accounts`、`codex1` 等 |
| 帳號清單 | `~/.config/codex-accounts/registry.json` |
| 新帳號資料 | `~/.local/share/codex-accounts/account-N` |

首次安裝可選擇自己的資料根目錄，之後 `add` 會沿用：

```sh
python3 codex_accounts.py install --accounts 2 --home-base "$HOME/my-codex-accounts"
```

也能採用既有目錄，無須複製憑證：

```sh
python3 codex_accounts.py install --accounts 2 \
  --adopt "1=$HOME/.codex" \
  --adopt "2=$HOME/.codex-personal" \
  --shell-setup
```

採用目錄時保留原本 `config.toml`。若採用 `~/.codex`，該帳號仍與使用這個目錄的 Codex 桌面程式共用資料。請不要再混用舊的「覆蓋 auth.json」切換工具，否則它仍能改變該目錄的登入帳號。

## 登入錯誤與設定警告

`codexN login status` 只能確認本機存在何種登入方式，不代表遠端憑證仍有效。若看到 `invalid_refresh_token`、`HTTP 401` 或要求重新登入：

```sh
codex2 login
```

若 Codex 仍要求先登出，執行 `codex2 logout` 再 `codex2 login`。登入與登出只使用這個編號的資料目錄；工具不會因缺少 `auth.json` 阻擋登入。

目前 Codex CLI 從家目錄啟動獨立 `CODEX_HOME` 時，可能把 `~/.codex/config.toml` 當成專案設定，造成 `notify` 警告及模型設定覆蓋。新建帳號設定預設將家目錄標記為 `untrusted`，阻止此載入；個別真正的專案仍可各自信任。家目錄可能出現未信任的提示；如果將整個家目錄重新設為 trusted，這個衝突可能再次發生。建議在實際專案資料夾中工作。

官方說明：[CODEX_HOME 與設定層](https://learn.chatgpt.com/docs/config-file/config-advanced)、[登入與憑證儲存](https://learn.chatgpt.com/docs/auth)。

## 測試

```sh
python3 test_accounts.py
python3 test_bootstrap.py
```

測試以暫存 HOME 和假 Codex 執行檔進行，不讀取真實登入資料、不呼叫模型。
