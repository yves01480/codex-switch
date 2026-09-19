# install.cruxilion.com deployment

正式流量使用 Cloudflare Pages。Contabo Nginx 僅保留為 rollback origin，不在正常請求路徑。

## 不變條件

- `site/cruxilion-codex.sh` 是目前最新版入口，必須使用 `Cache-Control: no-store`。
- `site/releases/<version>/` 是 immutable；已發布版本禁止覆寫。
- 安裝器內的 `MANAGER_SHA256` 必須等於該版本 `codex_accounts.py` 的 SHA-256。
- 不得發布 `auth.json`、真實 `registry.json`、profile 目錄、session、browser data 或任何憑證。

## 發布前

```sh
python3 test_accounts.py
python3 test_bootstrap.py
sh -n cruxilion-codex.sh
cmp cruxilion-codex.sh site/cruxilion-codex.sh
```

同步更新 `site/` 的 current installer 與 immutable 版本目錄後再發布。

## Cloudflare Pages

Pages project：`cruxilion-codex-installer`

自訂網域：

```text
install.cruxilion.com
  CNAME -> cruxilion-codex-installer.pages.dev
```

目前採 Direct Upload。使用具 Pages 權限的 scoped token：

```sh
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
npx wrangler pages deploy site \
  --project-name cruxilion-codex-installer \
  --branch main
```

部署後驗證首頁、current installer、版本檔與 SHA-256。

## Rollback

Contabo 保留 `/srv/cruxilion-codex-installer/public` 與 Nginx fallback。若 Pages 發生事故，可移除特定 `install.cruxilion.com` Pages CNAME / custom-domain association，讓既有 `*.cruxilion.com` Cloudflare Tunnel wildcard 再度承接流量。

回退後要重新測：

```sh
curl -fsSI https://install.cruxilion.com/
curl -fsS https://install.cruxilion.com/cruxilion-codex.sh | grep '^VERSION='
```
