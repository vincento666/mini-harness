# 验证契约

**日期**：2026-11-25（第二版：按独立复核的 3 个 blocker 修——回退改步末、取消按是否流过 delta 分叉、实时性用可控停顿验证）。

## 目标

让 chat 的正文在模型生成时逐段出现在屏幕上，同时不重复、不倒序、不吞掉无增量步，也不把取消前的半句话写成最终答复。

## 可观察行为

1. **默认就是流式，且是实时的**：不传 flag 时，首 delta 到达就被写到 stdout，不是缓存到轮末一次写出（seam：sink → 终端）。
2. **增量按序、不重复**：provider 的 delta 顺序等于屏幕顺序；流过 delta 的步不再整段重打（seam：sink → 终端）。
3. **无增量在步末回退**：某步没发 delta，就在该步结束、下一步开始前打印它的 `content`；同轮混合时不倒序（seam：步边界 → 日志投影）。
4. **轮边界清楚**：每轮一次 `[answer] `；目标多轮各自成行；`[轮] n/cap` 在该轮正文前；提示符一条输入只一次（seam：轮边界）。
5. **取消按「是否真的流过」分叉**：流过 → 保留前缀、不补整段、日志 abort；没流过 → 不吞完整回复，写完整 `model/response`（seam：取消路径）。
6. **日志与 provider 契约不变**：不写 `model/delta`、不新增事件类型、`model/response` 键集合不变、replay 仍退 0（seam：日志面）。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | 黑盒：用一个「发完第一个 delta 后阻塞、等测试放行再发第二个」的桩 provider；断言第一个 delta 在阻塞期间已出现在 stdout，第二个尚未出现（`test_the_first_delta_reaches_stdout_before_the_stream_finishes`）。sink 调用记录只能作辅助，不能替代这条 |
| 1 | 单测：不传 flag 时 `SessionEnv.on_delta` 非空；`--no-stream` 时为空（`test_stream_is_the_default_and_can_be_turned_off`） |
| 1 | 单测：`--stream --no-stream` 同给 → 退出码 2、无新日志 |
| 2 | 单测：`deltas: ["你","好"]`、`content: "你好"` → stdout 恰为 `你好` + 换行，`你好` 不出现第二次（`test_stream_writes_deltas_in_order_without_repeating_the_final_content`） |
| 2 | 单测：一轮两步都流正文 → `[answer] ` 恰一次（`test_the_answer_marker_appears_once_per_turn`） |
| 3 | 单测：无 delta、`content: "答案"` → 该步 `step/end` 之后、下一步开始之前，stdout 已含 `答案`（`test_a_step_without_deltas_falls_back_at_step_end`） |
| 3 | 单测：同轮第一步无 delta、第二步有 → stdout 的顺序是「第一步 content → 第二步增量」，不得倒序（`test_mixed_steps_never_print_out_of_order`） |
| 3 | 单测：空字符串 delta + 非空 `content` → 无 `[answer]`，按无 delta 处理（`test_empty_deltas_are_not_streaming`） |
| 4 | 黑盒：目标连续两轮、每轮正文非空 → stdout 恰两行；stderr 有 `[轮] 1/…` 与 `[轮] 2/…`，都在各自正文前（`test_goal_rounds_each_own_a_line`） |
| 4 | 黑盒：一条输入触发 1 人类轮 + 2 自动轮，结束回到提示符 → 提示符恰一次（`test_the_prompt_appears_once_per_input`） |
| 5 | pty：`--stream` 已显示 `半` 后 Ctrl-C → stdout 保留 `半` + 换行，不出现最终 `content`；日志该步 `error/abort` + `step/end ABORTED`，无 `model/response`（`test_ctrl_c_keeps_the_visible_prefix`） |
| 5 | 单测：`--stream` 但 provider 无 delta、生成完成后取消 → 写完整 `model/response`，正文仍被写出，日志里没有半条（`test_cancel_without_deltas_keeps_the_full_reply`） |
| 5 | 单测：`--no-stream` 下同一场景 → 日志形状与基线一致（`test_cancel_without_stream_keeps_the_old_shape`） |
| 6 | 单测：同一 fixture 分别 `--stream` / `--no-stream` 跑成功一轮 → 事件类型序列相同、`model/response` 键集合相同、都不含 `model/delta`；`model/response.content` 逐字相等（`test_streaming_does_not_change_the_log`） |
| 6 | 金样本：`--stream` 跑出的日志 `replay` 退 0；与 `--no-stream` 同内容日志折叠出的消息序列逐点相等（`test_replay_is_identical_with_and_without_stream`） |

## 坏法清单（变异种子）

1. **只改旗标不改输出**：`--stream` 接受但 env 不注入 sink → 行为 1、2 红。
2. **缓存后一次写**：provider 的 delta 全收进列表，轮末一次 `write` → 行为 1 的可控停顿判据红（阻塞期间 stdout 为空）。
3. **流了还整段打**：轮末不跳过已输出步 → 行为 2 红（`你好` 两次）。
4. **跳过所有步**：开了流式就一律不打日志投影 → 行为 3 红（无 delta 的步消失）。
5. **轮末才回退**：无 delta 的步等到轮末 → 行为 3 的倒序判据红（同轮混合时 2→1）。
6. **取消只看 sink**：`cancel.is_set() and env.on_delta is not None` 就 abort → 行为 5 的「无 delta 取消不吞」判据红。
7. **空 delta 算流式**：`text == ""` 也记入已输出集合 → 行为 3 的空 delta 判据红（正文被吞）。
8. **默认写反**：`set_defaults(stream=False)` → 行为 1 红。
9. **按输入收尾**：`finish()` 挂在外层输入循环而不是每轮 → 行为 4 的两行判据红。

## 不验什么

- 不做思考流：`[thinking]` / `reasoning/delta` / `on_reasoning` 全在 `reasoning-mode-and-budget`，本 change 不碰。
- 不改 host / serve 的 SSE 合流、游标、断线续读；host 不传 `on_step_end`，行为不变。
- 不做 `run` / `serve` 的正文流式。
- 不做终端富文本：颜色、Markdown 渲染、行内光标控制都不在范围内。
- 不验首帧延迟指标（H2 的 1 s 判据属于宿主轨）；本 change 只证明「轮结束前出现」，用阻塞桩证明不是缓存。
- 不验 provider 的 SSE 解析本身：`openai_compat` 已有 H2 判据，本 change 只消费 sink。

## 待裁决

- 默认 `--stream`：已定（沿用 2026-11-03 人裁）。
- `[answer] ` 在无思考流时是否保留：保留，将来 `[thinking]` 回来时协议不用改；若人认为噪音，可在 apply 前删掉该 Requirement 与对应判据。
- `--no-stream` 是否长期保留：保留，作为逐点对照与分诊开关。
- `on_step_end` 钩子只给 CLI：host 的 SSE 已有 durable `model/response` 帧，不需要这个钩子；若将来 host 也要「无 delta 补发」，另开 change。
