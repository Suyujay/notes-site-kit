# notes-site-kit

把一個 markdown 筆記 repo 變成可瀏覽的靜態網站。零設定、不動原本目錄結構。

支援兩種輸出：

- **material** — Material for MkDocs，目錄樹側欄、右側 TOC、中文搜尋、原生 Mermaid、深淺色
- **docsify** — 免建置，直接把 markdown 丟上去就能看

## 用法

```bash
pip install mkdocs-material

# 建置 + 本機預覽
python notes_site.py material <repo> --name "站名" --serve 8000
python notes_site.py docsify  <repo> --name "站名" --serve 8001

# 只建置
python notes_site.py material <repo> --name "站名"

# 建置後直接部署到 Cloudflare（需先 npx wrangler login）
python notes_site.py material <repo> --name "站名" --deploy <專案名>

# 檢查非 UTF-8（Big5）檔案與需改名的檔名
python notes_site.py check <repo>
```

產物：

```
<repo>/.notes_build/mkdocs.yml   設定（不進版控）
<repo>/.notes_build/docs/        複製後的 md 樹
<repo>/public/                   網站輸出
```

## Cloudflare Pages

| 欄位 | material | docsify |
|---|---|---|
| Build command | `pip install mkdocs-material && git clone --depth 1 https://github.com/Suyujay/notes-site-kit /tmp/kit && python /tmp/kit/notes_site.py material . --name "站名"` | `git clone --depth 1 https://github.com/Suyujay/notes-site-kit /tmp/kit && python /tmp/kit/notes_site.py docsify . --name "站名"` |
| Build output directory | `public` | `public` |
| 環境變數 | `PYTHON_VERSION=3.12` | 同 |

### 不想接 Git 整合時（任何 repo 都能用）

```bash
python notes_site.py material <repo> --name "站名" --deploy youtube-notes
```

會產生 `.notes_build/wrangler.jsonc`（設定不落在 repo 根目錄）並跑 `wrangler deploy`，
第一次會自動建立 Workers 專案，網址是 `https://<專案名>.<帳號>.workers.dev`。

注意：wrangler 4.158 的 `pages project create` 實際建的是 Worker 專案，
而且會在 cwd 寫 `wrangler.jsonc`、改 `.gitignore`。用 `--deploy` 可避開這件事。

`--deploy` 建立的專案不支援 push 自動部署；要 CI 請用下面的 Workers Builds。

### Workers Builds（push 自動部署）

Workers Builds **不吃** `wrangler.jsonc` 裡的 build 設定，指令要在 dashboard 填。
repo 只需要一份 `wrangler.jsonc` 告訴 wrangler 靜態檔在哪：

```jsonc
{
  "name": "站名",
  "compatibility_date": "2026-11-01",
  "assets": { "directory": "./public", "not_found_handling": "404-page" }
}
```

dashboard：Worker → Settings → Build → Connect Git 後填

| 欄位 | 值 |
|---|---|
| Build command | `python -m pip install --break-system-packages -q mkdocs-material && git clone --depth 1 https://github.com/Suyujay/notes-site-kit /tmp/kit && python /tmp/kit/notes_site.py material . --name "站名"` |
| Deploy command | `npx wrangler@4 deploy` |
| Build 環境變數 | `PYTHON_VERSION=3.12`（build image 預設 3.14，Material 的相依套件未必跟上） |

build image 內建 Python 3.14.8 / pip 26.2.1 / uv，`git` 也有，所以上面不需要額外安裝步驟。

## 私有存取

Cloudflare Zero Trust → Access → Applications → Add self-hosted → 指向該 Pages 網域，
政策設 `Emails` 白名單，登入方式 `One-time PIN`。免費版上限 50 人。

## 已知限制

- 非 UTF-8（Big5）的 `.md` 會被跳過並列在輸出中，需先轉存 UTF-8。
- 檔名結尾是 `.` 或空白時（例如 `xxx_....md`）Windows 會吃掉尾端字元，導致建置失敗；
  工具會在複製時自動改名（`xxx_....md` → `xxx.md`）並印出清單。
- Mermaid 由 Material 於瀏覽時從 unpkg 載入；要完全離線請在 `templates/mkdocs.yml` 打開 `privacy` 插件。
- 圖片請用相對路徑，絕對路徑在子路徑部署時會失效。
- 建議把 `/.notes_build/` 與 `/public/` 加進筆記 repo 的 `.gitignore`。
