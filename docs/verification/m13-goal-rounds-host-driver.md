# M13 追加验收：host 驱动、问题交回、停滞闸门（2026-11-20）

**触发**：UAT 之后的六点人裁（队列语义、`rounds_started` 口径、完成与停止、命名 C、host 驱动、DSH 组件顺序）。本文只记这次追加的**行为面**验收；命名 C 与组件顺序是独立 change / 文档，不在本报告。

## 一、行为变化

| # | 变化 | 之前 | 现在 |
|---|---|---|---|
| 1 | host 的 goal | 只到 `/goal` 命令面，`/goal resume` 之后没有驱动 | 段后收尾与 `run` / `chat` 共用 `settle_segment`；队列空且判定 `continue` 时自动开下一轮 |
| 2 | 队列优先级 | host 队列只在段尾先跑；chat 无队列 | 队列人话**先于**自动轮；chat 提示符上的下一条输入同样先于自动轮（D13） |
| 3 | 未决问题 | `paused` + 解除武装，人回答后要 `/goal resume` | 目标保持 `active/armed`；回答是人类段（`rounds_started` 不变），段收尾后自动续下一 goal 轮（D15） |
| 4 | 完成但没声明 | 驱动继续开轮，白烧额度 | 停滞闸门默认开、阈值 2：连续两轮零动作才 `stalled`（解除武装、相位不变、回到入口，D14）；一轮空转不误杀，`0` 可关闭；`segment/end.tool_calls` 落盘 |
| 5 | 命令面 | `/goal` 四条；host 的 `/goal resume` 只改状态 | 另加 `/goal edit <正文>`（不动相位/武装位）与 `/goal complete`；带参数的上限编辑在 CLI `minihns goal`；host 的 `/goal resume` 与 chat 一样立刻开下一轮 |

## 二、判据与证据

| 判据 | 用例 |
|---|---|
| host 自动续跑到 `round-limit` | `tests/test_host_goal_driver.py::test_host_runs_goal_rounds_to_the_cap` |
| 队列人话先于下一 goal 轮 | `...::test_a_queued_human_message_runs_before_the_next_goal_round` |
| host 里回答是 human turn、目标续跑 | `...::test_a_question_answer_is_a_human_turn_then_the_goal_continues` |
| host 的 `/goal resume` 立刻开段 | `...::test_goal_resume_command_starts_the_next_round_immediately` |
| chat 里回答是 human 段、不推进轮号 | `tests/test_chat_goal_driver.py::test_an_answer_is_a_human_segment_and_the_goal_resumes_after_it` |
| 未决问题不再 paused | `...::test_a_question_asked_in_a_round_returns_to_the_prompt_without_burning_the_next`、`tests/test_goal_rounds.py::test_an_unanswered_question_hands_control_back_without_burning_the_next_round` |
| 默认阈值 2：连续两轮才停 | `tests/test_goal_rounds.py::test_two_idle_goal_rounds_in_a_row_trip_the_stall_gate_by_default` |
| `stall_rounds = 0` 完全关闭 | `...::test_stall_rounds_zero_disables_the_gate_entirely` |
| 五档判定（stop/continue/exhausted/awaiting/stalled） | `...::test_the_round_decision_only_looks_at_the_snapshot_the_arm_and_the_stop_reason` |
| `/goal edit` 不动相位/武装位 | `tests/test_goal_commands.py::test_replacing_the_objective_does_not_touch_phase_or_arm` |
| CLI `goal edit` 改上限并截到部署硬顶 | `tests/test_cli_goal.py::test_edit_replaces_the_objective_and_the_cap`、`...::test_edit_clamps_the_cap_to_the_deployment_ceiling` |
| `/goal complete` | `...::test_complete_writes_complete_and_disarms` |

## 三、门禁

- ruff `check` / `format --check`：绿。
- `mypy --strict src`：绿。
- 全量：**860 passed / 7 skipped / 0 failed**（2026-11-20，本机；沙箱内跑，`TMPDIR` 指向仓库内）。
- `openspec validate --all --strict`：26 项全绿。
- 覆盖率：口径待修（单次 78.47% / 累积 96.66%，见 `docs/CURRENT.md`「覆盖率口径」）；本轮不引用旧读数当本次。

## 四、残余与不在本报告内的事

- **UAT 6.2 仍需人跑**：场次 1/2 已按 D15 改口；重点看「回答问题后自动续跑」。空转默认连续两轮才停，第一轮只说不动仍会继续。
- **`stalled` 的灰度**：只看「连续 N 轮 `tool_calls == 0`」（缺省 N=2）；读了文件再说「没有新内容」的轮次不会触发。更强的判据（工作区指纹 / 每轮必须更新 todo）会误杀研究型轮次，不做（design D14 残余）。
- **`awaiting_input` 不落持久原因**：日志只有 `question/asked` 没有 `question/answered`；这是可接受的线索，但不是显式状态。
- **命名 C**：`align-turn-step-naming` 已 propose（含 schema v2 上迁设计），未 apply。
- **host 的 goal 投影 / GoalBar**：仍不在 M13 范围。
