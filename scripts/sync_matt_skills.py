#!/usr/bin/env python3
"""把 mattpocock/skills 同步到本机技能目录（幂等）。

架构：`~/.agents/skills` 是唯一实体目录；`~/.claude/skills` 与 `~/.workbuddy/skills`
只放符号链接，各 harness 引用同一份文件，避免复制多份、版本漂移。

- 克隆/拉取到 ~/.cache/matt-skills
- 实体写入 ~/.agents/skills（已有则覆盖更新）
- 两个 harness 目录重建链接

只处理 engineering / productivity / misc 三组；in-progress 与 deprecated 不动。
用法：uv run python scripts/sync_matt_skills.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_URL = "https://github.com/mattpocock/skills.git"
CACHE = Path.home() / ".cache" / "matt-skills"
CANONICAL = Path.home() / ".agents/skills"
HARNESS_DIRS = (Path.home() / ".claude/skills", Path.home() / ".workbuddy/skills")
GROUPS = ("engineering", "productivity", "misc")


def sync_repo() -> Path:
    if (CACHE / ".git").is_dir():
        subprocess.run(["git", "-C", str(CACHE), "pull", "--ff-only"], check=True)
    else:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(CACHE)], check=True)
    return CACHE / "skills"


def link(harness_dir: Path, name: str, target: Path) -> None:
    harness_dir.mkdir(parents=True, exist_ok=True)
    path = harness_dir / name
    if path.is_symlink() or path.exists():
        path.unlink()
    path.symlink_to(target)


def main() -> int:
    root = sync_repo()
    CANONICAL.mkdir(parents=True, exist_ok=True)
    updated = created = 0
    for group in GROUPS:
        for src in sorted((root / group).iterdir()):
            if not (src / "SKILL.md").is_file():
                continue
            target = CANONICAL / src.name
            if target.exists():
                shutil.copytree(src, target, dirs_exist_ok=True)
                updated += 1
            else:
                shutil.copytree(src, target)
                created += 1
            for harness_dir in HARNESS_DIRS:
                link(harness_dir, src.name, target)
    print(f"更新 {updated} 个，新建 {created} 个；实体目录 {CANONICAL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
