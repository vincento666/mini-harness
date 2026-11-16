#!/usr/bin/env python3
"""把 mattpocock/skills 同步到本机三个技能目录（幂等）。

- 克隆/拉取到 ~/.cache/matt-skills
- 更新 ~/.claude/skills 与 ~/.agents/skills 里的同名副本（已有才更新，没有就新建）
- 在 ~/.workbuddy/skills 建符号链接（单一来源，避免复制两份）

只处理 engineering / productivity / misc 三组；in-progress 与 deprecated 不动。
用法：uv run python scripts/sync_matt_skills.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_URL = "https://github.com/mattpocock/skills.git"
CACHE = Path.home() / ".cache" / "matt-skills"
GROUPS = ("engineering", "productivity", "misc")
BASES = (Path.home() / ".claude/skills", Path.home() / ".agents/skills")
WORKBUDDY = Path.home() / ".workbuddy/skills"


def sync_repo() -> Path:
    if (CACHE / ".git").is_dir():
        subprocess.run(["git", "-C", str(CACHE), "pull", "--ff-only"], check=True)
    else:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(CACHE)], check=True)
    return CACHE / "skills"


def main() -> int:
    root = sync_repo()
    WORKBUDDY.mkdir(parents=True, exist_ok=True)
    updated = created = 0
    for group in GROUPS:
        for src in sorted((root / group).iterdir()):
            if not (src / "SKILL.md").is_file():
                continue
            target = next(
                (base / src.name for base in BASES if (base / src.name / "SKILL.md").is_file()),
                None,
            )
            if target is None:
                target = BASES[0] / src.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, target)
                created += 1
            else:
                shutil.copytree(src, target, dirs_exist_ok=True)
                updated += 1
            # 两处都有的，保持同一版本，避免漂移
            for base in BASES:
                if (base / src.name).is_dir() and base / src.name != target:
                    shutil.copytree(src, base / src.name, dirs_exist_ok=True)
            link = WORKBUDDY / src.name
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target)
    print(f"更新 {updated} 个，新建 {created} 个，链接目录 {WORKBUDDY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
