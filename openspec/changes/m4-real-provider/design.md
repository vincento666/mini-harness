# Design

## Context

见 proposal.md - Why。设计要处理的既有事实：`Provider` 契约只有一个方法（`provider/contract.py::generate`），Provider 拿不到 `EventLog`；`ToolSpec` 只有 `name` 与 `description`，参数形状只存在于注册表的 `args_model`；`AssistantTurn.finish_reason` 是记录、分支看 `tool_calls`；取消只在回合边界被看到（ADR-0002 第 10 条）；`model/retry` 在事件词表里已预留但 M2 明确不写。本机事实：`DEEPSEEK_API_KEY` 未设；本地端点 `http://127.0.0.1:8088/v1`（qqz-adapter 薄转发到 llama.cpp :8080，`tools` 与 `tool_calls` 原样透传）需要先起服务才可达。

## Goals / Non-Goals

**Goals:**

- 让真实模型成为 `Provider` 契约的第二个实现，且回合循环一行都不改。
- 让模型看到的工具面与派发侧的参数模型同源。
- 让「重试」这件事在日志里可见，而不是只留在 stderr。

**Non-Goals:**

- 不做流式解析、不做可配置重试策略、不做 `tool_choice`、不做 usage 预算（M5）。
- 不改取消语义：ADR-0002 第 10 条那条欠账仍留给 M3。
- 不把真实 provider 判据放进 CI 或门禁全量。

## Decisions

**D1 适配器是一个类、一个方法，HTTP 层可注入。** `provider/openai_compat.py` 实现 `generate`；构造入参是 base_url、model、api_key、超时常量，HTTP 客户端由外部注入（测试注入假 HTTP 层，生产注入 httpx 异步客户端）。备选：适配器内部自己建连接（否：seam ⑤ 的判据就得跑网络，门禁与 CI 依赖外部服务）。**httpx 只允许出现在这一个模块**——其它模块 import httpx 就是把外部依赖漏进内核，seam 边界守这条。

**D2 `ToolSpec` 加 `parameters`，由注册表的参数模型派生。** 单一真源是 `args_model` 的 JSON Schema；注册表在装配工具面时派生。备选：每个工具手写一份 schema（否：两份真源必然漂移，而漂移的后果是模型产出派发侧拒绝的参数，看起来像模型的错）。

**D3 Provider 不写日志；重试事实由返回值带回。** `ProviderFailure` 增加「重试过哪些状态码」这一项，回合循环据此写 `model/retry`（一次重试一条），再写 `error/model`。备选：适配器直接拿 `EventLog` 写事件（否：违反不变量 A「日志唯一真源由内核追加」，且 provider 变成有副作用的组件、mock 与真实不再同形）。

**D4 超时塌成失败结果，取消只在入口检查。** `generate` 入口先查 `signal`，已置位就不发请求；请求超时塌成 `PROVIDER_TIMEOUT` 的 `ProviderFailure`。备选：请求中途中断（否：那是 M3 的进程级取消，M4 不碰）。

**D5 provider 选择在 CLI，密钥判定用 base-url 的 host。** 默认仍是 `mock`；`openai` 时若 `DEEPSEEK_API_KEY` 未设且 host 不是 loopback 就在 session 开始之前以退出码 2 失败。备选：不预判、等 401 塌成 `PROVIDER_HTTP_STATUS`（否：那是退出码 1 的「模型错误」，而缺密钥是参数错误，且日志已经建了）。

**D6 测试策略与 seam 边界（不新增 seam）。** seam ⑤：假 HTTP 层驱动全部适配器判据（请求形状、`tool_calls` 解析、429/5xx 重试一次、400 不重试、超时、200 但响应体不合法）。seam ①：重试事件的位置与条数、一轮多调用被派发。seam ②：工具面 schema 与 `args_model` 同源。seam ⑥：真实子进程跑 `--provider openai`，参数校验类判据不发请求；「loopback 免密钥」那条用一个测试自己起的 loopback 假 server（真 socket、真 HTTP，但不依赖外部服务）。真实端点跑通是**人手验收**，记进 `docs/verification/m4-real-provider-manual.md`，不进 CI。

**D7 非流式。** 一次请求拿完整回复，`model/response` 一条记录。代价：长回复没有增量事件，M7 的 SSE 才处理流式。备选：流式（否：M4 的判据没有一条需要增量，而流式让重试语义变复杂）。

**D8 先本地端点、后 DeepSeek。** 第一个跑通目标是 loopback 端点（无密钥、可反复跑、零成本），DeepSeek 是收尾的真实 smoke。理由与代价见 ADR-0005；端点选择本身要另落一份 ADR（0006），把「mini 版相对 DSH 的简化」与「本地端点先跑通」写清。

## Risks / Trade-offs

- [本地 GGUF 的 chat template 可能不产出 `tool_calls`] → tasks 第 1 节先探测端点（带 `tools` 的最小请求），探不通就先换端点再写判据；不先写死适配器。
- [27B 本地模型响应慢，可能撞超时常量] → 超时取值写进常量并在人手验收里记录实测；MUST NOT 为此加命令行开关（规 2）。
- [`model/retry` 进词表后 replay 要能折叠它] → 折叠把它当事实记录、不影响上下文装配；seam ④ 补一条判据钉住「replay 对含 `model/retry` 的日志仍逐点相等」。
- [httpx 成为运行时依赖] → 只允许 D1 那一处 import；`pyproject.toml` 与 AGENTS.md 技术选型那行同步更新（人已裁决）。
- [真实模型的输出进日志] → 沿用现有规则，`session/start` payload MUST NOT 含密钥；日志里出现模型原文不是新问题（mock 也写原文）。

## Open Questions

- `usage` 是否进 `turn/end` 或 `context/assembled`：M5 才用到，M4 只保证适配器把响应的 usage 转进 `AssistantTurn`。
- 超时常量要不要暴露成命令行参数：先固定，等 M3 的超时语义定了再议。
