# Design

## Context

见 `proposal.md` 的 Why。当前仓库是 greenfield：`src/` 与 `tests/` 都不存在，`openspec/specs/` 为空。已锁定的工具链（Python ≥ 3.12、uv、`src/mini_harness/`、mypy strict、pydantic v2、argparse、pytest + pytest-asyncio、单一 asyncio 事件循环）与六条不变量是硬约束，本设计只补 seam 边界与测试策略。

## Goals / Non-Goals

**Goals:**

- 把六个预先约定的 seam 落成模块边界，让 M2..M7 只在既有 seam 上扩展而不改内核。
- 让「日志 → 折叠 → 上下文」这条链在任何进程里可复现，`replay` 与实时折叠可比对。
- 让失败（未注册工具、fixture 耗尽、非法返回、取消）都以事件记录 + 退出码的形式可断言。

**Non-Goals:**

- 不设计 M2..M7 的接口细节（工具契约、围栏两轴、并发调度、压缩、REPL、SSE）；只保证 M1 的 seam 不阻碍它们接入。
- 不设计性能、缓存、`--resume`、投影注册表。
- 本文件不含实现代码与函数签名细节。

## Decisions

### D1 模块划分即 seam 边界

`events/`（追加写 + 折叠）、`loop/`（回合主循环）、`tools/`（注册表 + 派发管线）、`provider/`（契约 + mock 适配器）、`cli/`（argparse + 退出码映射 + replay 打印）。对应六个 seam：① 回合循环 = `loop` 对外入口，② 工具注册与管线 = `tools`，③ 文件工具契约 = M2 才在 `tools` 下出现，④ 日志追加与折叠 = `events`，⑤ Provider 接口 = `provider`，⑥ CLI 黑盒 = `cli`（subprocess 跑真实命令）。

替代方案：按「session 对象」组织成一个上帝对象——被否，因为它让 seam ④⑤ 无法独立测试，且违反不变量 C（循环要显式）。

### D2 `seq` 由日志写入器单点分配

事件记录里的 `seq` 由 `events` 的追加写入器在写入那一刻分配，其它模块只提供 `type` 与 `payload`。替代方案：各模块自己维护计数器——被否，跨模块计数会漂移，且 `--events jsonl` 的 stdout 与日志文件就无法逐行相等。

### D3 折叠是纯函数，不写日志

折叠器输入事件序列、输出上下文（受保护头部 + 保留尾部），不产生副作用；`context/assembled` 由回合循环写入。替代方案：折叠器自己记账——被否，那会让「折叠两次结果相同」这条要求自指失效。

### D8 用户 prompt 经 `session/start.payload.prompt` 进入对话体

M1 的事件词表里没有专门的 prompt 事件类型，因此用户输入原文记在 `session/start` 的 payload 里，折叠时它是对话体的第一条 `user` 消息。这是显式设计选择，已记入 `docs/adr/0001-m1-simplifications.md`。替代方案：新增 `prompt/submitted` 事件类型——被否于 M1（会扩词表且没有额外收益）；M2 之后若需要多轮输入或 REPL 常驻，要走一次 openspec 变更再引入该类型。

### D9 `replay` 是逐点重算并断言相等

`replay` 不打印「全量折叠的最终上下文」，而是对日志里每条 `context/assembled` 用它之前的前缀重算折叠、逐字段比对，任一点不一致产出 `error/replay`（`code: REPLAY_MISMATCH`）并以退出码 1 结束。这样「冷启动折叠等于实时装配」这条不变量在每一个装配点都可断言，而不是只在最后一点；被重放的日志不被改写（`error/replay` 只走 CLI 输出）。替代方案：只比对最后一条 `context/assembled`——被否，因为最后一回合产生的对话体必然让全量折叠与最后一次装配不相等，那条断言在任何真实 run 上都不可满足。

### D4 Provider 契约保持单方法、非流式

`generate(messages, tools, signal) -> AssistantTurn`，mock 与真实实现共用（决策 20/21/23）。M1 只实现 mock 适配器；`signal` 参数在 M1 就要存在，否则 M3 的取消要改接口。替代方案：现在就留流式接口——被否，M1 非流式，过早抽象。

### D5 M1 实现「空注册表 + 完整派发管线」

M1 不注册任何工具，但派发管线（查表 → `tool/call` → 执行或未命中 → `tool/result`）必须完整，未命中产出 `UNKNOWN_TOOL`。这样不变量 B 在 M1 就可测，M2 只是往注册表里加工具。替代方案：M1 完全跳过工具派发——被否，会让 M2 的第一批测试同时改循环和管线，违反单切片纪律。

### D6 内核返回结果对象，退出码只在 CLI 层映射

内核返回运行结果（含最终 `stop_reason` 与失败码），`cli` 层把它映射到退出码表；内核 MUST NOT 直接 `sys.exit` 或抛业务异常。替代方案：内核抛带码异常——被否，与不变量 B「失败也是结果」冲突，且 seam ① 的测试会被异常控制流污染。

### D7 日志路径解析只有一处

`session-dir` 解析（默认 `<cwd>/sessions`）由一个解析器提供，`run` 与 `replay` 共用，避免两个命令找不同文件。

## 测试策略（只在六个 seam 上写）

| seam | M1 覆盖 | 做法 |
|---|---|---|
| ① 回合循环 | 是 | 直接调 `loop` 入口，注入 mock Provider 与临时 session 目录；断言事件序列、`stop_reason`、`turn_id` 对应关系 |
| ② 工具注册与管线 | 是（空注册表） | 注入带 `tool_calls` 的 fixture，断言 `tool/call`/`tool/result` 配对与 `UNKNOWN_TOOL`，断言回合继续 |
| ③ 文件工具契约 | 否 | M1 无文件工具；此 seam 的测试在 M2 出现 |
| ④ 日志追加与折叠 | 是 | 追加前缀不变、信封字段、`seq` 递增、折叠两次相同、逐点前缀重算等于该点的 `context/assembled` |
| ⑤ Provider 接口 | 是 | 直接调 mock Provider：fixture 顺序、非法 fixture、非法返回；断言循环只调 `generate` |
| ⑥ CLI 黑盒 | 是 | `subprocess` 跑真实 `minihns run` / `minihns replay`，断言退出码、stderr 失败词、stdout 与日志逐行相等 |

通用纪律：先写失败测试再写实现，一次一个 red→green 单切片；测试只 mock seam，不 mock 模块内部私有函数；fixture 仓库只读、每个测试复制到 tmp 工作区；`tests/fixtures/scenarios/<name>/` 放 mock fixture 序列。取消类测试通过注入取消信号驱动，Ctrl-C 的真实行为只留一条手动 smoke（Windows 上 SIGINT 经 subprocess 不稳定）。

## Risks / Trade-offs

- [`--events jsonl` 的 stdout 与日志必须逐行相等] → M1 的实现是 run 结束后把日志逐行打到 stdout，且此时不打印 session id 行；seam ⑥ 有一条断言逐行相等的测试兜住。
- [`schema_version` 从 1 起，DSH 是 4] → 明确不兼容 DSH 日志；记入 ADR，避免以后误以为能读 DSH 会话文件。
- [M1 立了退出码 3/4 却不可达] → 词表先定稿、可达性由 M2/M5 引入；seam ⑥ 有一条「M1 不产生 3 或 4」的断言防止提前实现。
- [折叠不截断，长 mock 场景可能写出很大的 `context/assembled`] → M1 场景保持小；真正的预算与压缩是 M5，不在 M1 提前实现。
- [取消语义在 Windows 上依赖信号传递] → 内核取消走注入信号，真实 Ctrl-C 只做手动 smoke。

## Migration Plan

greenfield，无迁移。M1 合入 `main` 后按流程 archive，五份 delta 同步进 `openspec/specs/`，简化决策补进 `docs/adr/`。

## Open Questions

- session id 的具体形态（uuid4 还是时间戳前缀 + 随机后缀）——只要求唯一与可定位，可延后。
- `--events jsonl` 是否默认开启——spec 只约束「开启时」的行为。
- `replay` 的人类可读输出排版——spec 只约束「逐点重算并断言相等」与失败时的 `error/replay`。
