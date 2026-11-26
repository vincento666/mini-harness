# 提案：合入 reasoning 两条分支并迁移到当前主线（`[reasoning]` / `[thinking]` 可见）

## Why

chat 里 `[reasoning]`（思考帧）一直不显示。原因不是没实现，而是**两条实现分支没有合入 main**：

- `origin/change/reasoning-mode-and-budget`：领先 main **50 个提交**，28 项 tasks 勾了 27 项（只有 7.2 UAT 人跑未做）。覆盖有序 content blocks、`fold` 回传、SSE `reasoning/delta`、`reasoning_tokens` 不重复计。
- `origin/change/chat-streaming-shell`：领先 main **47 个提交**，但 `git rev-list reasoning..shell == 0`——**shell 是 reasoning 的祖先**，合入 reasoning 就把 shell 一起带进来（`[thinking]` 开始标志、`on_reasoning`、thinking 结束行、`[answer]`）。
- 主规格里没有 `reasoning` 能力；main 的 `src/` 里 `on_reasoning` / `reasoning_content` 零命中。

分叉点是 `c6d59ed`（M10 之前）。此后 main 经历了 `align-turn-step-naming`（段/回合→轮/步，19 份主规格）、`goal-round-pacing`（政策 v1→v2）、`restore-chat-streaming`（默认流式、`on_step_end`）三次大改，所以**不能直接 merge 了事**，需要迁移。

## What Changes

1. 把 `origin/change/reasoning-mode-and-budget` 合入主线（连带 shell），解决 8 个文件 17 处冲突。
2. **迁移改名**：分支里用的是旧词（`segment`/回合/段），合入后必须改成 v2 词表（`turn`=轮、`step`=步、事件名 `turn/*` 与 `step/*`），并与 `goal-round-pacing` 的政策 v3、`restore-chat-streaming` 的默认流式/`on_step_end` 对齐。
3. 把分支自带的 `reasoning` 规格 delta 迁成当前主规格（本 change 的 `specs/reasoning/spec.md` 是原样带入的初稿，落实时按 v2 词表逐句核对）。
4. 跑该 change 遗留的 7.2 UAT（真实 reasoner 的 blocks/usage），产出 `docs/verification/merge-reasoning-stream-*.md`。

## 冲突清单（worktree 预演，2026-11-26）

| 文件 | 冲突块 |
|---|---|
| `src/mini_harness/cli/main.py` | 5 |
| `src/mini_harness/loop/turn_loop.py` | 3 |
| `tests/test_cli_chat.py` | 3 |
| `docs/CURRENT.md` | 2 |
| `src/mini_harness/cli/host.py` | 1 |
| `src/mini_harness/provider/contract.py` | 1 |
| `src/mini_harness/provider/openai_compat.py` | 1 |
| `docs/roadmap.md` | 1 |

## 不做什么

- 不新写一套 reasoning 实现（分支已有，重做等于把 27 项已完成任务再写一遍）。
- 不把 reasoning 混进正文 `model/delta`（规格明确要求分开）。
- 不在本 change 里改 `[轮]` 计数、政策内容等无关项。
