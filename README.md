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

# 檢查非 UTF-8（Big5）檔案
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

## 私有存取

Cloudflare Zero Trust → Access → Applications → Add self-hosted → 指向該 Pages 網域，
政策設 `Emails` 白名單，登入方式 `One-time PIN`。免費版上限 50 人。

## 已知限制

- 非 UTF-8（Big5）的 `.md` 會被跳過並列在輸出中，需先轉存 UTF-8。
- Mermaid 由 Material 於瀏覽時從 unpkg 載入；要完全離線請在 `templates/mkdocs.yml` 打開 `privacy` 插件。
- 圖片請用相對路徑，絕對路徑在子路徑部署時會失效。
- 建議把 `/.notes_build/` 與 `/public/` 加進筆記 repo 的 `.gitignore`。
