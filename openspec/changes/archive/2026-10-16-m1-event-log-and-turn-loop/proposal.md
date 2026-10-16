# Proposal

## Why

mini-harness 现在一行实现代码都没有，而 M2..M7（文件工具、围栏、并发、压缩、REPL、SSE）全都要求「一次运行可被重放、可被断言」。没有只追加的事件日志和显式的回合主循环，后面每个里程碑都没有可验证的对象。M1 用 mock Provider 把内核主干（记账 → 装配上下文 → 调模型 → 派发工具 → 判定停止）先跑通，并把六个测试 seam 的边界一次性钉死。

## What Changes

- 新增 JSONL 只追加事件日志：`schema_version` 字段、`namespace/method` 事件命名、每次 `run` 一个新 session id、日志文件 `sessions/<session-id>.jsonl`。
- 新增冷启动全量重放折叠（fold）：当前上下文只由日志派生，无缓存、无检查点、无 `--resume`。
- 新增显式回合主循环（单一 asyncio 事件循环，`--max-turns` 上限），停止判定显式写在循环里。
- 新增单方法 Provider 契约 `generate(messages, tools, signal)` 与 mock Provider（JSON fixture 序列）。
- 新增工具派发管线的最小可用版：注册表允许为空，未注册工具返回 `UNKNOWN_TOOL` 结果事件而不是抛异常（不变量 B 在 M1 就要可测）。
- 新增 CLI：`minihns run -p "任务"` 与 `minihns replay <session-id>`；新增退出码表 0/1/2/3/4/5。
- 无破坏性变更：greenfield，`openspec/specs/` 目前为空。

## Capabilities

### New Capabilities

- `event-log`: 只追加 JSONL 事件日志的写入契约——`schema_version`、事件类型词表、session id 与日志文件定位、追加不改写。
- `context-projection`: 从事件日志折叠出「当前算数的上下文」——受保护头部 + 保留尾部；冷启动全量重放。
- `turn-loop`: 显式回合主循环——记账、装配、调模型、派发工具、判定停止，以及 `UNKNOWN_TOOL`、`NOT_IMPLEMENTED` 这类失败结果。
- `provider`: Provider 单方法接口契约与 mock Provider（JSON fixture 序列），mock 与真实实现共用同一接口。
- `cli`: `minihns run` / `minihns replay` 的命令行外部行为与退出码表。

### Modified Capabilities

无（本仓库尚无已归档能力规格）。

## Impact

- 新代码：`src/mini_harness/`（`events/`、`loop/`、`tools/`、`provider/`、`cli/`）——本 change 只规定边界，不写实现。折叠（`context-projection` 这条能力的实现）落在 `src/mini_harness/events/fold.py`，与日志同层（design D1），没有独立的 `src/mini_harness/projection/` 包。
- 新测试：`tests/`，只写在六个预先约定的 seam 上（回合循环 / 工具注册与管线 / 文件工具契约 / 日志追加与折叠 / Provider 接口 / CLI 黑盒）。M1 覆盖 ①②④⑤⑥；seam ③（文件工具契约）在 M2 才出现。
- 新依赖：`pydantic` v2（事件 payload 与 Provider 返回校验）、`pytest` + `pytest-asyncio`；`uv` 管理。
- 「DSH 这么做」与「mini 版故意简化」的差别：DSH 是 `SESSION_FORMAT_VERSION = 4`、60 种已知事件类型、可选 zstd 压缩、带投影键注册表（见 `docs/dsh-reference/DSH逆向分析报告.md`）。mini 版取 `schema_version = 1`、16–20 种事件、明文 JSONL、无投影缓存。这些简化的代价记入 `docs/adr/`（ADR-0001「M1 的刻意简化」与 ADR-0002「记账：M1 留下的坏味道与设计缺口」），不在本 change 内实现。

## 明确不做（M1 范围外）

文件工具（`read`/`write`/`edit`/`glob`/`grep`）、围栏与工作区边界、写前必读 CAS、approval 两轴、`bash`、只读工具并发与超时取消、真实模型调用（DeepSeek/OpenAI 兼容端点）、上下文窗口预算与压缩（触发线、剪枝、摘要、遮蔽、标记对）、`minihns chat` REPL、`minihns serve --http`、`--resume` 与投影缓存、OS 级沙箱、插件容器、子代理委派。

退出码 3（围栏拒绝或审批被拒）与 4（上下文预算溢出）在 M1 只是**保留码**：词表在 M1 定稿，可达性分别由 M2 与 M5 引入。
