"""seam ②：子代理 preset 的配置校验与编译（`[subagent]` 段）。

编译发生在装配期：形状、引用与工具名在这里判掉；运行期只按 id 取编译好的表。
"""

from __future__ import annotations

from typing import Any

from mini_harness.config import ConfigFailure, build_registry
from mini_harness.tools import ToolRegistry


def _props(config: dict[str, Any] | None) -> dict[str, Any]:
    registry = build_registry(None, config)
    assert isinstance(registry, ToolRegistry)
    definition = registry.lookup("subagent")
    assert definition is not None
    properties = definition.args_model.model_json_schema()["properties"]
    return dict(properties)


def _enum(schema: dict[str, Any]) -> set[str]:
    prop = schema["agent_preset"]
    values = set(prop.get("enum", []))
    for alternative in prop.get("anyOf", []):
        values |= set(alternative.get("enum", []))
    return values


def test_presets_are_compiled_and_the_tools_argument_is_gone() -> None:
    properties = _props({"preset": "reader", "presets": {"reader": {"tools": ["read", "glob"]}}})

    assert "tools" not in properties
    # 没有白名单：字段不出现，模型不能选 preset（默认档仍然生效）。
    assert "agent_preset" not in properties


def test_the_whitelist_becomes_an_enum() -> None:
    properties = _props(
        {
            "allowed_presets": ["reader", "writer"],
            "presets": {"reader": {"tools": ["read"]}, "writer": {"tools": ["write"]}},
        }
    )

    assert _enum(properties) == {"reader", "writer"}


def test_a_preset_may_include_the_subagent_tool() -> None:
    registry = build_registry(
        None, {"preset": "loop", "presets": {"loop": {"tools": ["subagent"]}}}
    )

    assert isinstance(registry, ToolRegistry)


def test_a_preset_persona_is_accepted() -> None:
    registry = build_registry(
        None,
        {"preset": "reviewer", "presets": {"reviewer": {"tools": ["read"], "persona": "严格"}}},
    )

    assert isinstance(registry, ToolRegistry)


def test_an_empty_subagent_section_is_legal() -> None:
    assert isinstance(build_registry(None, {}), ToolRegistry)


def test_invalid_subagent_configs_are_failures() -> None:
    cases: list[tuple[dict[str, Any], str]] = [
        ({"unknown": 1}, "CONFIG_UNKNOWN_KEY"),
        ({"preset": "reader", "presets": {}}, "CONFIG_INVALID_VALUE"),
        ({"allowed_presets": ["reader"]}, "CONFIG_INVALID_VALUE"),
        ({"allowed_presets": []}, "CONFIG_INVALID_VALUE"),
        ({"preset": ["reader"]}, "CONFIG_INVALID_VALUE"),
        ({"presets": "reader"}, "CONFIG_INVALID_VALUE"),
        ({"presets": {"reader": {"tools": ["web_search"]}}}, "UNKNOWN_TOOL_NAME"),
        ({"presets": {"reader": {"persona": 1}}}, "CONFIG_INVALID_VALUE"),
        ({"presets": {"reader": {"tools": "read"}}}, "CONFIG_INVALID_VALUE"),
        ({"presets": {"": {"tools": []}}}, "CONFIG_INVALID_VALUE"),
        (
            {
                "preset": "reader",
                "allowed_presets": ["writer"],
                "presets": {"reader": {"tools": ["read"]}, "writer": {"tools": ["write"]}},
            },
            "CONFIG_INVALID_VALUE",
        ),
    ]

    for value, code in cases:
        result = build_registry(None, value)
        assert isinstance(result, ConfigFailure), value
        assert result.code == code, (value, result.code)
