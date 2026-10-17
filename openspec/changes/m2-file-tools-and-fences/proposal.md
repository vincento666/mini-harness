# Proposal

## Why

M1 把内核主干跑通了，但注册表是空的：`dispatch_tool_call` 对任何工具都只回 `NOT_IMPLEMENTED`，模型没有任何可观察副作用，不变量 E（围栏）完全没有实现。M2 让 harness 第一次能改文件——批量改 5 个 `.md` 成功、越界写被拒并退出码 3——并让「能干什么」与「要不要问人」这两条独立轴第一次在事件日志里可断言。

## What Changes

- 注册五个文件工具：`read` / `write` / `edit`（字面替换 + CAS）/ `glob` / `grep`。`tool/result.outcome` 词表从 {`UNKNOWN_TOOL`, `NOT_IMPLEMENTED`} 换成真实执行词表（`OK` 加文件层失败码）；`NOT_IMPLEMENTED` 被移除。
- 新增围栏：工作区边界（解析后路径必须落在工作区根之内）、`--sandbox` 三档（`read-only` / `workspace-write` / `danger-full-access`，默认 `workspace-write`）、写前必读 CAS（`write` 覆盖已存在文件与 `edit` 都要求本 session 先 `read` 过该路径；`edit` 的原文还须与读到时一致，否则 `STALE_EDIT`）。「已读过」集合从日志前缀派生，不另立真源。
- 新增 approval 轴：默认 ask，只有会改动的工具（`write` / `edit`）问人——往 stdin 提问并写 `approval/request` / `approval/response`；`--yes` 全自动；非 tty 且未 `--yes` 是围栏拒绝。
- 围栏拒绝是**终止结果**：先写配对的 `tool/result`（`outcome: DENIED_BY_FENCE`）保住「每个 `tool/call` 有配对结果」，再写 `error/fence` 与 `session/end`，退出码 3。M1 的保留码 3 在 M2 可达。
- 事件词表加 `approval/request`、`approval/response`、`error/fence`；`session/start.payload` 加 `sandbox`、`approval`、`tools`（当时的工具名列表）。后者修掉 ADR-0002 第 7 条：不记进日志，replay 重算头部时会把合法日志报成 `REPLAY_MISMATCH`。
- 新增只读 fixture 仓库 `tests/fixtures/repo`（5 个 `.md` + 一个可跑的小 pytest 工程），每个测试复制到 tmp 工作区再跑。
- 处理 ADR-0002 记账的 #1 #2 #5 #7（`SessionSettings`、`ToolDefinition` 与 `ToolSpec` 分叉、词表收成 `Literal`、replay 的工具描述从前缀派生）；#3 #4 #6 继续记账。
- **既有行为变化**：M1 的两个场景 fixture 调的是 `read`（参数 `file_path`），M1 里它们产出 `UNKNOWN_TOOL`，M2 里变成真实读结果（读不到就是文件层失败码，仍是结果）。`UNKNOWN_TOOL` 的判据改挂到未注册工具名上。M1 的 run/replay 参数与退出码语义不变。

## Capabilities

### New Capabilities

- `file-tools`: 五个文件工具的参数契约、执行结果词表、写前必读与 `edit` 的 CAS 语义。
- `fences`: 工作区边界、`--sandbox` 档位、approval 是否问人，以及围栏拒绝作为终止结果与退出码 3。

### Modified Capabilities

- `turn-loop`: 派发管线从「空注册表 + `NOT_IMPLEMENTED`」变成带执行上下文的真实派发；`tool/result.outcome` 词表换血；围栏拒绝终止 session。
- `event-log`: 事件词表加 `approval/request`、`approval/response`、`error/fence`；`session/start.payload` 字段表加 `sandbox`、`approval`、`tools`。
- `cli`: 参数表加 `--sandbox` 与 `--yes`；退出码 3 从保留码变成可达码。
- `context-projection`: 受保护头部的工具描述块内容改为「该装配点当时注册的工具名列表」，且必须可从日志前缀派生。

## Impact

- 代码：`src/mini_harness/tools/`（新增 `file_tools.py`、围栏与 approval 落在 `tools/fences.py`）、`loop/turn_loop.py`（派发上下文与终止路径）、`events/`（词表与 `session/start` 字段）、`cli/main.py`（两个新参数、退出码 3）。`provider/` 契约不变：`ToolSpec` 仍是 `name` + `description`，参数契约只存在于注册表侧。
- 测试：seam ③（文件工具契约）第一次出现；seam ②⑥ 扩；`tests/fixtures/repo` 新建。
- 「DSH 这么做」与「mini 版故意简化」：DSH 有 OS 级强制（Windows 受限令牌 + ACL、Linux landlock、macOS seatbelt）、approval 带提权通道（`sandbox_permissions` + `justification`）、工具管线六段（`pre-execute → guard → execute → post-execute → finalizeContent → tools/result`）、三档 permission preset 把两轴钉成固定组合。mini 版只做路径边界 + CAS + 档位判定，没有提权通道（档位外一律拒），管线塌成「校验参数 → 围栏判定 → 执行」，两轴保持独立不预设。代价记进 `docs/adr/0003-m2-fence-simplifications.md`（ADR-FORMAT：扫现有最大号 +1）。

## 明确不做（M2 范围外）

`bash`、只读工具并发与 `max_parallel = 8`、超时与 `tool/cancelled`、真实 Provider 与 `parallel_tool_calls`、上下文窗口预算与压缩、`minihns chat`、`minihns serve --http`、`--resume` 与投影缓存、OS 级沙箱、工具输出的分页与截断预算、approval 的提权请求、把工具参数 JSON Schema 送给模型（M2 的参数契约写在工具描述文本里）。退出码 4 仍是保留码，可达性属 M5。
