"""工具表从装配来：内置定义按配置白名单筛，子代理 preset 在这里编译（design D4 / D3）。

preset 的校验与编译只发生在装配期：名字、引用、`allowed_presets` 的白名单关系在这里判掉，
失败与别的配置错误同形（`INVALID_ARGUMENT`、退出码 2、不建日志）。运行期只按 id 取
已经编译好的子工具表——不读磁盘、不读父会话的注册表。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mini_harness.config.load import ConfigCode, ConfigFailure
from mini_harness.skills import Skill
from mini_harness.tools import ToolRegistry
from mini_harness.tools.bash_tools import bash_tool_definitions
from mini_harness.tools.file_tools import file_tool_definitions
from mini_harness.tools.skill import skill_tool_definitions
from mini_harness.tools.subagent import SubagentPresets, subagent_tool_definitions

_SUBAGENT_KEYS = frozenset({"preset", "allowed_presets", "presets"})
_PRESET_KEYS = frozenset({"tools", "persona", "skills"})
# preset 的 skills 是一张挂 provider 的表；现在只有 filesystem 一种（ADR-0040）。
_PRESET_SKILL_KEYS = frozenset({"kind", "dirs"})
SKILL_KINDS = frozenset({"filesystem"})


def _invalid(detail: str, code: ConfigCode = "CONFIG_INVALID_VALUE") -> ConfigFailure:
    return ConfigFailure(code, detail)


def _names_joined(names: Sequence[str]) -> str:
    return " / ".join(names)


def _presets(
    value: Mapping[str, Any], known_tools: frozenset[str], skills: Sequence[Skill]
) -> SubagentPresets | ConfigFailure:
    """`[subagent]` 段 → 已编译的 preset 表；任何形状/引用错误都是配置失败。"""
    unknown = sorted(set(value) - _SUBAGENT_KEYS)
    if unknown:
        return _invalid(f"[subagent] 里有未知的键：{_names_joined(unknown)}", "CONFIG_UNKNOWN_KEY")

    default = value.get("preset")
    if default is not None and not isinstance(default, str):
        return _invalid("[subagent] preset 必须是字符串")
    if isinstance(default, str) and not default:
        return _invalid("[subagent] preset 不能是空字符串")

    allowed_raw = value.get("allowed_presets")
    if allowed_raw is not None and (
        not isinstance(allowed_raw, list)
        or not allowed_raw
        or not all(isinstance(item, str) and item for item in allowed_raw)
    ):
        return _invalid("[subagent] allowed_presets 必须是非空字符串数组")

    raw_presets = value.get("presets", {})
    if not isinstance(raw_presets, dict):
        return _invalid("[subagent] presets 必须是一张表")
    tool_names: dict[str, tuple[str, ...]] = {}
    personas: dict[str, str] = {}
    skill_dirs: dict[str, tuple[str, ...]] = {}
    for preset_id, spec in raw_presets.items():
        if not isinstance(preset_id, str) or not preset_id:
            return _invalid("[subagent.presets] 的 id 必须是非空字符串")
        if not isinstance(spec, dict):
            return _invalid(f"[subagent.presets.{preset_id}] 必须是一张表")
        extra = sorted(set(spec) - _PRESET_KEYS)
        if extra:
            return _invalid(
                f"[subagent.presets.{preset_id}] 里有未知的键：{_names_joined(extra)}",
                "CONFIG_UNKNOWN_KEY",
            )
        tools = spec.get("tools")
        if not isinstance(tools, list) or not all(isinstance(item, str) for item in tools):
            return _invalid(f"[subagent.presets.{preset_id}].tools 必须是字符串数组")
        unknown_tools = sorted({name for name in tools if name not in known_tools})
        if unknown_tools:
            return _invalid(
                f"preset {preset_id} 里有未注册的工具名：{_names_joined(unknown_tools)}",
                "UNKNOWN_TOOL_NAME",
            )
        skills_spec = spec.get("skills")
        if skills_spec is not None and not isinstance(skills_spec, dict):
            return _invalid(f"[subagent.presets.{preset_id}].skills 必须是一张表")
        if isinstance(skills_spec, dict):
            extra_skill_keys = sorted(set(skills_spec) - _PRESET_SKILL_KEYS)
            if extra_skill_keys:
                return _invalid(
                    f"[subagent.presets.{preset_id}].skills 里有未知的键："
                    f"{_names_joined(extra_skill_keys)}",
                    "CONFIG_UNKNOWN_KEY",
                )
            kind = skills_spec.get("kind")
            if kind not in SKILL_KINDS:
                return _invalid(
                    f"[subagent.presets.{preset_id}].skills.kind 只接受 "
                    f"{_names_joined(sorted(SKILL_KINDS))}"
                )
            dirs = skills_spec.get("dirs")
            if not isinstance(dirs, list) or not all(isinstance(item, str) for item in dirs):
                return _invalid(f"[subagent.presets.{preset_id}].skills.dirs 必须是字符串数组")
            skill_dirs[preset_id] = tuple(dirs)
        persona = spec.get("persona")
        if persona is not None and not isinstance(persona, str):
            return _invalid(f"[subagent.presets.{preset_id}].persona 必须是字符串")
        if isinstance(persona, str) and persona:
            personas[preset_id] = persona
        tool_names[preset_id] = tuple(tools)

    if default is not None and default not in tool_names:
        return _invalid(f"[subagent] preset {default} 不在 presets 里")
    allowed: tuple[str, ...] = tuple(allowed_raw or ())
    missing = [item for item in allowed if item not in tool_names]
    if missing:
        return _invalid(f"allowed_presets 里有未定义的 preset：{_names_joined(missing)}")
    if default is not None and allowed and default not in allowed:
        return _invalid(f"[subagent] preset {default} 不在 allowed_presets 里")

    # registries 先建空表再填充：subagent 自己的定义持有同一个 dict 的引用，递归包含
    # `subagent` 的 preset 因此也能建出（深度上限仍会挡住真正的递归调用）。
    registries: dict[str, ToolRegistry] = {}
    presets = SubagentPresets(
        default=default,
        allowed=allowed,
        registries=registries,
        personas=personas,
        skill_dirs=skill_dirs,
    )
    catalog = [
        *file_tool_definitions(),
        *bash_tool_definitions(),
        *subagent_tool_definitions(presets),
        *skill_tool_definitions(skills),
    ]
    for preset_id, names in tool_names.items():
        registries[preset_id] = ToolRegistry([tool for tool in catalog if tool.name in names])
    return presets


def build_registry(
    whitelist: Sequence[str] | None,
    subagent: Mapping[str, Any] | None = None,
    skills: Sequence[Skill] = (),
) -> ToolRegistry | ConfigFailure:
    """内置六定义（五个文件工具加 `bash`）；`None` 是全开，给了白名单就按内置顺序筛。

    白名单里的未知名是一条配置失败：工具表不会悄悄少一个，也不会悄悄多一个。
    `subagent` 是 `[subagent]` 段：给了就编译成 preset 表并挂到 `subagent` 工具上。
    """
    known_tools = frozenset(tool.name for tool in subagent_tool_definitions())
    known_tools = known_tools | frozenset(tool.name for tool in file_tool_definitions())
    known_tools = known_tools | frozenset(tool.name for tool in bash_tool_definitions())
    known_tools = known_tools | frozenset(tool.name for tool in skill_tool_definitions(skills))

    presets: SubagentPresets | None = None
    if subagent is not None:
        parsed = _presets(subagent, known_tools, skills)
        if isinstance(parsed, ConfigFailure):
            return parsed
        presets = parsed

    definitions = [
        *file_tool_definitions(),
        *bash_tool_definitions(),
        *subagent_tool_definitions(presets),
        *skill_tool_definitions(skills),
    ]
    if whitelist is None:
        return ToolRegistry(definitions)
    known = {tool.name for tool in definitions}
    for name in whitelist:
        if name not in known:
            return ConfigFailure("UNKNOWN_TOOL_NAME", f"工具白名单里有未注册的名字：{name}")
    kept = set(whitelist)
    return ToolRegistry([tool for tool in definitions if tool.name in kept])
