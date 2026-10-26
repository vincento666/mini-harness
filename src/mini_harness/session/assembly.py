"""装配：把「请求 + 环境」塌成一次会话的材料（H1 design D2）。

`run` / `chat` / `serve` / `host` 四个入口共用这一条路。它只回答两件事：材料齐了（`Prepared`），
或者在哪一步失败（`Failure`）。失败是结果不是异常（不变量 B）；所有失败都在 `EventLog.start`
之前，调用方把 `Failure` 映射成 stderr 与退出码，或映射成宿主层的 400 JSON。
"""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mini_harness.config import (
    ConfigFailure,
    build_registry,
    discover_config,
    layer_settings,
    load_config,
)
from mini_harness.context.budget import pressure_budget
from mini_harness.events import EventLog, LogWriteFailure
from mini_harness.loop import (
    APPROVAL_MODES,
    PROVIDER_NAMES,
    SANDBOX_LEVELS,
    ProviderEndpoint,
    SessionSettings,
)
from mini_harness.loop.settings import ApprovalMode
from mini_harness.provider import FixtureLoadFailure, load_fixture_provider
from mini_harness.provider.contract import Provider
from mini_harness.provider.openai_compat import OpenAICompatProvider, validate_base_url
from mini_harness.tools import ToolRegistry
from mini_harness.tools.bash_tools import platform_facts

EXIT_INTERNAL_ERROR = 1
EXIT_INVALID_ARGUMENT = 2


@dataclass(frozen=True)
class AssemblyRequest:
    """一次装配的输入：CLI flag 或宿主请求体，还没有经过层叠与校验。

    哨兵一律是 `None`：`None` 是「这一层没给」，与「显式给了内置默认值」是两层不同的事实。
    `auto_approve` 是 CLI 的 `--yes`；宿主用请求体的 `approval: "auto"` 走同一条判定。
    """

    workspace: str | None = None
    config: str | None = None
    session_dir: str | None = None
    provider: str | None = None
    fixture: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    max_turns: int | None = None
    window: int | None = None
    reserve: int | None = None
    append_system_prompt: str | None = None
    sandbox: str | None = None
    approval: str | None = None
    auto_approve: bool = False


@dataclass(frozen=True)
class Prepared:
    """装配好的会话材料：provider、有效设置、日志、工具表。"""

    provider: Provider
    settings: SessionSettings
    log: EventLog
    registry: ToolRegistry


@dataclass(frozen=True)
class Failure:
    """装配路上的失败：码、面向人的 detail、CLI 退出码。

    宿主层只读 `code` 与 `detail`；`exit_code` 是 CLI 的映射，不是宿主的状态码。
    """

    code: str
    detail: str
    exit_code: int


def _session_dir(value: str | None) -> Path:
    if value is not None:
        return Path(value)
    return Path.cwd() / "sessions"


def assemble(
    request: AssemblyRequest,
    environ: Mapping[str, str],
    *,
    allow_danger_full_access: bool = True,
    allow_auto_approval: bool = True,
) -> Prepared | Failure:
    """参数校验 → 配置层叠 → 装配 → 开日志。

    校验顺序固定：配置 → 窗口 → 工具 → provider/密钥 → 开日志。任何一步失败都不建日志。
    `allow_*` 两个开关是宿主的服务器级许可：CLI 默认全允许（flag 本身就是显式选择），
    host 从 `--allow-danger-full-access` / `--allow-auto-approval` 传进来。
    """
    # 配置文件发现用的工作区是「`--workspace` 或当前目录」这一层，不来自配置文件（design D7）。
    discovery_workspace = Path(request.workspace) if request.workspace is not None else Path.cwd()
    config: dict[str, Any] = {}
    config_path = discover_config(discovery_workspace, request.config)
    if config_path is not None:
        loaded_config = load_config(config_path)
        if isinstance(loaded_config, ConfigFailure):
            return Failure("INVALID_ARGUMENT", loaded_config.detail, EXIT_INVALID_ARGUMENT)
        config = loaded_config
    # 三层塌成一份有效设置：之后的校验与装配只认这一份。`layer_settings` 的入参是
    # 「一层可选字段的袋子」，请求体与 argparse 的 Namespace 同形。
    layered = layer_settings(Namespace(**asdict(request)), config, environ)
    max_turns = layered.max_turns
    provider_name = layered.provider
    if max_turns < 1:
        return Failure(
            "INVALID_ARGUMENT", f"--max-turns 至少为 1，收到 {max_turns}", EXIT_INVALID_ARGUMENT
        )
    if provider_name not in PROVIDER_NAMES:
        return Failure(
            "UNKNOWN_PROVIDER",
            f"--provider 只接受 {' / '.join(PROVIDER_NAMES)}，收到 {provider_name}",
            EXIT_INVALID_ARGUMENT,
        )
    # 围栏两条轴的取值词表由围栏规定：配置文件写错档位不是「运行期再说」，是参数错误。
    for key, level, allowed in (
        ("sandbox", layered.sandbox, SANDBOX_LEVELS),
        ("approval", layered.approval, APPROVAL_MODES),
    ):
        if level not in allowed:
            return Failure(
                "INVALID_ARGUMENT",
                f"{key} 只接受 {' / '.join(allowed)}，收到 {level}",
                EXIT_INVALID_ARGUMENT,
            )
    # 宿主层的服务器级许可：只有服务器启动时显式给了，才允许请求体里的这两档。
    if layered.sandbox == "danger-full-access" and not allow_danger_full_access:
        return Failure(
            "INVALID_ARGUMENT",
            "danger-full-access 需要服务器启动时显式给 --allow-danger-full-access",
            EXIT_INVALID_ARGUMENT,
        )
    approval: ApprovalMode = "auto" if request.auto_approve else layered.approval
    if approval == "auto" and not allow_auto_approval:
        return Failure(
            "INVALID_ARGUMENT",
            "approval: auto 需要服务器启动时显式给 --allow-auto-approval",
            EXIT_INVALID_ARGUMENT,
        )
    # 窗口预算的两个参数在 session 开始之前判掉：非法取值不产生日志（context-budget 规格）。
    for flag, value in (("--window", layered.window), ("--reserve", layered.reserve)):
        if value < 1:
            return Failure(
                "INVALID_ARGUMENT", f"{flag} 至少为 1，收到 {value}", EXIT_INVALID_ARGUMENT
            )
    # 压力预算 `W - O` 非正时没有任何装得下的上下文：照 DSH 这是配置解析期的错误，
    # 不是运行期才发现的溢出（ADR-0019）。触发线为 0 不是配置错误——它只意味着每次装配
    # 都尝试压缩，装得下的读数照样跑完。
    if pressure_budget(layered.window, layered.reserve) <= 0:
        return Failure(
            "INVALID_ARGUMENT",
            f"--window {layered.window} 减去 --reserve {layered.reserve} 之后没有压力预算",
            EXIT_INVALID_ARGUMENT,
        )

    # 工具表从装配来：内置六定义按配置的白名单筛，未知名与别的配置失败同形。
    registry = build_registry(layered.tools)
    if isinstance(registry, ConfigFailure):
        return Failure("INVALID_ARGUMENT", registry.detail, EXIT_INVALID_ARGUMENT)

    provider: Provider
    endpoint: ProviderEndpoint | None = None
    if provider_name != "mock":
        if request.fixture is not None:
            return Failure(
                "INVALID_ARGUMENT",
                f"--provider {provider_name} 不使用 --fixture",
                EXIT_INVALID_ARGUMENT,
            )
        # 密钥只从 --api-key-env 指定的环境变量读：它不进 argv、不进日志、不进 payload。
        # 另两项由预设表保证非空：词表已判过 provider 名字，非 mock 的预设给这两项。
        assert layered.base_url is not None
        assert layered.api_key_env is not None
        invalid = validate_base_url(layered.base_url)
        if invalid is not None:
            return Failure("INVALID_ARGUMENT", invalid, EXIT_INVALID_ARGUMENT)
        # 端点三条在这里塌成一个对象：payload 那三个字段由它派生，不再各判一遍。
        # 密钥是装配的必需项：未设或空串都在 session 开始之前当场失败，一个请求都不发。
        api_key = environ.get(layered.api_key_env)
        if not api_key:
            return Failure(
                "INVALID_ARGUMENT",
                f"环境变量 {layered.api_key_env} 未设置或为空：--provider {provider_name} 需要密钥",
                EXIT_INVALID_ARGUMENT,
            )
        # 补齐之后还可能缺的只有 model：`openai` 预设不给它默认（ADR-0027）。缺它当场失败，
        # 不带着空值去发一个注定打不到的请求。
        if layered.model is None:
            return Failure(
                "INVALID_ARGUMENT",
                f"--provider {provider_name} 需要 --model：{provider_name} 预设不给 model 默认",
                EXIT_INVALID_ARGUMENT,
            )
        endpoint = ProviderEndpoint(
            base_url=layered.base_url,
            model=layered.model,
            api_key_env=layered.api_key_env,
        )
        provider = OpenAICompatProvider(
            base_url=endpoint.base_url,
            model=endpoint.model,
            api_key=api_key,
        )
    else:
        if request.fixture is None:
            return Failure(
                "INVALID_ARGUMENT",
                "--provider mock 需要 --fixture 指向 JSON 数组",
                EXIT_INVALID_ARGUMENT,
            )
        loaded = load_fixture_provider(Path(request.fixture))
        if isinstance(loaded, FixtureLoadFailure):
            return Failure(loaded.code, loaded.detail, EXIT_INVALID_ARGUMENT)
        provider = loaded

    log = EventLog.start(_session_dir(layered.session_dir))
    if isinstance(log, LogWriteFailure):
        return Failure(log.code, log.detail, EXIT_INTERNAL_ERROR)

    settings = SessionSettings(
        workspace=Path(layered.workspace) if layered.workspace is not None else Path.cwd(),
        provider_name=provider_name,
        max_turns=max_turns,
        sandbox=layered.sandbox,
        approval=approval,
        append_system_prompt=layered.append_system_prompt,
        window=layered.window,
        reserve=layered.reserve,
        endpoint=endpoint,
        platform=platform_facts(),
    )
    return Prepared(provider=provider, settings=settings, log=log, registry=registry)
