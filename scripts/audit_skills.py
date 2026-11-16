#!/usr/bin/env python3
"""审计 WorkBuddy 挂载的技能：体积、可调用性、重复与重叠。

用法：uv run python scripts/audit_skills.py
只读；不卸载、不修改任何技能。
"""

from __future__ import annotations

import hashlib
import re
from itertools import combinations
from pathlib import Path

WB = Path.home() / ".workbuddy/skills"
ROOT = Path.home() / ".agents/skills"

DEV_HINTS = (
    "code", "review", "test", "tdd", "git", "pr", "bug", "design", "spec",
    "ticket", "skill", "agent", "loop", "grill", "plan", "implement", "research",
    "security", "merge", "commit", "wizard", "handoff", "triage",
)
OFF_DOMAIN = ("daily-close", "weekly-compile", "my-zone", "paper", "journal",
              "literature", "origin-plot", "agentero", "capture-session", "ui-analyzer")


def frontmatter(text: str) -> str:
    m = re.search(r"^---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


def desc_of(fm: str) -> str:
    m = re.search(r"^description:\s*(.+)$", fm, re.M)
    return m.group(1).strip() if m else ""


def bigrams(text: str) -> set[str]:
    chars = re.sub(r"\s+", "", text.lower())
    return {chars[i : i + 2] for i in range(len(chars) - 1)}


def main() -> int:
    rows = []
    for link in sorted(WB.iterdir()):
        skill = link / "SKILL.md"
        if not skill.is_file():
            continue
        text = skill.read_text(encoding="utf-8", errors="ignore")
        fm = frontmatter(text)
        rows.append(
            {
                "name": link.name,
                "desc": desc_of(fm),
                "invocable": "disable-model-invocation: true" not in fm,
                "hash": hashlib.sha256(text.encode()).hexdigest()[:12],
                "bytes": len(text),
            }
        )

    invocable = [r for r in rows if r["invocable"]]
    desc_chars = sum(len(r["desc"]) for r in invocable)
    print(f"挂载 {len(rows)} 个；可被模型调用 {len(invocable)} 个")
    print(f"可调用 description 共 {desc_chars} 字符 ≈ {desc_chars / 2.2:.0f} tokens/轮")

    dup = {}
    for r in rows:
        dup.setdefault(r["hash"], []).append(r["name"])
    print("内容完全重复:", [v for v in dup.values() if len(v) > 1] or "无")

    pairs = []
    for a, b in combinations(invocable, 2):
        ja, jb = bigrams(a["desc"]), bigrams(b["desc"])
        if not ja or not jb:
            continue
        score = len(ja & jb) / len(ja | jb)
        if score >= 0.35:
            pairs.append((round(score, 2), a["name"], b["name"]))
    print("描述高度重叠（Jaccard ≥0.35）:")
    for score, a, b in sorted(pairs, reverse=True)[:10]:
        print(f"  {score:.2f}  {a}  ~  {b}")
    if not pairs:
        print("  无")

    off = [r["name"] for r in rows if any(h in r["name"] for h in OFF_DOMAIN)]
    print("与本仓库研发流程无关（候选卸载）:", off or "无")
    heavy = sorted(invocable, key=lambda r: -len(r["desc"]))[:5]
    print("描述最长的 5 个:", [(r["name"], len(r["desc"])) for r in heavy])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
