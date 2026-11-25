# 验证契约

**日期**：2026-11-25（第三版）。第一版复核出 3 个 blocker；第二版修订后复核仍出 GAPS，本版按「回退 exact-once、钩子传内容、取消按落盘、观测点用管道」再修。

## 目标

让 chat 的正文在模型生成时逐段出现在屏幕上，同时不重复、不倒序、不吞掉无增量步，也不把取消前的半句话写成最终答复。

## 可观察行为

1. **默认就是流式，且是实时的**：不传 flag 时，首 delta 到达就写到 stdout；用「首 delta 后阻塞」的桩在**管道**上观测，阻塞期间首 delta 可读、第二个尚不可读（seam：sink → 终端）。
2. **增量按序、不重复**：delta 顺序等于屏幕顺序；流过 delta 的步不再整段重打（seam：sink → 终端）。
3. **无增量在步末回退、恰一次**：某步没发 delta，就在 `step/end` 之后、下一步 `step/start` 之前打印它的 `content`；同轮混合不倒序，且该步整轮只出现一次（seam：步边界）。同轮多步的正文按顺序**拼接在同一行**，轮末一个换行——流式的收尾单位是轮，不是步。
4. **轮边界清楚**：有非空正文 delta 的轮 `[answer] ` 恰一次；目标多轮各自成行；`[轮] n/cap` 在该轮正文前；提示符一条输入只一次（seam：轮边界）。
5. **取消按「回复是否已落盘」分叉**：未落盘 → 保留前缀、不写 response；已落盘 → 保留完整记录、不补第二段正文（seam：取消路径）。
6. **日志与 provider 契约不变**：不写 `model/delta`、不新增事件类型、`model/response` 键集合不变、replay 仍退 0（seam：日志面）。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | 管道/pty：桩 provider 发完首 delta 后阻塞；在管道上读到首 delta 时第二个尚未可读，放行后第二个到达（`test_the_first_delta_is_readable_before_the_stream_finishes`）。不用 `capsys`——它绕过了 flush，测不出「写而不 flush」 |
| 1 | 单测：不传 flag 时 `SessionEnv.on_delta` 非空；`--no-stream` 与 `host` 时 `on_delta` 与 `on_step_end` 都为空（`test_stream_is_the_default_and_can_be_turned_off`） |
| 1 | 单测：`--stream --no-stream` 同给 → 退出码 2、无新日志 |
| 2 | 单测：`deltas: ["你","好"]`、`content: "你好"` → 去掉提示符后的 stdout 恰为 `你好` + 换行，`你好` 不出现第二次（`test_stream_writes_deltas_in_order_without_repeating_the_final_content`） |
| 2 | 单测：一轮两步都流正文 → `[answer] ` 恰一次（`test_the_answer_marker_appears_once_per_turn`） |
| 3 | 单测：无 delta、`content: "答案"` → 该步 `step/end` 之后、下一步 `step/start` 之前 stdout 已含 `答案`，整轮 `stdout.count("答案") == 1`（`test_a_step_without_deltas_falls_back_once_at_step_end`） |
| 3 | 单测：同轮第一步无 delta、第二步有 → 去掉提示符后是「第一步 content + 换行 + 第二步增量」，精确序列，不得倒序（`test_mixed_steps_never_print_out_of_order`） |
| 3 | 单测：空字符串 delta + 非空 `content` → 无 `[answer]`，按无 delta 处理（`test_empty_deltas_are_not_streaming`） |
| 3 | 单测：工具步 `content` 为空或全空白 → 不出空行（`test_tool_only_steps_leave_no_blank_line_while_streaming`） |
| 3 | 单测：带 `purpose: "compaction"` 的 `model/response` → 摘要永不出现于 stdout；同轮回退只取真正回复（`test_compaction_summaries_never_reach_stdout`） |
| 4 | 黑盒：目标连续两轮、每轮正文非空 → 去掉提示符后 stdout 恰两行正文；stderr 有 `[轮] 1/…` 与 `[轮] 2/…`（跨流先后由 pty 合流断言；仅数次数不算）（`test_goal_rounds_each_own_a_line`） |
| 4 | 黑盒：一条输入触发 1 人类轮 + 2 自动轮，结束回到提示符 → 提示符恰一次（`test_the_prompt_appears_once_per_input`） |
| 5 | 单测（sink barrier）：桩 provider 发完首 delta 后阻塞，测试在 `on_delta` 里置取消 → stdout 保留首段，日志无 `model/response`、有 `error/abort` + `step/end ABORTED`（`test_cancel_mid_stream_keeps_the_visible_prefix`） |
| 5 | 单测：`--stream`、provider 无 delta、生成落盘后取消 → 完整 `model/response` 保留，正文写出一次，日志无半条（`test_cancel_after_the_reply_is_persisted_keeps_it`） |
| 5 | 单测：`--stream`、流过 delta 且 `model/response` 已落盘，取消发生在工具派发 → 日志完整、stdout 无第二条正文（`test_cancel_in_the_tool_window_keeps_the_full_reply`） |
| 5 | pty：只验信号投递——`0x03` 能让进程进入取消收尾并回到提示符，不承担「半句时刻」的可控性（`test_ctrl_c_is_delivered_as_sigint`） |
| 5 | 单测：`--no-stream` 下同一场景 → 日志形状与基线一致（`test_cancel_without_stream_keeps_the_old_shape`） |
| 6 | 单测：同一 fixture 分别 `--stream` / `--no-stream` 跑成功一轮 → 事件类型序列相同、`model/response` 键集合相同、都不含 `model/delta`；`content` 逐字相等（`test_streaming_does_not_change_the_log`） |
| 6 | 合成 v2 日志：`--stream` 与 `--no-stream` 同内容日志的折叠消息序列逐点相等，`replay` 都退 0（`test_replay_is_identical_with_and_without_stream`） |
| 6 | 单测：`--resume` 的日志里有一条 `purpose` 摘要 + 一条新回复 → 新回复打印一次（`printed` 只数非 `purpose`）（`test_resume_after_compaction_prints_the_first_new_reply`） |

## 坏法清单（变异种子）

1. **只改旗标不改输出**：`--stream` 接受但 env 不注入 sink → 行为 1、2 红。
2. **缓存后一次写**：delta 全收进列表、轮末一次写 → 行为 1 的管道判据红（阻塞期间读不到首 delta）。
3. **写但不 flush**：每 delta 写 stdout 但不 flush → 管道判据红（缓冲未到）。
4. **流了还整段打**：轮末不跳过已输出步 → 行为 2 红。
5. **回退后再打一次**：步末回退过、轮末又投影 → 行为 3 的 exact-once 红（1→2→1）。
6. **轮末才回退**：无 delta 的步等到轮末 → 行为 3 的倒序判据红。
7. **空 delta 算流式**：空串也记入已输出集合 → 行为 3 的空 delta 判据红（正文被吞）。
8. **空 content 也回退**：不判 `strip()` → 行为 3 的空行判据红。
9. **取消只看 sink**：`cancel.is_set() and env.on_delta is not None` 就 abort → 行为 5 的「已落盘保留完整记录」判据红。
10. **取消在写前不看 `streamed_any`**：只要取消就 abort → 行为 5 的「无 delta 不吞整段」红。
11. **默认写反**：`set_defaults(stream=False)` → 行为 1 红。
12. **按输入收尾**：`finish_turn()` 挂在外层输入循环而不是每轮 → 行为 4 的两行判据红。

## 不验什么

- **取消的 CLI 屏幕判据**：`--stream` 中途取消时「半句保留、不补整段」在 CLI 层没有独立黑盒判据——内核层用 sink barrier 钉住了「不写半条 `model/response`」，屏幕上的前缀由 UAT 场次 4 的人眼判。工具窗口取消同理。
- **`--resume` + 压缩摘要的首条回复**：游标口径已统一，但没有专门造「有摘要的日志 + resume」的判据；它的行为由 `_print_new_replies` 与初始化两处同口径的代码审查兜住。

- 不做思考流：`[thinking]` / `reasoning/delta` / `on_reasoning` 全在 `reasoning-mode-and-budget`，本 change 不碰。
- 不改 host / serve 的 SSE 合流、游标、断线续读；host 不装 `on_step_end`，行为不变（由判据锁住）。
- 不做 `run` / `serve` 的正文流式。
- 不做终端富文本：颜色、Markdown 渲染、行内光标控制都不在范围内。
- 不验首帧延迟指标（H2 的 1 s 判据属于宿主轨）；只证明「阻塞期间首 delta 可读」。
- 不验 provider 的 SSE 解析本身：`openai_compat` 已有 H2 判据，本 change 只消费 sink。
- 不验 pty 上的「半句时刻」：可控性由 sink barrier 单测承担；pty 只验信号投递。

## 待裁决

- 默认 `--stream`：已定（沿用 2026-11-03 人裁）。
- `[answer] ` 在无思考流时是否保留：保留，将来 `[thinking]` 回来时协议不用改。
- `--no-stream` 是否长期保留：保留，作为逐点对照与分诊开关。
- `on_step_end` 钩子只给 CLI：host 的 SSE 已有 durable `model/response` 帧；若将来 host 也要「无 delta 补发」，另开 change。
