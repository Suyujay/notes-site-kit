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
import re
import shutil
import subprocess
import sys
from pathlib import Path

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


def copy_tree(repo: Path, dst: Path) -> tuple[int, list[str]]:
    """複製 markdown 樹（跳過 SKIP 與非 UTF-8 檔案）。回傳 (頁數, 被跳過的檔)。"""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    pages, bad = 0, []

    def walk(src: Path, out: Path) -> None:
        nonlocal pages
        out.mkdir(parents=True, exist_ok=True)
        for item in sorted(src.iterdir()):
            if item.name in SKIP_DIRS or item.name in SKIP_FILES:
                continue
            if item.is_dir():
                if item.name.startswith("."):
                    continue
                walk(item, out / item.name)
            elif item.suffix.lower() == ".md":
                if not is_utf8(item):
                    bad.append(str(item.relative_to(repo)))
                    continue
                shutil.copy2(item, out / item.name)
                pages += 1
            else:
                shutil.copy2(item, out / item.name)

    walk(repo, dst)
    return pages, bad


def write_landing(docs: Path, name: str) -> None:
    """沒有 index.md / README.md 時，產生一個目錄首頁。"""
    if (docs / "index.md").exists() or (docs / "README.md").exists():
        return
    lines = [f"# {name}", "", "## 目錄", ""]
    for d in sorted(p for p in docs.iterdir() if p.is_dir()):
        lines.append(f"- **{d.name}**")
        for f in sorted(d.glob("*.md"))[:20]:
            lines.append(f"    - [{title_of(f)}]({d.name}/{f.name})")
    (docs / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    bad, total = [], 0
    for p in repo.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        total += 1
        if not is_utf8(p):
            bad.append(str(p.relative_to(repo)))
    print(f"md 總數 {total}，非 UTF-8 {len(bad)}")
    for b in bad:
        print(f"  跳過：{b}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["material", "docsify", "check"])
    ap.add_argument("repo", type=Path)
    ap.add_argument("--name", default=None)
    ap.add_argument("--serve", type=int, default=0)
    a = ap.parse_args()

    repo = a.repo.resolve()
    if not repo.is_dir():
        sys.exit(f"找不到目錄：{repo}")
    name = a.name or repo.name.replace("_", " ").title()

    if a.mode == "check":
        cmd_check(repo)
        return

    pages, bad = copy_tree(repo, repo / ".notes_build" / "docs")
    write_landing(repo / ".notes_build" / "docs", name)
    print(f"頁面 {pages}，非 UTF-8 跳過 {len(bad)}")
    for b in bad:
        print(f"  跳過（Big5？）：{b}")

    out = build_material(repo, name, pages) if a.mode == "material" else build_docsify(repo, name)
    files = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"[{a.mode}] 輸出 {out}  ({files} 檔)")

    if a.serve:
        host = ["-m", "mkdocs", "serve", "-f", ".notes_build/mkdocs.yml", "-a", f"127.0.0.1:{a.serve}"]
        if a.mode == "docsify":
            host = ["-m", "http.server", str(a.serve), "-d", "public"]
        subprocess.run([sys.executable, *host], cwd=str(repo))


if __name__ == "__main__":
    main()
