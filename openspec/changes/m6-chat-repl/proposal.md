# Proposal

## Why

`minihns` 只有一个入口：一次性 `run`。内核（回合循环、日志、折叠、预算、围栏、provider）已经齐了，但没有任何入口能把「一个会话」连续跑下去。`docs/roadmap.md` 的 M6 就是这一条：`minihns chat` REPL。它同时是 ADR-0002 第 3 条（`_replay` 摸事件层的内部形状）与第 21 条（`registry` / `context` / `approval_gate` / `on_approval_request` 四个入参一路结伴）的**第二个消费者**——那两条都写着「等第二个消费者出现再抽」，M6 就是那个消费者。

第二件事是 REPL 让 M5 落下的溢出形状变得不可接受。DSH 把溢出当成**请求级失败**：`agent/request-error` 里 `code == CONTEXT_WINDOW_EXCEEDED` 时先压缩、再重试那次请求，上限 `maxOverflowRetries` 默认 1；压缩没有产生持久表层进展或次数用完，就保留原始请求错误——回合失败，会话不死（`dsh-compaction-basic/lib/index.js:861-887`）。窗口预算本身不成立时（`contextWindow − 预留 completion − headroomTokens ≤ 0`）DSH 在配置解析期抛 `TargetPressureConfigError`，运行期只 warn 一次并跳过压缩（同文件 :130-131、:844-847）。mini 版现在把这两件事都做成了「终止整个 session、退出码 4」：REPL 里一次溢出会杀掉整个会话；而 `--window 32768 --reserve 4096` 这种配置要跑到第一次装配才发现它没救（M5 模型层实测：`无可遮蔽的内容，预算读数 33 已超过触发线 0`）。

## What Changes

- 新增 `minihns chat`：与 `run` 共用参数表、配置层叠与内核入口；一次 chat 恰一份日志、恰一个 `session_id`，`session/end` 只在会话收尾时写。
- 词表新增 `user/message`：REPL 的每条输入是一条记录；折叠里 `role: user` 消息多一个来源。`session/start.payload` 新增 `entry`（`run` / `chat`），chat 的 `prompt` 是空串。
- 每条输入是一个**回合段**，段内上限是有效 `max_turns`，`turn_id` 跨段连续编号；段用完上限或段失败都回到提示符。
- 取消两级：段进行中取消 → 回合级收尾、会话继续；提示符上取消或 EOF → 写 `session/end`（`stop_reason: MODEL_COMPLETED`）、退出码 0。
- 按 DSH 校正溢出：溢出与取消同形——内核只写回合级收尾，**会话是否结束由入口决定**（一次性 `run` 塌成退出码 4，chat 回到提示符）；provider 报溢出时先压缩一次并重试该请求一次（上限 1）；`window − reserve − 65536 ≤ 0` 是配置错误，在 session 开始之前以退出码 2 失败。
- 收 ADR-0002 第 3 条（replay 的扫描逻辑下沉到事件层）与第 21 条（四个入参收成一个派发环境）。

## Capabilities

### New Capabilities
- `chat-repl`: REPL 的会话边界、输入即记录、回合段与上限、两级取消、非 tty 的 stdin、stdout 的打印范围。

### Modified Capabilities
- `cli`：`session/start` payload 加 `entry`；退出码表加 chat 的正常收尾。
- `event-log`：词表加 `user/message`。
- `context-projection`：对话体的 `user` 消息有两个来源。
- `turn-loop`：`turn_id` 覆盖 `user/message`；`max_turns` 是段内上限；「预算溢出终止整个 session」被「溢出是回合终止结果、会话是否继续由入口决定」接替。
- `context-budget`：窗口预算不成立是启动期配置错误；装配内一次压缩与请求级一次重试分开；provider 报溢出先压缩再重试。

## 明确不做

- 不做 `--resume`、斜杠命令、多会话、REPL 里的目标与委派（M15）。
- 不做工具事件的终端投影（Claude Code 那种「Reading file…」进度行）：stdout 只打模型回复正文。工具事件的终端投影是日志的另一种投影，归 M7 之后的事件流消费者，记 ADR-0002。
- 不做「摘要调用失败时 warn 并继续这一回合」（DSH：`continuing the turn`）：mini 版沿用 M5 落下的 provider 失败形状，记 ADR-0002 推到 M10 / M11。
- 不做 tty 检测、不做真 tokenizer、不做多 provider 路由。

## Impact

`src/mini_harness/cli/`（新子命令与输入循环）、`events/`（词表 + replay 的扫描逻辑下沉）、`loop/`（回合段、溢出收尾、派发环境）、`context/budget.py`（启动期校验）、`tests/`（seam ① ④ ⑥ 各补判据）。M5 的 manual 文档里「窗口 32768 → 退出码 4」那条观察被启动期校验取代，收尾时标注。新增 ADR-0019（溢出的入口边界与请求级重试）与 ADR-0020（REPL 的会话与 `user/message`）。
