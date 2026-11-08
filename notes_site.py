#!/usr/bin/env python3
"""把 markdown 筆記 repo 變成可瀏覽的靜態網站。

用法：
    python notes_site.py material <repo> [--name 名稱] [--serve 8000]
    python notes_site.py docsify  <repo> [--name 名稱] [--serve 8001]
    python notes_site.py check    <repo>

產物：
    <repo>/.notes_build/mkdocs.yml   Material 設定（不進版控）
    <repo>/.notes_build/docs/        複製後的 md 樹
    <repo>/public/                   網站輸出（Cloudflare Pages 的輸出目錄）

設計：不動 repo 原本的目錄結構，先複製到 .notes_build/docs 再建置。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
TPL = HERE / "templates"

SKIP_DIRS = {
    ".git", ".github", ".notes_build", "public", "node_modules",
    ".playwright-mcp", ".obsidian", ".venv", "venv", "__pycache__",
    ".ipynb_checkpoints", "_site", "dist",
}
SKIP_FILES = {"AGENTS.md", "CLAUDE.md", ".DS_Store"}


def title_of(p: Path) -> str:
    try:
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            m = re.match(r"^#\s+(.+?)\s*#*\s*$", line)
            if m:
                return m.group(1).strip()
    except UnicodeDecodeError:
        pass
    return p.stem.replace("_", " ")


def is_utf8(p: Path) -> bool:
    try:
        p.read_text(encoding="utf-8-sig")
        return True
    except UnicodeDecodeError:
        return False


def needs_rename(name: str) -> bool:
    """Windows 會吃掉結尾的空白與句點，導致 mkdocs 建好的目錄找不到。"""
    if name != name.rstrip(" ."):
        return True
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem != stem.rstrip(" .")


def safe_name(name: str) -> str:
    """去尾端的點與空白；`x....md` -> `x.md`，`dir...` -> `dir`。"""
    stem, dot, ext = name.rpartition(".")
    if dot and ext and not name.startswith("."):
        return f"{stem.rstrip(' .') or '_'}.{ext}"
    return name.rstrip(" .") or "_"


def copy_tree(repo: Path, dst: Path) -> tuple[int, list[str], list[tuple[str, str]]]:
    """複製 markdown 樹（跳過 SKIP 與非 UTF-8 檔案）。

    回傳 (頁數, 被跳過的檔, [(舊相對路徑, 新相對路徑)])。
    """
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    pages, bad, renamed = 0, [], []

    def walk(src: Path, out: Path) -> None:
        nonlocal pages
        out.mkdir(parents=True, exist_ok=True)
        for item in sorted(src.iterdir()):
            if item.name in SKIP_DIRS or item.name in SKIP_FILES:
                continue
            target = out / safe_name(item.name)
            if target.name != item.name:
                n = 2
                base = target.name
                stem, dot, ext = base.rpartition(".")
                while target.exists():
                    target = out / (f"{stem}_{n}.{ext}" if dot else f"{base}_{n}")
                    n += 1
                renamed.append(
                    (item.relative_to(repo).as_posix(), target.relative_to(dst).as_posix())
                )
            if item.is_dir():
                if item.name.startswith("."):
                    continue
                walk(item, target)
            elif item.suffix.lower() == ".md":
                if not is_utf8(item):
                    bad.append(str(item.relative_to(repo)))
                    continue
                shutil.copy2(item, target)
                pages += 1
            else:
                shutil.copy2(item, target)

    walk(repo, dst)
    return pages, bad, renamed


def fix_renamed_links(docs: Path, renamed: list[tuple[str, str]]) -> int:
    """被改名的檔案，把其他頁面指向舊檔名的連結一併改掉。"""
    if not renamed:
        return 0
    pairs = [(Path(o).name, Path(n).name) for o, n in renamed]
    fixed = 0
    for md in docs.rglob("*.md"):
        text = md.read_text(encoding="utf-8-sig")
        orig = text
        for old, new in pairs:
            for a, b in ((old, new), (quote(old), quote(new))):
                if a != b and a in text:
                    text = text.replace(a, b)
        if text != orig:
            md.write_text(text, encoding="utf-8")
            fixed += 1
    return fixed


def write_dir_indexes(docs: Path, name: str, only_root: bool = False) -> int:
    """每個缺 index.md / README.md 的資料夾都補一個目錄頁。

    沒有目錄頁時，指向資料夾的連結（`../06_IP_Study/`）會 404，
    補上之後 mkdocs 才會產生該資料夾的 index.html。
    """
    created = 0
    targets = [docs] if only_root else [docs, *sorted(p for p in docs.rglob("*") if p.is_dir())]
    for d in targets:
        if (d / "index.md").exists() or (d / "README.md").exists():
            continue
        subdirs = sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith("."))
        files = sorted(p for p in d.iterdir() if p.is_file() and not p.name.startswith("."))
        mds = [f for f in files if f.suffix.lower() == ".md" and f.name not in SKIP_FILES]
        others = [f for f in files if f.suffix.lower() != ".md"]
        if not (subdirs or mds or others):
            empty = ["（這個資料夾目前是空的）", ""]
            (d / "index.md").write_text(f"# {name if d == docs else d.name}\n\n" + "\n".join(empty), encoding="utf-8")
            created += 1
            continue
        lines = [f"# {name if d == docs else d.name}", ""]
        if subdirs:
            lines += ["## 子目錄", ""]
            lines += [f"- [{s.name}]({s.name}/index.md)" for s in subdirs]
            lines.append("")
        if mds:
            lines += ["## 文件", ""]
            lines += [f"- [{title_of(f)}]({f.name})" for f in mds]
            lines.append("")
        if others:
            lines += ["## 附件", ""]
            lines += [f"- [{f.name}]({f.name})" for f in others[:200]]
            lines.append("")
        (d / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        created += 1
    return created


def gen_sidebar(docs: Path) -> str:
    lines = []

    def walk(d: Path, depth: int) -> None:
        for f in sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".md"):
            rel = f.relative_to(docs).as_posix()
            label = "首頁" if rel in ("README.md", "index.md") and depth == 0 else title_of(f)
            lines.append("  " * depth + f"- [{label}]({rel})")
        for sub in sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")):
            lines.append("  " * depth + f"- {sub.name}")
            walk(sub, depth + 1)

    walk(docs, 0)
    return "\n".join(lines) + "\n"


def build_material(repo: Path, name: str, pages: int) -> Path:
    build = repo / ".notes_build"
    docs = build / "docs"
    build.mkdir(exist_ok=True)
    cfg = (TPL / "mkdocs.yml").read_text(encoding="utf-8").replace("__NAME__", name)
    (build / "mkdocs.yml").write_text(cfg, encoding="utf-8")
    out = repo / "public"
    subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "-f", str(build / "mkdocs.yml"), "--clean"],
        check=True, cwd=str(repo),
    )
    return out


def build_docsify(repo: Path, name: str) -> Path:
    docs = repo / ".notes_build" / "docs"
    out = repo / "public"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(docs, out)
    html = (TPL / "docsify_index.html").read_text(encoding="utf-8")
    home = "index.md" if (docs / "index.md").exists() else "README.md"
    html = html.replace("__NAME__", name).replace("__HOME__", home)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "_sidebar.md").write_text(gen_sidebar(docs), encoding="utf-8")
    return out


def cmd_check(repo: Path) -> None:
    bad, rename, total = [], [], 0
    for p in repo.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and p.suffix.lower() == ".md":
            total += 1
            if not is_utf8(p):
                bad.append(str(p.relative_to(repo)))
        if needs_rename(p.name):
            rename.append(str(p.relative_to(repo)))
    print(f"md 總數 {total}，非 UTF-8 {len(bad)}，需改名 {len(rename)}")
    for b in bad:
        print(f"  跳過（非 UTF-8）：{b}")
    for r in rename:
        print(f"  改名（尾端點/空白）：{r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["material", "docsify", "check"])
    ap.add_argument("repo", type=Path)
    ap.add_argument("--name", default=None)
    ap.add_argument("--serve", type=int, default=0)
    ap.add_argument("--no-index", action="store_true", help="不要自動補資料夾目錄頁")
    ap.add_argument("--deploy", metavar="PROJECT", help="建置後用 wrangler 部署到 Cloudflare Pages")
    a = ap.parse_args()

    repo = a.repo.resolve()
    if not repo.is_dir():
        sys.exit(f"找不到目錄：{repo}")
    name = a.name or repo.name.replace("_", " ").title()

    if a.mode == "check":
        cmd_check(repo)
        return

    docs = repo / ".notes_build" / "docs"
    pages, bad, renamed = copy_tree(repo, docs)
    fixed = fix_renamed_links(docs, renamed)
    dirs = write_dir_indexes(docs, name) if not a.no_index else write_dir_indexes(docs, name, only_root=True)
    print(f"頁面 {pages}，非 UTF-8 跳過 {len(bad)}，改名 {len(renamed)}，補目錄頁 {dirs}")
    for b in bad:
        print(f"  跳過（Big5？）：{b}")
    for old, new in renamed:
        print(f"  改名（尾端點/空白）：{old} -> {Path(new).name}")
    if fixed:
        print(f"  連帶修正 {fixed} 個檔案的連結")

    out = build_material(repo, name, pages) if a.mode == "material" else build_docsify(repo, name)
    files = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"[{a.mode}] 輸出 {out}  ({files} 檔)")

    if a.serve:
        host = ["-m", "mkdocs", "serve", "-f", ".notes_build/mkdocs.yml", "-a", f"127.0.0.1:{a.serve}"]
        if a.mode == "docsify":
            host = ["-m", "http.server", str(a.serve), "-d", "public"]
        subprocess.run([sys.executable, *host], cwd=str(repo))

    if a.deploy:
        deploy_to_cloudflare(repo, out, a.deploy)


def deploy_to_cloudflare(repo: Path, out: Path, project: str) -> None:
    """用 wrangler 直接上傳（Workers 靜態資源），不需要 Cloudflare 的 Git 整合。

    設定寫在 `.notes_build/` 而非 repo 根目錄，維持「筆記 repo 不加檔案」。
    """
    cfg = repo / ".notes_build" / "wrangler.jsonc"
    rel = Path(os.path.relpath(out, cfg.parent)).as_posix()
    cfg.write_text(
        "{\n"
        f'  "name": "{project}",\n'
        '  "compatibility_date": "2026-11-01",\n'
        '  "assets": {\n'
        f'    "directory": "{rel}",\n'
        '    "not_found_handling": "404-page"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    cmd = 'npx --yes wrangler deploy -c wrangler.jsonc'
    print(f"[deploy] {cmd}  (cwd={cfg.parent})")
    subprocess.run(cmd, cwd=str(cfg.parent), shell=True, check=True)


if __name__ == "__main__":
    main()
