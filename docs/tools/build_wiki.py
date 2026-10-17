#!/usr/bin/env python3
"""构建 repowiki：把 repowiki/src/pages 的正文片段编译成 zh/content 下的 HTML 页面树，
并生成 zh/meta/repowiki-metadata.json 台账。

用法：
    uv run python docs/tools/build_wiki.py
    uv run python docs/tools/build_wiki.py --only 核心运行时

正文片段里的 {{svg:<图表 id>}} 会被替换成内联 SVG 与图名；
页面外壳、导航、面包屑、元数据全部由本脚本生成，正文里不写跨页链接。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import posixpath
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent.parent
sys.path.insert(0, str(TOOLS))

import wiki_catalog as catalog
from diagram_defs import FIGURES

SRC_PAGES = REPO / "repowiki" / "src" / "pages"
SVG_DIR = REPO / "repowiki" / "assets" / "svg"
CONTENT = REPO / "repowiki" / "zh" / "content"
META = REPO / "repowiki" / "zh" / "meta"
INVENTORY = REPO / "repowiki" / "assets" / "meta" / "inventory.json"

REPO_ID = "mini-harness"
NOW = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S")

CSS = """
:root{--bg:#0b1220;--panel:#101a2c;--line:#1f2f47;--ink:#e6edf6;--sub:#9fb3cc;--muted:#6b829f;
--core:#00b4d8;--data:#48cae4;--ok:#06d6a0;--warn:#f77f00;--mono:'Courier New','Lucida Console','Microsoft YaHei',monospace;
--sans:'Helvetica Neue',Helvetica,'PingFang SC','Microsoft YaHei',sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.75}
.layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:24px;padding:24px;max-width:1500px;margin:0 auto}
nav.toc{position:sticky;top:16px;align-self:start;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px 12px;font-size:13px;max-height:calc(100vh - 32px);overflow:auto}
nav.toc .brand{font-family:var(--mono);font-size:12px;letter-spacing:.08em;color:var(--core);margin-bottom:10px}
nav.toc ul{list-style:none;margin:0;padding:0}
nav.toc li{margin:2px 0}
nav.toc a{color:var(--sub);text-decoration:none;display:block;padding:3px 6px;border-radius:4px}
nav.toc a:hover{background:#16233a;color:var(--ink)}
nav.toc a.current{background:#16233a;color:var(--core);border-left:2px solid var(--core)}
nav.toc .lvl2{padding-left:12px}
nav.toc .lvl3{padding-left:24px}
nav.toc .hub>a{color:var(--ink);font-weight:600}
main{min-width:0}
.crumbs{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:14px}
.crumbs a{color:var(--data);text-decoration:none}
article{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:26px 30px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:.01em}
h2{font-size:19px;margin:34px 0 10px;padding-top:10px;border-top:1px solid var(--line);color:var(--core)}
h3{font-size:16px;margin:22px 0 8px;color:var(--ink)}
h4{font-size:14px;margin:18px 0 6px;color:var(--sub);font-family:var(--mono)}
p,li{color:var(--ink)}
ul,ol{padding-left:22px}
code{font-family:var(--mono);background:#0d1728;border:1px solid var(--line);border-radius:3px;padding:1px 5px;font-size:13px;color:#d7e6f5}
pre{background:#0d1728;border:1px solid var(--line);border-radius:6px;padding:12px 14px;overflow:auto;font-family:var(--mono);font-size:13px}
cite{display:block;background:#0d1728;border:1px dashed var(--line);border-radius:6px;padding:10px 14px;margin:14px 0 20px;font-size:13px;color:var(--sub)}
cite a{color:var(--data);text-decoration:none;font-family:var(--mono)}
a{color:var(--data)}
ul.sources{list-style:none;padding:0;margin:10px 0 18px;font-size:12.5px;color:var(--muted)}
ul.sources li{margin:2px 0}
ul.sources a{font-family:var(--mono);color:var(--muted)}
ul.sources a:hover{color:var(--data)}
figure{margin:18px 0;padding:12px;background:#08111f;border:1px solid var(--line);border-radius:8px}
figure svg{width:100%;height:auto;display:block}
figcaption{font-family:var(--mono);font-size:12px;color:var(--sub);margin-top:8px}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:left}
th{background:#13203a;color:var(--core);font-family:var(--mono);font-size:12px;letter-spacing:.04em}
.missing{border:1px dashed var(--warn);border-radius:6px;padding:12px;color:var(--warn);font-family:var(--mono);font-size:13px}
footer{color:var(--muted);font-size:12px;font-family:var(--mono);margin-top:22px}
@media(max-width:980px){.layout{grid-template-columns:1fr}nav.toc{position:static;max-height:none}}
"""


def load_svg(fig_id: str) -> str | None:
    path = SVG_DIR / f"{fig_id}.svg"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("<?xml"):
        text = text.split("?>", 1)[1]
    return text.strip()


def figure_block(fig_id: str, titles: dict[str, tuple[str, str]]) -> str:
    svg = load_svg(fig_id)
    if svg is None:
        return f'<div class="missing">缺图表源：{fig_id}</div>'
    title, subtitle = titles.get(fig_id, (fig_id, ""))
    return (
        '<figure class="fig">'
        f'<div class="fig-svg">{svg}</div>'
        f"<figcaption>{title}　·　{subtitle}</figcaption>"
        "</figure>"
    )


def nav_html(current: dict[str, Any]) -> str:
    items: list[str] = []
    for item in catalog.CATALOG:
        cls = "lvl2" if item["level"] == 2 else "lvl3" if item["level"] == 3 else ""
        if catalog.children_of(item["slug"]):
            cls += " hub"
        if item["slug"] == current["slug"]:
            cls += " current"
        href = rel_link(current, item)
        items.append(f'<li class="{cls.strip()}"><a href="{href}">{item["name"]}</a></li>')
    return (
        '<nav class="toc"><div class="brand">MINI-HARNESS / REPOWIKI</div><ul>'
        + "".join(items)
        + "</ul></nav>"
    )


def rel_link(from_item: dict[str, Any], to_item: dict[str, Any]) -> str:
    here = posixpath.dirname(catalog.path_of(from_item))
    target = catalog.path_of(to_item)
    return posixpath.relpath(target, here or ".")


def crumbs_html(item: dict[str, Any]) -> str:
    chain: list[dict[str, Any]] = []
    cursor: dict[str, Any] | None = item
    while cursor is not None:
        chain.append(cursor)
        cursor = catalog.by_slug()[cursor["parent"]] if cursor["parent"] else None
    parts = [f'<a href="{rel_link(item, catalog.CATALOG[0])}">repowiki</a>']
    for entry in reversed(chain):
        if entry["slug"] == item["slug"]:
            parts.append(entry["name"])
        else:
            parts.append('<a href="{}">{}</a>'.format(rel_link(item, entry), entry["name"]))
    return " / ".join(parts)


def build_page(item: dict[str, Any], titles: dict[str, tuple[str, str]]) -> str:
    src = SRC_PAGES / f"{item['slug']}.html"
    if not src.exists():
        body = f'<div class="missing">正文片段缺失：repowiki/src/pages/{item["slug"]}.html</div>'
    else:
        body = src.read_text(encoding="utf-8")
        for fig_id in item["diagrams"]:
            body = body.replace(f"{{{{svg:{fig_id}}}}}", figure_block(fig_id, titles))
    children = catalog.children_of(item["slug"])
    child_links = ""
    if children:
        links = "".join(
            '<li><a href="{}">{}</a></li>'.format(rel_link(item, child), child["name"])
            for child in children
        )
        child_links = f"<h2>本目录页面</h2><ul>{links}</ul>"
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{item['name']} · mini-harness repowiki</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        '<div class="layout">\n' + nav_html(item) + "\n<main>\n"
        f'<div class="crumbs">{crumbs_html(item)}</div>\n'
        "<article>\n" + body.strip() + "\n" + child_links + "\n"
        f"<footer>页面 {item['slug']} · 层级 {item['level']} · 生成于 {NOW}</footer>\n"
        "</article>\n</main>\n</div>\n</body>\n</html>\n"
    )


def build_catalog_tree() -> str:
    lines = ["repowiki/zh/content/"]
    for item in catalog.CATALOG:
        path = catalog.path_of(item)
        depth = path.count("/")
        lines.append("    " * depth + ("├── " if depth else "") + path.split("/")[-1])
    lines.append("repowiki/zh/meta/repowiki-metadata.json")
    return "\n".join(lines)


def build_metadata() -> dict[str, Any]:
    inventory = (
        json.loads(INVENTORY.read_text(encoding="utf-8")) if INVENTORY.exists() else {"modules": []}
    )
    slug_to_cat = {
        item["slug"]: f"cat-{index:03d}" for index, item in enumerate(catalog.CATALOG, start=1)
    }

    source_files: list[dict[str, Any]] = []
    seen_paths: dict[str, str] = {}
    for item in catalog.CATALOG:
        for raw in item["files"]:
            path = raw.rstrip("/")
            if path in seen_paths:
                continue
            seen_paths[path] = f"src-{len(source_files) + 1:03d}"
            source_files.append(
                {
                    "id": seen_paths[path],
                    "repo_id": REPO_ID,
                    "path": path,
                    "gmt_create": NOW,
                    "gmt_modified": NOW,
                }
            )

    code_snippets: list[dict[str, Any]] = []
    for module in inventory["modules"]:
        path = module["path"]
        for cls in module.get("classes", []):
            code_snippets.append(
                {
                    "id": f"snip-{len(code_snippets) + 1:03d}",
                    "path": path,
                    "line_range": f"{cls['start']}-{cls['end']}",
                    "name": cls["name"],
                    "kind": "class",
                    "gmt_create": NOW,
                    "gmt_modified": NOW,
                }
            )
        for fn in module.get("functions", []):
            code_snippets.append(
                {
                    "id": f"snip-{len(code_snippets) + 1:03d}",
                    "path": path,
                    "line_range": f"{fn['start']}-{fn['end']}",
                    "name": fn["name"],
                    "kind": "function",
                    "gmt_create": NOW,
                    "gmt_modified": NOW,
                }
            )

    wiki_catalogs: list[dict[str, Any]] = []
    wiki_items: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    for item in catalog.CATALOG:
        cat_id = slug_to_cat[item["slug"]]
        wiki_catalogs.append(
            {
                "id": cat_id,
                "repo_id": REPO_ID,
                "name": item["name"],
                "description": item["slug"],
                "prompt": item["prompt"],
                "progress_status": "completed",
                "dependent_files": ",".join(item["files"]),
                "raw_data": json.dumps(
                    {"diagrams": item["diagrams"], "level": item["level"]}, ensure_ascii=False
                ),
                "layer_level": item["level"],
                "order": item["order"],
                "parent_id": slug_to_cat.get(item["parent"], ""),
            }
        )
        wiki_items.append(
            {
                "id": f"item-{len(wiki_items) + 1:03d}",
                "catalog_id": cat_id,
                "title": item["name"],
                "description": item["prompt"],
                "extend": "{}",
                "progress_status": "completed",
                "repo_id": REPO_ID,
                "reference_count": 0,
                "gmt_create": NOW,
                "gmt_modified": NOW,
            }
        )
        if item["parent"]:
            relations.append(
                {
                    "id": f"rel-{len(relations) + 1:03d}",
                    "source_id": slug_to_cat[item["parent"]],
                    "target_id": cat_id,
                    "source_type": "WIKI_ITEM",
                    "target_type": "WIKI_ITEM",
                    "relationship_type": "PARENT_CHILD",
                    "extra": "{}",
                    "gmt_create": NOW,
                    "gmt_modified": NOW,
                }
            )
        for raw in item["files"]:
            path = raw.rstrip("/")
            relations.append(
                {
                    "id": f"rel-{len(relations) + 1:03d}",
                    "source_id": cat_id,
                    "target_id": seen_paths[path],
                    "source_type": "WIKI_ITEM",
                    "target_type": "SOURCE_FILE",
                    "relationship_type": "REFERENCED_BY",
                    "extra": "{}",
                    "gmt_create": NOW,
                    "gmt_modified": NOW,
                }
            )
        for snippet in code_snippets:
            if snippet["path"].rstrip("/") in {f.rstrip("/") for f in item["files"]}:
                relations.append(
                    {
                        "id": f"rel-{len(relations) + 1:03d}",
                        "source_id": cat_id,
                        "target_id": snippet["id"],
                        "source_type": "WIKI_ITEM",
                        "target_type": "CODE_SNIPPET",
                        "relationship_type": "CONTAINS",
                        "extra": "{}",
                        "gmt_create": NOW,
                        "gmt_modified": NOW,
                    }
                )

    tree = build_catalog_tree()
    return {
        "wiki_catalogs": wiki_catalogs,
        "wiki_items": wiki_items,
        "source_files": source_files,
        "code_snippets": code_snippets,
        "knowledge_relations": relations,
        "wiki_overview": {
            "id": "overview-001",
            "repo_id": REPO_ID,
            "content": (
                "<blog>mini-harness 是一个 MVP 个人实验版 agent harness，用来把参考 harness 的运行时决策"
                "重写成可读、可测、可回放的最小实现。M1 交付追加式事件日志、折叠装配、五步回合循环与 CLI "
                "run/replay 黑盒；文件工具与围栏在 M2，并发与超时在 M3，真实 Provider 在 M4，窗口预算与压缩在 M5。"
                "本 wiki 同时面向人类与 AI：每个结论都带源码行区间引用，每张图都带可校验的 SVG 源。</blog>"
            ),
            "gmt_create": NOW,
            "gmt_modified": NOW,
        },
        "wiki_readme": {
            "id": "readme-001",
            "repo_id": REPO_ID,
            "content": (
                "# mini-harness repowiki\n\n"
                "页面树在 zh/content 下，根级页面与目录同名枢纽页并列，目录内可再嵌一层目录。\n"
                "正文片段在 repowiki/src/pages，图表源在 repowiki/assets/svg，"
                "生成工具在 docs/tools。构建命令：uv run python docs/tools/build_wiki.py\n"
            ),
            "gmt_create": NOW,
            "gmt_modified": NOW,
        },
        "wiki_repo": {
            "id": "repo-001",
            "name": REPO_ID,
            "progress_status": "completed",
            "wiki_present_status": "completed",
            "optimized_catalog": tree,
            "current_document_structure": json.dumps(
                [
                    {"slug": item["slug"], "level": item["level"], "parent": item["parent"]}
                    for item in catalog.CATALOG
                ],
                ensure_ascii=False,
            ),
            "catalogue_think_content": (
                "目录按「先宏观架构与流程，再关键机制细节」的顺序组织：架构设计、核心运行时、工具契约、"
                "Provider 抽象、CLI 命令、事件与数据模型、测试与质量门禁，根级页面承担概览、上手、流程、工具、路线图与术语。"
            ),
            "recovery_checkpoint": f"wiki_generation_completed:{len(catalog.CATALOG)}",
            "last_commit_id": "",
            "extend_info": json.dumps(
                {"diagram_count": len(FIGURES), "page_count": len(catalog.CATALOG)},
                ensure_ascii=False,
            ),
            "gmt_create": NOW,
            "gmt_modified": NOW,
        },
    }


def build_index() -> str:
    rows: list[str] = []
    for item in catalog.CATALOG:
        indent = "&nbsp;" * (2 * (item["level"] - 1))
        href = posixpath.relpath(catalog.path_of(item), ".")
        rows.append(f'<li>{indent}<a href="zh/content/{href}">{item["name"]}</a></li>')
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        "<title>mini-harness repowiki</title>\n"
        f'<style>{CSS}</style>\n</head>\n<body>\n<div class="layout">\n'
        '<nav class="toc"><div class="brand">MINI-HARNESS / REPOWIKI</div><ul>'
        + "".join(
            f'<li><a href="zh/content/{posixpath.relpath(catalog.path_of(x), ".")}">{x["name"]}</a></li>'
            for x in catalog.CATALOG
        )
        + "</ul></nav>\n<main><article><h1>mini-harness repowiki</h1>"
        "<p>同一套内容两种读法：人类从「项目概述」顺序读，AI 从目录表与元数据直接定位。"
        "每页正文都带源码行区间引用，每张图都是可校验的 SVG 源。</p>"
        f"<ul>{''.join(rows)}</ul>"
        '<ul class="sources"><li><b>章节来源</b></li>'
        '<li><a href="file://docs/tools/wiki_catalog.py">docs/tools/wiki_catalog.py</a></li>'
        '<li><a href="file://docs/tools/build_wiki.py">docs/tools/build_wiki.py</a></li></ul>'
        f"<footer>共 {len(catalog.CATALOG)} 篇 · 生成于 {NOW}</footer></article></main></div>\n</body>\n</html>\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 repowiki HTML 页面树")
    parser.add_argument("--only", default="", help="只构建 slug 前缀匹配的页面")
    args = parser.parse_args()

    titles = {fig["id"]: (fig["title"], fig.get("subtitle", "")) for fig in FIGURES}
    built = 0
    missing: list[str] = []
    for item in catalog.CATALOG:
        if args.only and not item["slug"].startswith(args.only):
            continue
        out_path = CONTENT / catalog.path_of(item)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(build_page(item, titles), encoding="utf-8")
        built += 1
        if not (SRC_PAGES / f"{item['slug']}.html").exists():
            missing.append(item["slug"])

    META.mkdir(parents=True, exist_ok=True)
    (REPO / "repowiki" / "index.html").write_text(build_index(), encoding="utf-8")
    (META / "repowiki-metadata.json").write_text(
        json.dumps(build_metadata(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"页面 {built} 篇 · 缺正文 {len(missing)} 篇 -> {CONTENT}")
    if missing:
        print("缺正文：" + "、".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
