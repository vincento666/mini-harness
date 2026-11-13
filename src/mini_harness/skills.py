"""技能发现与正文读取（M14 / skill-invocation-policy）。

四级根、kebab-case、必填 description、两个调用策略位、发现完整性与 preset 目录层。
发现发生在装配期；清单进 `session/start.payload.skills` 与受保护头部，正文只在
`skill` 工具被调用时读，并作为 `tool/result` 落日志（不变量 A：回放只认日志）。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

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
# preset 层排在最前：同名直接胜出，rank 只在层内裁决。
RANK_PRESET_LAYER = 50

# DSH 的宽松布尔：大小写不敏感的 true/false、yes/no、on/off、1/0。
_TRUE_WORDS = frozenset({"true", "yes", "on", "1"})
_FALSE_WORDS = frozenset({"false", "no", "off", "0"})


@dataclass(frozen=True)
class Skill:
    """发现到的一个技能：清单字段、正文路径与两个独立的调用策略位。"""

    name: str
    description: str
    rank: int
    path: Path
    model_invocable: bool = True
    user_invocable: bool = True
    # 来自哪一层（project / project-shared / user / bundled / preset:<id>）；
    # 只做审计与目录提示，不参与胜出裁决。
    source: str = ""


@dataclass(frozen=True)
class SkillDiscovery:
    """一次发现的清单与是否完整（根目录扫不动即不完整）。"""

    skills: tuple[Skill, ...]
    complete: bool


def _frontmatter(text: str) -> dict[str, str]:
    """只认清单需要的四个键，按 `key: value` 解析（不引入 YAML）。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() in {
            "name",
            "description",
            "disable-model-invocation",
            "user-invocable",
        }:
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


def _policy(raw: str | None, *, default: bool) -> bool | None:
    """缺省由调用方给；宽松布尔；非法拼写返回 None（丢弃整个技能）。"""
    if raw is None:
        return default
    word = raw.strip().lower()
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    return None


def _skill_at(path: Path, rank: int, source: str) -> Skill | None:
    """读一个候选文件；任何不合法都是「没有这个技能」，不抛。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fields = _frontmatter(text)
    name = fields.get("name")
    description = (fields.get("description") or "").strip()
    if not name or KEBAB_CASE.fullmatch(name) is None or not description:
        return None
    model_disabled = _policy(fields.get("disable-model-invocation"), default=False)
    user_invocable = _policy(fields.get("user-invocable"), default=True)
    if model_disabled is None or user_invocable is None:
        return None
    model_invocable = not model_disabled
    return Skill(
        name=name,
        description=description[:DESCRIPTION_MAX],
        rank=rank,
        path=path,
        model_invocable=model_invocable,
        user_invocable=user_invocable,
        source=source,
    )


def _scan(root: Path, rank: int, source: str) -> tuple[list[Skill], bool]:
    """一个根下的技能：目录式 `<name>/SKILL.md` 或扁平 `<name>.md`，不递归。

    返回 (技能, 完整)；目录本身扫不动才不完整，单个文件坏掉只跳过。
    """
    if not root.is_dir():
        return [], True
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return [], False
    found: list[Skill] = []
    for entry in entries:
        if entry.is_dir():
            candidate = entry / "SKILL.md"
            if not candidate.is_file():
                continue
        elif entry.suffix == ".md" and entry.is_file():
            candidate = entry
        else:
            continue
        skill = _skill_at(candidate, rank, source)
        if skill is not None:
            found.append(skill)
    return found, True


def skill_roots(workspace: Path, environ: Mapping[str, str]) -> list[tuple[int, Path, str]]:
    """四个根与它们的 rank；`MINIHNS_HOME` 没给就用 `~/.mini-harness`。"""
    home = Path(environ.get(HOME_ENV) or Path.home() / DEFAULT_HOME_DIR)
    return [
        (RANK_PROJECT, workspace / ".minihns" / "skills", "project"),
        (RANK_PROJECT_SHARED, workspace / ".agents" / "skills", "project-shared"),
        (RANK_USER, home / "skills", "user"),
        (RANK_BUNDLED, Path(__file__).parent / BUNDLED_DIR, "bundled"),
    ]


def discover_skills(workspace: Path, environ: Mapping[str, str]) -> SkillDiscovery:
    """四级根合并：同名取 rank 小者（并列取路径小者），结果按名字排序。"""
    by_name: dict[str, Skill] = {}
    complete = True
    for rank, root, source in skill_roots(workspace, environ):
        found, ok = _scan(root, rank, source)
        complete = complete and ok
        for skill in found:
            current = by_name.get(skill.name)
            if current is None or (skill.rank, str(skill.path)) < (
                current.rank,
                str(current.path),
            ):
                by_name[skill.name] = skill
    return SkillDiscovery(
        skills=tuple(sorted(by_name.values(), key=lambda skill: skill.name)),
        complete=complete,
    )


def discover_skill_layer(directories: Sequence[Path], source: str = "") -> SkillDiscovery:
    """一个 scope 层：按目录顺序扫入，层内先到先得；complete 取与。"""
    skills, complete = merge_skill_layer((), directories, source)
    return SkillDiscovery(skills, complete)


def merge_skill_layer(
    base: Sequence[Skill], directories: Sequence[Path], source: str = ""
) -> tuple[tuple[Skill, ...], bool]:
    """preset 层：按目录顺序扫入，同名直接覆盖全局；层内先到先得。"""
    by_name = {skill.name: skill for skill in base}
    layer_seen: set[str] = set()
    complete = True
    for index, directory in enumerate(directories):
        found, ok = _scan(directory, RANK_PRESET_LAYER + index, source)
        complete = complete and ok
        for skill in found:
            if skill.name in layer_seen:
                continue
            layer_seen.add(skill.name)
            by_name[skill.name] = skill
    return tuple(sorted(by_name.values(), key=lambda skill: skill.name)), complete


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


def catalog_digest(skills: Sequence[Skill], complete: bool) -> str:
    """模型目录的指纹：模型可调 `(name, description, source)` + 完整性。"""
    entries = [
        (skill.name, skill.description, skill.source) for skill in skills if skill.model_invocable
    ]
    payload = json.dumps(
        {"entries": entries, "complete": complete}, ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_catalog_message(skills: Sequence[Skill], complete: bool) -> str:
    """DSH 同形的目录消息：只放名字 + 转义描述，结尾要求先加载再行动。"""
    entries = [
        (skill.name, skill.description[:DESCRIPTION_MAX], skill.source)
        for skill in skills
        if skill.model_invocable
    ]
    if not entries:
        if complete:
            return (
                "<system-reminder>\n"
                "本会话当前没有可用技能。不要使用之前目录里的技能名。\n"
                "</system-reminder>"
            )
        return (
            "<system-reminder>\n"
            "这次发现一个技能都没确认到。等下一次目录更新再调用 `skill`；"
            "不要凭空目录推断。\n"
            "</system-reminder>"
        )
    lines = [
        f"- `{name}`（{escape(source)}）: {escape(description)}"
        if source
        else f"- `{name}`: {escape(description)}"
        for name, description, source in entries
    ]
    parts = [
        "<system-reminder>",
        "技能是一组可复用的任务指令。本会话可用的技能如下：",
        "",
        "<available_skills>",
        *lines,
        "</available_skills>",
    ]
    if not complete:
        parts += ["", "（有一些技能目录没能检查到，只列确认的；下一次会重试。）"]
    parts += [
        "",
        "如果用户点名一个技能，或任务明显匹配某个技能的描述，"
        "先调用 `skill` 工具加载它的完整指令再行动。目录只是摘要，不要凭摘要推断技能内容。",
        "</system-reminder>",
    ]
    return "\n".join(parts)


def read_skill_body(skill: Skill, *, limit: int = BODY_LIMIT) -> str:
    """读正文；超过上限截断并提示用 read 读全文（路径就是它）。"""
    try:
        body = _strip_frontmatter(skill.path.read_text(encoding="utf-8"))
    except OSError as error:
        return f"（读不出技能正文：{error}）"
    if len(body) <= limit:
        return body
    return body[:limit] + f"\n\n…（正文超过 {limit} 字符，已截断；用 read 读全文：{skill.path}）"


def skill_content_body(skill: Skill, body: str, instruction: str = "") -> str:
    """用给定的正文渲染 XML 三段（注册表的 `get` 提供正文时用）。"""
    content = (
        f'<skill_content name="{skill.name}">\n'
        f"<skill_resources>\n- {skill.path}\n</skill_resources>\n"
        f"<skill_instructions>\n{body}\n</skill_instructions>\n"
        f"</skill_content>"
    )
    return content if not instruction else content + "\n\n" + instruction


def skill_content(skill: Skill, instruction: str = "") -> str:
    """DSH 同形的 XML 三段；`skill` 工具与命令展开共用，避免两处漂移。"""
    return skill_content_body(skill, read_skill_body(skill), instruction)
