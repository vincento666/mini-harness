# 提案：把 chat 的正文流式补回来

## 为什么

今天 `minihns chat` 的 stdout 是日志的**轮末投影**：`_print_new_replies()` 在每轮结束后从 `model/response` 读回正文，一次 `print` 整段。长回答的表现是「先安静很久，再一次性出现」；目标续跑时更糟——屏幕上只有 `[轮] n/cap` 与工具回执，人分不清模型是在写、在等，还是已经卡死。

这套能力 2026-11-03 实现过一次（`chat-streaming-shell`：`_ChatStreamRenderer` + `chat --stream` / `--no-stream`，默认 `--stream`；15/15，主规格 `chat-streaming` 已 sync）。但它的合并提交 `6857ce4` 只进了 `change/reasoning-mode-and-budget` 分支，**从未进 main**：

- `git merge-base --is-ancestor 6857ce4 main` → 否；
- `openspec/specs/` 下没有 `chat-streaming`，只有 `chat-repl` 与 `chat-tool-events`；
- 当前工作分支从 main 拉出；`cli/main.py` 构造 `SessionEnv` 时没有 `on_delta`，`SessionEnv` 虽然有这个字段，但 CLI 从未注入。

所以结论既不是「没实现」，也不是「改名改坏了」：实现停在一条没有合入的分支上。附带一个文档硬伤——`docs/reference/h2-streaming-and-reasoning.md` 按那条分支写着「chat shell 默认 `--stream`」，对当前 main 是假陈述，本 change 一并修正。

## 要改什么

- `chat` 增加互斥的 `--stream` / `--no-stream`，默认 `--stream`；`--no-stream` 的 stdout、stderr、日志与退出码 MUST 与今天逐点相同。
- 复用 `SessionEnv.on_delta`（内核已有，host 在用）：不新造 provider 方法、不新增事件类型、不改 `model/response` 载荷。
- CLI 侧的终端渲染器：正文 delta 写 stdout 并逐个 flush；每轮第一次非空正文 delta 之前在 stderr 打一次 `[answer] `；轮末换行并重置本轮标记。
- 去重：流过正文 delta 的**步**，轮末不再整段打印；没流过（provider 不流式、fixture 无 delta、只有空 delta）的步回退到既有日志投影。
- 按**轮**收尾：目标续跑连续开的多轮各自成行，`[轮] n/cap` 仍在该轮正文之前；一条输入只对应一个提示符。

## 不做什么

- **不做思考流**：`on_reasoning` 在当前 `SessionEnv` 不存在，provider 也不解析 `reasoning_content`；`[thinking]` 与 `reasoning/delta` 归 `reasoning-mode-and-budget`（见 `docs/reference/reasoning-mode.md` 的结论：要真对齐得先把 assistant message 升级成有序 content blocks）。
- **不改 host / serve 的 SSE**：它们的 delta 通道是 `HostSession.publish_delta` + `/events`，与本 change 无关。
- **不写日志**：`model/delta`、`reasoning/delta` 都不是事件词表成员；流式只改变屏幕时序，不改变 durable 真相。
- **不改 `--no-stream` 的取消形状**：有 sink 时 `turn_loop` 走 `_abort_turn`（不写半条 `model/response`），没有 sink 时保持今天的形状；这是既有判据，本 change 只是让 chat 的默认路径落到它上面。
- **不做 `run` / `serve` 的正文流式**：它们的 stdout 是退出码产物或事件流，不是正文投影。

## Impact

- CLI flag +2（互斥组），`chat` 的默认输出时序改变（内容与顺序不变）。
- `cli/main.py` +1 个渲染器，`_print_new_replies` 多一个「已流式步」跳过集合；内核、provider、事件词表、日志 schema 都不动。
- 既有 `chat` 测试中依赖「轮末整段打印」的断言需要显式加 `--no-stream`，或改为流式断言。
- 文档：`docs/reference/h2-streaming-and-reasoning.md` 的 chat 段落按实现回写；`docs/CURRENT.md` 记一条。
