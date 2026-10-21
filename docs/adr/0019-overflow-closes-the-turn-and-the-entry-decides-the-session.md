---
status: accepted
---

# 溢出只塌到回合级；provider 报出的超限先压缩一次再重试一次

DSH 的 `compactIfNeeded` 跑在 `agent/pre-step`，压缩失败只 warn 并继续这个 turn；provider 报出的上下文超限走 `agent/request-error`，先做一次请求级压缩再重试那一次请求，上限 `maxOverflowRetries` 默认 1，救不动才把原始错误留给上层。mini 照这个做法，并把它写成两条判据：**窗口预算不成立是启动期参数错误**——`window − reserve − 65536 ≤ 0` 当场退出码 2、不建 session 日志（DSH 的 `pressureBudgetTokens <= 0` 也是在配置解析时就抛 `TargetPressureConfigError`，不是运行期才发现）；**provider 报出的超限先救一次**——先做一次请求级压缩，有可遮蔽内容就写 `compaction/summary`、重新折叠、重试那一次请求，上限一次；无可遮蔽内容 / 那一次用完 / 重试仍失败，三条塌成同一个溢出结果，且不写 `error/model`。同时把收尾的**层级**定下来：内核只写 `error/context` + `turn/end(CONTEXT_WINDOW_EXCEEDED)` + `segment/end(CONTEXT_WINDOW_EXCEEDED)`，`session/end` 与退出码归入口——`run` 塌成 4，`chat` 回到提示符。

Considered options：照 DSH 那样「压缩失败 warn 并继续这个 turn」（否：mini 还没有「在一个没有预算的回合里继续」那条路，它要先有 M10 / M11 的压缩失败策略，记进 ADR-0002）；把 `maxOverflowRetries` 做成参数（否：它是实现常量，照 DSH 的默认 1，窗口参数 `--window` / `--reserve` 两个够了）；chat 也塌成退出码 4（否：那等于一条长输入杀死整个会话，与「一次 chat 是一个连续会话」直接矛盾）。

Consequences：ADR-0016 里「两条触发路径塌成同一个结果」那句里的「+ 退出码 4」只成立于 `run` 入口，退出码那一半由本条接管。请求级压缩与装配内的压缩是两次不同的尝试：一次装配最多一次装配内压缩，请求级压缩另计、上限一次。chat 的 stdout 是「每段跑完读回日志再打印」的投影，不是流式；工具事件的终端投影与进度归 M7 之后（记在 ADR-0002）。

**收尾轮的裁决（2026-10-21，人）：重试之前补一条 `context/assembled`。** 请求级压缩之后那次重试发出去的是遮蔽之后重新折叠的表层，日志里此前只有该回合装配点那一条快照——「日志说的不是实际发出去的」。裁决走「实现补快照」：重试之前写一条 `context/assembled`（内容 = 遮蔽之后的前缀折叠，重放方按前缀重算照样逐字段相等）；带 `purpose: compaction` 的摘要调用不写快照，规格写明它的上下文是「该回合表层加一条固定的摘要指令」。DSH 的对应形状是两条：一次 provider 尝试一条记录（`assistant/attempt`，`dsh-agent-loop/lib/index.js:1101-1134`——失败先落 attempt，拿到 `{kind: "retry"}` 就 `continue`，重试再落一条），上下文记录只在头部变化之后补一条（`request/header`，同文件 :1214-1225）。代价写进规格：一个回合可能出现两条 `context/assembled`，「每回合恰有一条」的 WHEN 收窄成「没有回合走到请求级重试」。另一条读法（实现不动、只改规格，重试那次的上下文只由前缀派生、不写快照）被否——它把「日志说的和实际发出去的不是一回事」合法化；第三条读法（不写第二条 `model/request`、照 429 那条用 `model/retry`）也被否——它与 DSH 的「一次尝试一条记录」相反，也正是 ADR-0002 第 17 条要避开的形状。
