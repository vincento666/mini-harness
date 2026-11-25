# 任务：restore-chat-streaming

## 1 实现

- [x] 1.1 红判据先落：默认流式、`--no-stream` 基线、互斥 flag、首帧可读（`tests/test_cli_chat.py`）
- [x] 1.2 `_ChatStreamRenderer`：`text()` 写正文、每轮一次 `[answer] `、`finish_turn()` 只在写过正文时换行
- [x] 1.3 互斥 `--stream` / `--no-stream`，`--stream` 默认；flag 表测试并上这两个
- [x] 1.4 `SessionEnv.on_step_end(step_id, content)`；`_run_steps` 在 `step/end` 之后、`break` 之前调用；钩子异常写 `error/internal`
- [x] 1.5 CLI 钩子：`content.strip()` 非空且该步没流过非空 delta 才补打；`--no-stream` 与 host 不装钩子
- [x] 1.6 去重：`_print_new_replies` 跳过 `already_shown`；`printed` 游标按非 `purpose` 计数，`--resume` 初始化同口径
- [x] 1.7 按轮收尾：`run_turn` 返回后立刻 `finish_turn()`（在诊断行之前）
- [x] 1.8 取消分叉：`DeltaState.streamed_any` 只算非空 text，每次 generate 前重置（含压缩重试）
- [x] 1.9 实时性判据用真子进程 + 真管道（`test_the_first_delta_is_visible_before_the_turn_ends`）

## 2 判据

- [x] 2.1 默认流式：`deltas: ["你","好"]` → 顺序出现、轮末不重复
- [x] 2.2 实时性：管道桩在轮末前可读；「攒批」与「写但不 flush」两个变异都能红（见 mutation M1/M6）
- [x] 2.3 `--no-stream` 与基线逐点相同：三条既有 chat 测试显式加 flag 后仍绿
- [x] 2.4 去重三分支：有 delta、无 delta、同轮混合不倒序（精确序列 `> 甲甲乙乙`）
- [x] 2.5 `[answer] ` 每轮恰一次；空 delta 不触发；空白 `content` 不出空行
- [x] 2.6 compaction：摘要不进 stdout（stream 与 no-stream 各一条）
- [x] 2.7 黑盒：目标两轮各一行、`[轮]` 在正文前（`test_goal_rounds_each_get_their_own_line`）
- [x] 2.8 管道喂行：真实端点场次（`2eb3ff10…`）与 UAT 场次 5 覆盖
- [x] 2.9 取消：内核层两条（有增量不写半条 / 无增量不吞整段）；CLI 屏幕判据归 UAT 场次 4
- [x] 2.10 pty `0x03` 投递：不由本轮新增，既有 `_cli_console_process` 路径覆盖；macOS 归 UAT 场次 4
- [x] 2.11 日志不变：类型序列与 `model/response` 键集合相同；`replay` 退 0、无 `REPLAY_MISMATCH`
- [x] 2.12 `--resume` + compaction：游标口径已统一，专门判据未做（记在契约「不验什么」）

## 3 收尾

- [x] 3.1 全量门禁：**920 passed / 7 skipped**、ruff / `mypy --strict` 绿、`openspec validate` 绿
- [x] 3.2 真实端点：OpenRouter `qwen/qwen3.8-27b` 一场，会话 `2eb3ff10…`；增量拼接等于日志 `content` 且只出现一次
- [ ] 3.3 UAT 验收：人跑；场次手册 `docs/verification/restore-chat-streaming-uat.md`（关键场次是 UX 手感，按 ADR-0025 不得由 agent 代跑）
- [x] 3.4 变异一轮：M1–M8 八条全杀（其中 M8 由既有的 `test_tool_only_turns_leave_no_blank_lines` 杀死）；两条同族合并、一条结构性改法未跑，记录在 `restore-chat-streaming-mutation.md`
- [x] 3.5 两轴 review：`PASS WITH FINDINGS`，9 major + 4 minor；修复项与处置见 `restore-chat-streaming-code-review.md`
- [x] 3.6 Learning Gate：**`NO-PROMOTION`**。两条候选（「收行必须紧跟产生它的输出」、「时序类需求要构造两个元素的顺序差异」）与收件箱里 L-098 / L-099 同族；且收件箱已 28 条、超过 15 条上限，按纪律先消化再收，本次不新增
- [x] 3.7 文档：`h2-streaming-and-reasoning.md` §6.1 按实现回写（正文流式已补回、思考流仍 deferred）；`CURRENT.md` 更新
