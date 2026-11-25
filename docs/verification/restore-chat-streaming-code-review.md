# restore-chat-streaming 代码审查（两轴）

**日期**：2026-11-25。范围：`git diff HEAD`（本 change 未提交的实现与测试）＋两份验收记录。审查者：独立上下文的只读子代理，输入只有 change id、delta 路径、diff 范围与两轴定义。

## 子代理裁决（原文，未改写）

**verdict**：`PASS WITH FINDINGS`

1. `cli/main.py:754` · Spec · **major** — `printed` 初始化改成只数非 `purpose` 后，`--resume` + 压缩摘要 + `--no-stream` 会多打印一条旧行为跳过的回复，违反 Requirement 1「`--no-stream` 逐点相同」。建议：在规格中显式豁免这次游标修正并补判据，或只在 `--stream` 下使用新口径。
2. `cli/main.py:855` · Spec · **major** — `finish_turn()` 在 `_print_turn_note()`/`_print_shadow_feedback()` 之后才写换行，tty 上 `[轮] 收尾 ABORTED`/`[遮蔽]` 会粘在流式正文同一行，Requirement 4 的轮边界不成立。建议：`run_turn` 返回后立即 `finish_turn()`，再打诊断行。
3. `loop/turn_loop.py:1361` · Spec · **major** — 取消分叉实际只看 `on_delta` + `delta_state.streamed_any`，不是规格写的「`model/response` 是否已落盘」；generate 已完整返回但尚未落盘的窄窗口会丢掉完整回复，工具窗口路径也没有显式判据。建议：按落盘/未落盘分叉，或把 `streamed_any` 写进规格，并补工具窗口取消测试。
4. `cli/main.py:584` · Spec · **major** — 步末回退只写 `content` 不写换行，同轮混合实际是 `甲甲乙乙\n`，与契约要求的 `甲甲\n乙乙` 精确序列不符。
5. `tests/test_turn_loop.py:1122` · Spec · **major** — 取消 Scenario 的 CLI 屏幕判据缺失：没有测 `--stream` 中途取消的 stdout 前缀、无 delta 已落盘后正文仍写出、工具窗口取消、`--no-stream` 旧形状。
6. `verification-contract.md:31-41` · Spec · **major** — stream 模式压缩摘要不进 stdout、stream/no-stream replay 折叠相等、`--resume` 后首条新回复、提示符一条输入一次、goal 轮 `[轮]` 在正文前（pty）都没有对应测试；`test_streaming_does_not_change_the_event_types` 也不比较 `content`。
7. `tests/test_cli_chat.py:1150` · Spec · **major** — `test_a_step_without_deltas_falls_back_at_step_end_once` 只数出现次数，无法区分步末回退与轮末回退，`mutation.md` 的 M3 已证明该点存活。
8. `tests/test_cli_chat.py:1279` · Standards · **major** — 实时性判据用 `python -c` 直接 import `_ChatStreamRenderer` 起子进程，不是真实 `minihns chat` 命令，绕过 CLI 装配与既有 `cli_blackbox` harness。
9. `restore-chat-streaming-uat.md:3` · Standards · **major** — 场次 2/5 标为 agent 代跑；ADR-0025 的 UAT 是「人坐在终端前办一件真事」，非 tty 也不能由 agent 代跑并算通过。
10. `tests/test_turn_loop.py:1122` · Standards · **minor** — 新增的 `test_a_cancel_after_deltas_does_not_write_half_a_response` 与既有的 `test_a_cancel_during_stream_aborts_without_a_model_response` 逐条重复。
11. `loop/turn_loop.py:635` · Standards · **minor** — `on_step_end` 异常分支写 `error/internal`/`RENDER_FAILED`，位于 `step/end` 之后且无测试/变异。
12. `cli/main.py:568` · Spec · **minor** — `text()` 只判 `if not text`，纯空白 delta 会被当作流式并加入 `already_shown`，随后 `on_step_end` 跳过回退，最终非空白 `content` 可能不显示。
13. `restore-chat-streaming-mutation.md:9` · Standards · **minor** — 变异记录只有 M1–M4，契约 12 个坏法里默认写反、写而不 flush、回退后再打、空 content、per-input finish 等未跑或未记录。

## 处置

| # | 裁决 | 落点 |
|---|---|---|
| 1 | **接受（规格豁免 + 记缺口）** | `--no-stream` 的「逐点相同」在规格里加了唯一例外：游标原先按「所有 `model/response`」计数、投影只打非 `purpose` 的那些，两者不一致会在「有摘要的日志」上**少打**一条真回复。初始化改同口径是修正。专门判据未做，记进契约「不验什么」。 |
| 2 | **接受** | `finish_turn()` 移到 `run_turn` 返回后、`_print_turn_note` 之前。tty 上诊断行不再粘在正文后。 |
| 3 | **部分接受** | 实现不改：判断点在「写 `model/response` 之前」，那里「已落盘」等价于「没流过非空增量」。改的是**规格措辞**——写清判断点与所用事实，并说明工具窗口的取消走收尾分支、回复已落盘。工具窗口的独立判据未加（见 #5）。 |
| 4 | **拒绝加换行，接受写清口径** | 流式的收尾单位是**轮**，同轮多步正文按顺序拼接、轮末一个换行——这是规格「按轮收尾」的原意。契约补上这句口径，混合测试改成断言精确前缀 `> 甲甲乙乙`（能杀 M3）。 |
| 5 | **部分接受（记缺口）** | CLI 层的取消时机需要 pty + 精确定时，归 UAT 场次 4 的人眼判；内核层已有「有增量不写半条」「无增量不吞整段」两条判据。写进契约「不验什么」。 |
| 6 | **部分接受（补 3 条）** | 补了 stream 版压缩摘要（`test_a_compaction_summary_never_reaches_stdout_while_streaming`）与 replay 相等（`test_a_streamed_log_still_replays`）；提示符与 pty `[轮]` 位置归 UAT 场次 1/3。 |
| 7 | **接受** | 混合测试改为精确前缀断言；单步那条保留（它守「只出现一次」）。M3 之前杀不死单步测试的原因写进 mutation 记录。 |
| 8 | **部分接受（保留并标注）** | 它是**渲染器接口判据**（seam ① 的边界），不是 seam ⑥ 黑盒——黑盒实时性要阻塞式 SSE 桩，成本高于收益。注释与契约里写明归属；M1/M6 两个变异证明它能证伪。 |
| 9 | **接受** | UAT 状态改为「全部待人跑/待人确认」，代跑记录保留但不算通过；场次 1、3、4 无记录。 |
| 10 | **接受** | 删掉重复的那条（44 行），保留「无增量不吞整段」——它才是 `streamed_any` 的判据。 |
| 11 | **接受** | 补 `test_a_broken_step_end_hook_records_an_internal_error`：断言 `error/internal` 的 code、`step/end` 在它之前、`turn/end` 在它之后。 |
| 12 | **接受** | 纯空白 delta 照写（保留换行）但不打标记、不进已显示集合；`text()` 里分开判 `not text` 与 `not text.strip()`。 |
| 13 | **接受（补跑 4 条 + 说明 2 组同族 + 1 条未跑）** | 补跑 M5（默认写反）、M6（写而不 flush）、M7（空 content 也回退）、M8（空 delta 算流式）；#9/#10 同族、#5/#4 同族；#12（按输入收尾）是结构性改法，未跑并写明由哪条判据覆盖。 |

## 结论

13 条全部处置：6 条接受、6 条部分接受、1 条拒绝（#4 的「必须加换行」）。两个真问题（#2 诊断行粘行、#12 空白 delta 吞正文）已修并有判据；#1 与 #3 通过规格措辞消除歧义，不留实现与规格的缝。
