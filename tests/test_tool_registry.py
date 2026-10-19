"""seam ②：注册表的内容、结果词表、三段派发的顺序。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

from mini_harness.tools.fences import ApprovalDecision, DispatchContext
from mini_harness.tools.file_tools import file_tool_definitions
from mini_harness.tools.registry import (
    ToolArgs,
    ToolDefinition,
    ToolOutcome,
    ToolRegistry,
    ToolResult,
)
from tool_harness import dispatch_call

_FIVE_TOOLS = ["read", "write", "edit", "glob", "grep"]
_FIVE_MUTATES = [False, True, True, False, False]

_RAN: list[Any] = []


class _StubArgs(ToolArgs):
    file_path: str

    def target_path(self) -> str | None:
        return self.file_path


class _ApprovingGate:
    def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        return "APPROVED"


async def _stub_run(args: Any, context: DispatchContext) -> ToolResult:
    _RAN.append(args)
    return ToolResult(outcome="OK", content="执行了")


def _stub_registry(*, mutates: bool) -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="stub",
                description="测试桩工具",
                args_model=_StubArgs,
                mutates=mutates,
                run=_stub_run,
            )
        ]
    )


def test_the_registry_holds_exactly_the_five_file_tools() -> None:
    definitions = file_tool_definitions()
    registry = ToolRegistry(definitions)

    assert [tool.name for tool in definitions] == _FIVE_TOOLS
    assert [tool.mutates for tool in definitions] == _FIVE_MUTATES
    assert all(tool.description and tool.args_model is not None for tool in definitions)
    assert all(tool.run is not None for tool in definitions)
    assert [(spec.name, spec.description) for spec in registry.specs()] == [
        (tool.name, tool.description) for tool in definitions
    ]
    assert all(
        set(spec.model_dump()) == {"name", "description", "parameters"} for spec in registry.specs()
    )


def test_the_parameter_schema_a_model_sees_comes_from_the_dispatch_side_model() -> None:
    """工具面的参数 schema 由派发侧的 `args_model` 派生，不是手搓的第二份描述。"""
    definitions = file_tool_definitions()
    registry = ToolRegistry(definitions)
    by_name = {spec.name: spec for spec in registry.specs()}

    for tool in definitions:
        parameters = by_name[tool.name].parameters
        assert parameters == tool.args_model.model_json_schema()
        assert parameters["type"] == "object"
        assert parameters["properties"]
        assert tool.name in {"read", "write", "edit", "glob", "grep"}


def test_the_outcome_vocabulary_has_sixteen_values_and_no_not_implemented() -> None:
    outcomes = set(get_args(ToolOutcome))

    assert len(outcomes) == 16
    assert "NOT_IMPLEMENTED" not in outcomes
    required = {
        "DENIED_BY_FENCE",
        "DENIED_BY_APPROVAL",
        "UNKNOWN_TOOL",
        "TOOL_ARGS_INVALID",
        "TOOL_IO_FAILED",
        "TOOL_TIMEOUT",
        "TOOL_CANCELLED",
        "NOT_A_DIRECTORY",
    }
    assert required <= outcomes


async def test_invalid_arguments_skip_both_the_fence_and_the_execution(tmp_path: Path) -> None:
    _RAN.clear()
    outcome = await dispatch_call(
        tmp_path,
        "stub",
        {},
        sandbox="read-only",
        approval="ask",
        registry=_stub_registry(mutates=True),
        approval_gate=_ApprovingGate(),
    )

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert outcome.fence_code is None
    assert outcome.approval is None
    assert _RAN == []


async def test_a_fence_denial_skips_the_execution(tmp_path: Path) -> None:
    _RAN.clear()
    outcome = await dispatch_call(
        tmp_path,
        "stub",
        {"file_path": "../outside.md"},
        registry=_stub_registry(mutates=True),
        approval_gate=_ApprovingGate(),
    )

    assert outcome.result.outcome == "DENIED_BY_FENCE"
    assert outcome.fence_code == "OUTSIDE_WORKSPACE"
    assert _RAN == []


async def test_invalid_arguments_are_caught_before_the_fence_is_consulted(tmp_path: Path) -> None:
    """入参不合法且路径越界时，报的是校验段的 `TOOL_ARGS_INVALID`，不是围栏段的拒绝。"""
    outcome = await dispatch_call(tmp_path, "write", {"file_path": "../outside.md", "content": 7})

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert outcome.fence_code is None
