---
status: accepted
---

# 溢出只塌到回合级；provider 报出的超限先压缩一次再重试一次

DSH 的 `compactIfNeeded` 跑在 `agent/pre-step`，压缩失败只 warn 并继续这个 turn；provider 报出的上下文超限走 `agent/request-error`，先做一次请求级压缩再重试那一次请求，上限 `maxOverflowRetries` 默认 1，救不动才把原始错误留给上层。mini 照这个做法，并把它写成两条判据：**窗口预算不成立是启动期参数错误**——`window − reserve − 65536 ≤ 0` 当场退出码 2、不建 session 日志（DSH 的 `pressureBudgetTokens <= 0` 也是在配置解析时就抛 `TargetPressureConfigError`，不是运行期才发现）；**provider 报出的超限先救一次**——先做一次请求级压缩，有可遮蔽内容就写 `compaction/summary`、重新折叠、重试那一次请求，上限一次；无可遮蔽内容 / 那一次用完 / 重试仍失败，三条塌成同一个溢出结果，且不写 `error/model`。同时把收尾的**层级**定下来：内核只写 `error/context` + `turn/end(CONTEXT_WINDOW_EXCEEDED)` + `segment/end(CONTEXT_WINDOW_EXCEEDED)`，`session/end` 与退出码归入口——`run` 塌成 4，`chat` 回到提示符。

Considered options：照 DSH 那样「压缩失败 warn 并继续这个 turn」（否：mini 还没有「在一个没有预算的回合里继续」那条路，它要先有 M10 / M11 的压缩失败策略，记进 ADR-0002）；把 `maxOverflowRetries` 做成参数（否：它是实现常量，照 DSH 的默认 1，窗口参数 `--window` / `--reserve` 两个够了）；chat 也塌成退出码 4（否：那等于一条长输入杀死整个会话，与「一次 chat 是一个连续会话」直接矛盾）。

Consequences：ADR-0016 里「两条触发路径塌成同一个结果」那句里的「+ 退出码 4」只成立于 `run` 入口，退出码那一半由本条接管。请求级压缩与装配内的压缩是两次不同的尝试：一次装配最多一次装配内压缩，请求级压缩另计、上限一次。chat 的 stdout 是「每段跑完读回日志再打印」的投影，不是流式；工具事件的终端投影与进度归 M7 之后（记在 ADR-0002）。
