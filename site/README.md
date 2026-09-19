# Cruxilion Codex

在 macOS 與 Linux 上管理多個獨立 Codex CLI profile。每個 `codexN` 都固定使用自己的 `CODEX_HOME`，因此可以同時執行，不需要交換 `auth.json`。

目前穩定版本：**1.1.0**

> 這是非官方社群工具，不隸屬於 OpenAI。工具不會讀取、複製、上傳、列印或解析登入 token。

## 快速安裝

需要 macOS / Linux、Python 3.9+ 與 curl。Codex CLI 若不存在，而系統已有 npm，安裝器會以使用者權限安裝到 `~/.local`。

```sh
curl -fsSL https://install.cruxilion.com/cruxilion-codex.sh -o /tmp/cruxilion-codex.sh
sh /tmp/cruxilion-codex.sh --accounts 2
export PATH="$HOME/.local/bin:$PATH"
codex1 login
codex2 login
```

把 `2` 改成需要的 profile 數量，支援 1–99。

## 日常使用

```sh
codex1
codex2 resume
codex-switch status
codex-switch add codex3
codex-switch label codex1 first@example.com
codex-switch remove codex3
codex-switch enable codex3
```

`remove` 只會停用 profile 並保留資料。永久刪除必須明確使用：

```sh
codex-switch purge codex3 --yes
```

而且只允許刪除由工具建立、已停用、仍具完整歸屬記錄的 profile；採用的既有目錄與舊版 registry 不能 purge。

## 更新

```sh
cruxilion-codex.sh --update
```

更新是使用者主動觸發，不會在背景自行更新。既有 profile、設定與登入資料會保留。

## 既有 Codex 帳號

首次安裝時，若存在 `~/.codex` 與 `~/.codex-personal`，HTTPS 安裝器會採用它們作為前兩個 profile，不複製憑證。

若要手動指定：

```sh
python3 codex_accounts.py install --accounts 2 \
  --adopt "1=$HOME/.codex" \
  --adopt "2=$HOME/.codex-personal" \
  --shell-setup
```

## 下載與驗證

- [目前安裝器](/cruxilion-codex.sh)
- [1.1.0 完整 ZIP](/releases/1.1.0/codex-switch-v1.1.0.zip)
- [1.1.0 SHA256SUMS](/releases/1.1.0/SHA256SUMS)
- [1.1.0 原始管理程式](/releases/1.1.0/codex_accounts.py)
- [GitHub 原始碼](https://github.com/yves01480/codex-switch)
- [安全政策](https://github.com/yves01480/codex-switch/blob/main/SECURITY.md)

版本路徑是 immutable；已發布版本不覆寫。根目錄的 `cruxilion-codex.sh` 是目前最新版入口，設定為 `no-store`。

## 手機使用

網站可以在 iPhone / Android 正常閱讀與下載，但 Codex CLI 與本工具必須在 **macOS 或 Linux Terminal** 執行。

## 授權

核心工具採 MIT License。詳見 GitHub repository。
