"""技能发现与正文读取（M14）：四级根、kebab-case、清单注入。

发现发生在装配期；清单进 `session/start.payload.skills` 与受保护头部，正文只在
`skill` 工具被调用时读，并作为 `tool/result` 落日志（不变量 A：回放只认日志）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# 名字照 DSH 的 kebab-case：小写字母/数字，单词之间一个连字符。
KEBAB_CASE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# 单个技能的描述进清单前截到这里（DSH 的 catalogDescriptionMaxLength 默认值）。
DESCRIPTION_MAX = 500
# 受保护头部里技能清单的字符预算；超了截断并留 marker。
CATALOG_BUDGET = 2000
# `skill` 工具单次返回的正文上限；超了截断并提示用 read 读全文。
BODY_LIMIT = 32 * 1024

HOME_ENV = "MINIHNS_HOME"
DEFAULT_HOME_DIR = ".mini-harness"
BUNDLED_DIR = "builtin_skills"

# 四个根的 rank 照 DSH：项目内 100、项目共享 200、用户级 400、内置 600。
RANK_PROJECT = 100
RANK_PROJECT_SHARED = 200
RANK_USER = 400
RANK_BUNDLED = 600


@dataclass(frozen=True)
class Skill:
    """发现到的一个技能：清单要的三个字段 + 正文所在路径。"""

    name: str
    description: str
    rank: int
    path: Path


def _frontmatter(text: str) -> dict[str, str]:
    """只认 `name` 与 `description` 两个键，按 `key: value` 解析（不引入 YAML）。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() in {"name", "description"}:
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def _strip_frontmatter(text: str) -> str:
    """去掉 frontmatter 块；`<skill_instructions>` 里只放正文。"""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[index + 1 :]).lstrip("\n")
    return text


def _skill_at(path: Path, rank: int) -> Skill | None:
    """读一个候选文件；名字不合规或读不出就是「没有这个技能」，不抛。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fields = _frontmatter(text)
    fallback = path.parent.name if path.name == "SKILL.md" else path.stem
    name = fields.get("name") or fallback
    if KEBAB_CASE.fullmatch(name) is None:
        return None
    return Skill(
        name=name,
        description=(fields.get("description") or "").strip()[:DESCRIPTION_MAX],
        rank=rank,
        path=path,
    )


def _scan(root: Path, rank: int) -> list[Skill]:
    """一个根下的技能：目录式 `<name>/SKILL.md` 或扁平 `<name>.md`，不递归。"""
    if not root.is_dir():
        return []
    found: list[Skill] = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            candidate = entry / "SKILL.md"
            if not candidate.is_file():
                continue
        elif entry.suffix == ".md" and entry.is_file():
            candidate = entry
        else:
            continue
        skill = _skill_at(candidate, rank)
        if skill is not None:
            found.append(skill)
    return found


def skill_roots(workspace: Path, environ: Mapping[str, str]) -> list[tuple[int, Path]]:
    """四个根与它们的 rank；`MINIHNS_HOME` 没给就用 `~/.mini-harness`。"""
    home = Path(environ.get(HOME_ENV) or Path.home() / DEFAULT_HOME_DIR)
    return [
        (RANK_PROJECT, workspace / ".minihns" / "skills"),
        (RANK_PROJECT_SHARED, workspace / ".agents" / "skills"),
        (RANK_USER, home / "skills"),
        (RANK_BUNDLED, Path(__file__).parent / BUNDLED_DIR),
    ]


def discover_skills(workspace: Path, environ: Mapping[str, str]) -> tuple[Skill, ...]:
    """四级根合并：同名取 rank 小者（并列取路径小者），结果按名字排序。"""
    by_name: dict[str, Skill] = {}
    for rank, root in skill_roots(workspace, environ):
        for skill in _scan(root, rank):
            current = by_name.get(skill.name)
            if current is None or (skill.rank, str(skill.path)) < (
                current.rank,
                str(current.path),
            ):
                by_name[skill.name] = skill
    return tuple(sorted(by_name.values(), key=lambda skill: skill.name))


def catalog_text(entries: Sequence[tuple[str, str]], *, budget: int = CATALOG_BUDGET) -> str:
    """把清单渲染成紧凑文本；超预算时截断并留「还有 N 个未列出」。"""
    lines: list[str] = []
    used = 0
    for index, (name, description) in enumerate(entries):
        line = f"- {name}：{description}" if description else f"- {name}"
        cost = len(line) + 1
        if used + cost > budget:
            hidden = len(entries) - index
            lines.append(f"（还有 {hidden} 个技能未列出）")
            break
        lines.append(line)
        used += cost
    return "\n".join(lines)


def render_skill_catalog(skills: Sequence[Skill], *, budget: int = CATALOG_BUDGET) -> str:
    return catalog_text([(skill.name, skill.description) for skill in skills], budget=budget)


def skill_content(skill: Skill, instruction: str = "") -> str:
    """DSH 同形的 XML 三段；`skill` 工具与命令展开共用，避免两处漂移。"""
    body = read_skill_body(skill)
    content = (
        f'<skill_content name="{skill.name}">\n'
        f"<skill_resources>\n- {skill.path}\n</skill_resources>\n"
        f"<skill_instructions>\n{body}\n</skill_instructions>\n"
        f"</skill_content>"
    )
    return content if not instruction else content + "\n\n" + instruction


def read_skill_body(skill: Skill, *, limit: int = BODY_LIMIT) -> str:
    """读正文；超过上限截断并提示用 read 读全文（路径就是它）。"""
    try:
        body = _strip_frontmatter(skill.path.read_text(encoding="utf-8"))
    except OSError as error:
        return f"（读不出技能正文：{error}）"
    if len(body) <= limit:
        return body
    return body[:limit] + f"\n\n…（正文超过 {limit} 字符，已截断；用 read 读全文：{skill.path}）"
