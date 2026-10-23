# Proposal

## Why

人手验收里 `minihns chat` 在真端点上「对不了话」。会话 `92c155ba16fb4a4aa7bcbf931d5ba098`（`--base-url http://127.0.0.1:8300/v1`、`window 128000`、`max_turns 8`）的第一段用 8 个工具回合把上下文推过触发线，之后两条输入（`ihi`、`enen`）各只得到一个段级收尾：`model/request(purpose: compaction)` → `error/model(PROVIDER_HTTP_STATUS, HTTP 400)` → `turn/end(PROVIDER_ERROR)`，屏幕上只有提示符。根因是**摘要请求把要压缩的整份上下文原样发给模型**：那条用来救「越线」的请求本身比它要缩小的东西更大，端点直接拒——`prompt (222233 tokens) leaves no room to answer in the context (196608); requests are never truncated`。

**判据这一侧还有一条**：压缩与遮蔽这条机制从来没有在真实端点上跑过的判据——M4 的完成判据里有「两个端点各一次真实 smoke」那一行，M5（正是压缩那个里程碑）、M6、M7 的完成判据里都没有。真实那一半被放进了「人手验收、不进 CI、不替代任何一条判据」的位置，于是 mock 桩绿就等于里程碑完成，而真实端点上的失败形状（400 的正文、`error.type` 而不是 `error.code`）没有任何判据打到过。

## What Changes

- **摘要请求裁进窗口**：生成摘要的那次调用只装「本次要遮蔽的那一段」折出的消息（加系统消息与摘要指令），不再发整份表层；这一段本身就装不下时**不发**这个请求，直接走溢出结果。
- **溢出识别放宽**：适配器把可识别的上下文超限回复规范化为 `PROVIDER_CONTEXT_OVERFLOW`——除既有的 `error.code == context_length_exceeded`，也认 `error.message` 命中固定短语表（大小写不敏感、整句里找子串；真端点那一次回的正文里只有 `error.type` 与 `message`，没有 `error.code`）。塌成溢出只发生在不可重试的 4xx：429 与 5xx 仍走 `PROVIDER_HTTP_STATUS`，塌成溢出的那条不重试。
- **失败带上提供方那句话**：`ProviderFailure.detail` 与 `error/model.payload.detail` 里带上响应正文的有界摘要（单行、至多 200 字符），不再是光秃秃的 `HTTP 400`。
- **失败在屏幕上可见**：`minihns chat` 里段**不以** `MODEL_COMPLETED` / `ABORTED` 收尾时（`PROVIDER_ERROR` / `CONTEXT_WINDOW_EXCEEDED` / `MAX_TURNS` / `FENCE_DENIED` 都在其中），stderr 打一行说明；stdout 仍是日志的投影，规则不变。
- **遮蔽层在屏幕上可见**：一个段里写出 `compaction/summary` 时，stderr 打一行遮蔽反馈（`shadowed_range` 两端、`tokens_before`、`tokens_after`），同一条记录只报一次；不新增事件类型、不改 payload。
- **判据补上真实端点那一层**：seam ⑤ 的识别判据直接读真端点实际回过的那条 400 正文，seam ① 的记录形状判据读真端点实际写出的那条 `compaction/summary`（两份 fixture 的来源见 `tests/fixtures/real_endpoint/README.md`）；seam ⑥ 的 chat 判据跑真实子进程、端点是 mock 或监听 loopback 的假 server，真实那一半由完成判据里那次真实实测承担。另加一条**完成判据**——一次真实端点的 `minihns chat` 实测（不进 CI，但不跑完这个 change 不算完成）。这是流程层面的更正：M4 之后每个里程碑的完成判据里都没有真实端点那一行，见 ADR-0022。

**本 change 明确不做**：不改 `字符 ÷ 4` 的预算估算（DSH 自己也把精确 token 化列为暂缓，见其 `dsh-compaction-basic` 开发备注）；不加工具输出修剪器（DSH 的 `dsh-compaction-tool-result-pruner`）；不给摘要请求加 `max_tokens`；不改 `max_turns` 默认值；不碰 `minihns serve` 的事件流；不解决 Windows 上被 skip 的四条 SIGINT 子进程判据；不动 `context-budget` 主规格里只写 `minihns run` 的那处不对称。

## Capabilities

### New Capabilities

（无——三条都落在既有能力上）

### Modified Capabilities

- `context-budget`：「越线时压缩发生在装配之内」加摘要请求的形状与预算约束；「摘要调用失败沿用 provider 失败结果」补「请求没发出」那一支。
- `provider`：「上下文超限的回复是溢出结果」放宽识别；新增「失败结果带上提供方说的那句话」。
- `chat-repl`：新增「段不以正常回复收尾时 stderr 看得见一行」与「压缩与遮蔽在屏幕上看得见」。

## Impact

- 代码：`loop/turn_loop.py` 的压缩段（现 620–681 行，`[*context.messages, SUMMARY_INSTRUCTION]` 那一处）、`context/budget.py`（复用已算出的 `shadowed_range`）、`provider/openai_compat.py`（`_reports_context_overflow`、`ProviderFailure.detail`）、`cli/main.py::_chat_session`。
- 判据：seam ①（回合循环里的压缩与溢出）、seam ⑤（Provider 接口的识别与 detail）、seam ⑥（CLI 黑盒的 stderr 两行与遮蔽反馈）；`tests/fixtures/` 新增真实端点产物。
- 文档：立 **ADR-0022**（模型相关功能的完成判据含一次真实端点实测，CI 的 mock 判据不算验收；与 handoff 决策 6 的关系）与 **ADR-0023**（「DSH 只回放被遮蔽区域、mini 之前发整份表层」的更正 + 猜正文短语的代价）；`docs/adr/0002` 第 62、63 条与本条同源，新增第 64 条记估算与真端点差 4 倍这件事；`AGENTS.md` 晋升一条（一进一出）。
- 依赖：无新增依赖。
