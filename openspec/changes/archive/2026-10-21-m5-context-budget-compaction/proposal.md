# Proposal

## Why

不变量 D（窗口预算与显式溢出错误）至今没有兑现：`fold` 把全部历史折进上下文，`cli` 把退出码 4 写成保留码。一次长 run 只会在 provider 侧撞墙——mini 既不知道这份上下文有多贵，也没有「贵到不能继续」这个结果。M5 把预算、触发线、遮蔽式压缩与 `CONTEXT_WINDOW_EXCEEDED` 一次立起来。

## What Changes

- 新增窗口预算：`--window`（默认 128000）与 `--reserve`（默认 8192），有效值进 `session/start` 的 payload。
- 新增触发线 `floor(min(W × 0.8, W − O − 65536))`，照抄 DSH 的 `DEFAULT_THRESHOLD_RATIO = .8` 与 `headroomTokens ?? 65536`。预算读数取「本次折叠上下文的 `len ÷ 4` 估算」与「该日志前缀里 provider 回报过的最大 `input_tokens`」的较大者。
- 新增遮蔽式压缩：越线时调模型生成摘要，写**一条** `compaction/summary`，payload 带 `shadowed_range{start, end}`、摘要文本、压缩前后的估算 token。原文事件不删、不改、不重排。
- 折叠读方 honor 遮蔽：被覆盖的记录不产出消息；摘要作为受保护头部之后的 `system` 消息进入表层；多次压缩按写入顺序累积。
- **BREAKING** 新增 `CONTEXT_WINDOW_EXCEEDED` 停止理由，退出码 4 从保留码变可达码。两条触发路径产出同一个结果：压缩之后估算仍超线（兜底），或 provider 报出上下文超限（新失败码 `PROVIDER_CONTEXT_OVERFLOW`，不重试）。两条都写 `error/context`。
- 回合五步不变；压缩段落在「折叠装配」之内、`context/assembled` 之前。
- 收 ADR-0002 第 5 条的剩余部分：`StopReason` 加这一个值，并补「每个值可达」判据。

## Capabilities

### New Capabilities

- `context-budget`: 窗口预算与触发线公式、预算读数的两个来源、压缩触发的时机、压缩救不了时的溢出结果。

### Modified Capabilities

- `context-projection`: 折叠如何 honor 遮蔽与摘要；移除「M1 不施加窗口预算与截断」这条阶段性限定。
- `event-log`: 事件词表加 `compaction/summary` 与 `error/context`。
- `turn-loop`: 停止判定词表加 `CONTEXT_WINDOW_EXCEEDED`；压缩段在回合内的落盘位置。
- `provider`: 新增 `PROVIDER_CONTEXT_OVERFLOW`——上下文超限的 400 不重试、不塌成 `PROVIDER_HTTP_STATUS`。
- `cli`: `run` 的参数表加 `--window` / `--reserve`；`session/start` payload 加 `window` / `reserve`；退出码表里 4 变可达。

## 明确不做

- **不做单条工具结果的剪枝**（DSH 的 `dsh-compaction-tool-result-pruner`：超 8192 字符保头 4096 尾 1024）。它动的是工具管线，与 M10 的「管线加段」撞车；记账进 ADR-0002。
- 不做图片 offload（mini 没有图片输入）、不做 spill（超限工具文本外置成文件）、不做 `/compact` 命令（那是 M6 的 REPL 面）。
- 不做 token 计量的服务化、投影缓存或检查点：每次装配现算，DSH 的 `dsh-token-meter` 是 replay-aware 服务，mini 故意简化。
- 不做 `--headroom` 开关：65536 是实现常量（同并发额度 8 那条规矩）。
- 不做压缩范围覆盖 `session/start`：DSH 保护的是 node 0（system/message），mini 的头部与用户 prompt 都从 `session/start` 一条记录派生，覆盖它等于拆掉头部。差异与代价落 ADR。
- 不做 provider 缓存复用、不做压缩策略的可配置化。既有「始终不做」项照旧。

## Impact

- 代码：`events/fold.py`（遮蔽与摘要进表层）、`events/vocabulary.py`（两个新类型）、`loop/turn_loop.py`（压缩段、新 `StopReason`）、`loop/settings.py` 与 `cli/main.py`（两个参数、退出码 4）、`provider/openai_compat.py`（新失败码）、新建 `context/budget.py`。
- 测试：seam ① ② ④ ⑤ ⑥ 各加一组判据，`tests/fixtures/scenarios/` 加压缩场景，词表可达性判据扩到新值。
- 文档：新 ADR 三份（遮蔽的形状、预算读数与两条触发路径、压缩范围不覆盖 `session/start`）；ADR-0002 追加剪枝记账，并把指向 M5 的旧指针按 M5 的实际范围改判——那些「处理时点：M5」写于「M5 是 REPL」的旧分期。
- 基线会变：236 passed / 2 skipped 与 `TOTAL 1167 53 95%` 是本轮起点，不是终点。
