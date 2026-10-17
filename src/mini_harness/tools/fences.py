"""围栏判定：工作区边界 + `--sandbox` 档位 + 派发上下文。只由 harness 自身判定，不做 OS 级强制。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mini_harness.loop.settings import ApprovalMode, SandboxLevel, SessionSettings

FenceCode = Literal[
    "OUTSIDE_WORKSPACE",
    "SANDBOX_DENIES_WRITE",
    "APPROVAL_DENIED",
    "APPROVAL_UNAVAILABLE",
]
FenceOutcome = Literal["ALLOWED", "NEEDS_APPROVAL", "DENIED"]


@dataclass(frozen=True)
class DispatchContext:
    """一次派发能看到的全部事实：工具只读它，不读进程内状态。"""

    workspace: Path
    sandbox: SandboxLevel
    approval: ApprovalMode
    read_paths: frozenset[str]

    @classmethod
    def from_settings(
        cls, settings: SessionSettings, read_paths: frozenset[str]
    ) -> DispatchContext:
        return cls(
            workspace=settings.workspace,
            sandbox=settings.sandbox,
            approval=settings.approval,
            read_paths=read_paths,
        )


@dataclass(frozen=True)
class FenceDecision:
    """围栏段的结论。被拒也是结果，不是异常。"""

    outcome: FenceOutcome
    code: FenceCode | None = None
    detail: str = ""


def path_key(workspace: Path, raw_path: str) -> str:
    """入参路径 → 判定用的键。

    相对工作区根解析；`os.path.realpath` 解析 junction 与符号链接；Windows 上 `normcase` 折叠
    大小写——否则同一个文件换一种写法就能绕过写前必读与 CAS。
    """
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = os.path.realpath(candidate)
    if os.name == "nt":
        resolved = os.path.normcase(resolved)
    return resolved


def _is_inside_workspace(workspace: Path, key: str) -> bool:
    root = Path(path_key(workspace, "."))
    target = Path(key)
    return target == root or target.is_relative_to(root)


def judge_fence(context: DispatchContext, *, raw_path: str, mutates: bool) -> FenceDecision:
    """三段判定里的围栏段：档位 → 工作区边界 → 要不要问人。

    边界只约束会改动的操作；`danger-full-access` 解除边界，但写前必读与 CAS 不在这里判。
    """
    if not mutates:
        return FenceDecision(outcome="ALLOWED")

    if context.sandbox == "read-only":
        return FenceDecision(
            outcome="DENIED",
            code="SANDBOX_DENIES_WRITE",
            detail=f"{context.sandbox} 档位不许可会改动的操作：{raw_path}",
        )

    key = path_key(context.workspace, raw_path)
    if context.sandbox == "workspace-write" and not _is_inside_workspace(context.workspace, key):
        return FenceDecision(
            outcome="DENIED",
            code="OUTSIDE_WORKSPACE",
            detail=f"解析后在工作区之外：{key}",
        )

    if context.approval == "ask":
        return FenceDecision(outcome="NEEDS_APPROVAL", detail=key)

    return FenceDecision(outcome="ALLOWED", detail=key)
