# Design

## Context

见 `proposal.md` 的 Why。设计侧的当前实况只有三条：

- 落盘形状：`turn_loop._dispatch_batch` 把整批结果攒在 `outcomes` 里，批次结束才 `_append_all`。M3 的变异记录已经写明「`tool/call` 的落盘顺序在当前实现下**不可观察**」（`_append_all` 是同步函数、`begin()` 全程不让出事件循环），所以那条护栏变异 C2 被判成 dud。
- 取消形状：`cancel.is_set()` 在派发段两处被查（拿到独占权之后、`begin` 之前），未派发的调用**不写 `tool/call`**；取消塌成会话终止（ADR-0007）。
- 折叠形状：`events/fold.py` 完全忽略 `tool/call`，只从 `tool/result` 取工具结果消息。所以「有 `tool/call` 没 `tool/result`」的半截前缀在折叠里表现为「一条 assistant 工具请求消息没有配平的工具结果消息」。

约束：不变量 A（只追加不改写）与 B（失败也是结果）不可让步；CI 不持 API key，判据必须离线可跑（ADR-0005）。

## Goals / Non-Goals

**Goals:**
- 日志前缀在任何时刻都是完整事实：已产出的结果立刻在盘上，未派发的调用也是结果。
- 取消的可见后果是「回合闭合」，不是「批次被掀翻」，为 M6 / M7 的会话续跑留出正确形状。
- 半截前缀有读方修复，且修复是确定性的、不落盘的。

**Non-Goals（设计级边界，proposal 之外）:**
- 不给工具体派生信号，也不加管线段——那是 M10（ADR-0013）。M8 的「协作式」只到「内核等已派发的调用自己产出结果词」这一层。
- 不做 `--resume`、不把闭合写回日志、不做折叠缓存——那是 M11。
- 不改 `TOOL_CANCELLED` 这个名字去对齐 DSH 的 `ABORTED`。
- 不引入新的退出码，也不改退出码 5 的含义。

## Decisions

**D1 闭合是读方派生，不是写方记录。** 折叠遇到未配对的 `tool/call` 时派生一条 `TOOL_OUTCOME_UNKNOWN` 的工具结果消息。备选是写方 closer（进程被硬杀时没机会写）或 resume 时补（那是 M11，M8 没有 resume）。代价：盘上那份日志永远半截，「完整」只成立于读方；M11 要决定是否把闭合写回日志。

**D2 未派发的调用写 `tool/call` + `tool/result`。** 备选是只写 `tool/result`（破坏「每条结果有配对的 `tool/call`」）或什么都不写（就是被推翻的 M3 形状）。选前者：`tool/call` 记录的是「模型声明了这个调用」这一事实，`ABORTED_BEFORE_DISPATCH` 记录的是「内核决定不派发」，两者都是真发生过的事。

**D3 保留 `TOOL_CANCELLED`，用 `GLOSSARY.md` 对齐 DSH 的 `ABORTED`。** 改名要掀 M3 的判据与既有日志的可读性，换来的只是名字相同。按 ADR-0010 的「术语对齐代替实现」处理。

**D4 落盘从「批次末一次性写」改成「产出即写」。** 每个调用产出结果时立刻 append 并 flush，`outcomes` 不再缓冲。代价：一次 run 的 flush 次数上升（本地文件、每结果一次，可接受）；`tool/result` 的顺序变成完成顺序，判据要按集合断言。备选是保留缓冲但在取消路径上单独 flush——否：那等于把缺口按路径切开，硬杀那一侧照旧。

**D5 取消时未派发的调用不配 `tool/cancelled`。** 「被打断」预设它开始过。未派发的只有一个结果词。这让 `tool/cancelled` 的语义保持单一：它对应一次真的开始过的调用。

**Seam 边界与测试策略**（不新增 seam）：
- **seam ① 回合循环**：取消的两个结果词、回合闭合顺序（`error/abort` → `turn/end(ABORTED)`）、未派发调用不配 `tool/cancelled`。注入 cancel，不看真实信号。
- **seam ② 工具注册与管线**：`ToolOutcome` 两个新值的可达判据与「词表外的值不被写出」。
- **seam ④ 日志追加与折叠**：立刻落盘（轮询日志文件观察结果先于批次结束出现）、读方闭合、闭合的确定性、半截日志喂折叠。**读方闭合的判据全部用构造日志**，不依赖真硬杀——这条必须确定、不能 flaky。
- **seam ⑥ CLI 黑盒**：真硬杀（Linux `SIGKILL`、Windows `Popen.kill()`，杀点用「轮询到日志里出现 N 条 `tool/call`」定位）判「已产出的结果都在盘上且每条可独立解析」；退出码 5 与 replay 逐点相等照旧。判据只断言**与杀点无关的性质**，不断言具体条数。

## Risks / Trade-offs

- [真硬杀判据在 Windows 上杀点不精确] → 判据只断言「已写出的每条 `tool/result` 完整可解析、没有半行 JSON」这种杀点无关的性质；读方闭合的判据不依赖这条测试，改用构造日志（seam ④）。
- [「协作式取消」在 M8 只做了一半：工具体仍不观察信号，长命令仍靠打断] → 在 `docs/dsh-alignment.md` 与 design 里写明这是半转向，M10 补完；M8 的判据不承诺工具体自己停。
- [落盘顺序变了，既有判据要重写，可能连带掀 M3 的变异记录] → 迁移计划里先重写判据再改实现；M3 变异记录加一条注记说明 C2 那条护栏在 M8 之后不再适用（不改写历史）。
- [读方闭合让「日志坏了」变得不可见] → 判据里保留一条「完整日志不派生任何闭合」的负判据；M11 决定是否把闭合写回日志时再处理可见性。
- [两个新结果词进词表，Active Lesson 1 栽过两次] → 每个值一条可达判据，且 seam ② 有一条「词表外的值不被写出」的护栏。

## Migration Plan

1. 重写被推翻的判据（先 red）：`tests/test_turn_concurrency.py::test_results_land_in_declared_order_when_the_second_finishes_first` 改成完成顺序 + 集合断言；`tests/test_turn_cancel.py::test_no_call_has_a_tool_call_without_a_result_after_a_cancel` 扩成「未派发的调用也各有一对记录」。
2. 实现：`tools/registry.py` 两个新 `ToolOutcome` → `loop/turn_loop.py` 立刻落盘与取消分支 → `events/fold.py` 读方闭合 → `cli/main.py` 入口侧的会话终止措辞（退出码 5 不变）。
3. 既有绿判据回归：`tests/test_turn_cancel.py` 其余三条、`tests/test_approval_gate.py` 的两条顺序与取消判据、`tests/test_event_vocabulary.py`。
4. 无数据迁移：既有 session 日志不改写；旧日志里「有 `tool/call` 没 `tool/result`」的前缀在新折叠下自动得到闭合。

## Open Questions

- 读方闭合要不要在 payload 里留一个可观察标记（例如折叠结果的消息上带 `synthesized: true`）？留与不留都不改规格与任务拆分，实现时定。
