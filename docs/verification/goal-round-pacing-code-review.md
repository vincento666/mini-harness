# goal-round-pacing 代码审查（两轴）

**日期**：2026-11-25。范围：`git diff 2213a8a..bfd4589`（本 change 的实现、测试、验收记录、账本）。两轴：Standards 与 Spec。审查者：独立上下文的只读子代理，输入只有 change id、delta 路径、diff 范围与两轴定义。

## 子代理裁决（原文，未改写）

**verdict**：`PASS WITH FINDINGS`

**findings**

1. `/Users/vincento/work/develop/mini-harness/docs/verification/goal-round-pacing-uat.md:3-4,27` · Standards · **major** — UAT 标为「已完成」，但场次 1/2/3/5 是 agent 在非交互 `run` 上代跑、场次 4 未跑，不满足 `AGENTS.md`「人坐在终端前办一件真事 / tty 场次不得代跑」的完成判据；即使有授权记录，归档门仍需人确认。建议：状态改为「待人确认」，由人补跑 chat 场次（含 `[轮]` 观察与 Ctrl-C），或明确记录豁免后再归档。

2. `/Users/vincento/work/develop/mini-harness/openspec/changes/goal-round-pacing/specs/goal/spec.md:63-66` · Spec · **major** — 「早失败不消耗轮次」的 WHEN 不可达：`_run_steps` 在调用 provider 之前已写 `step/start`（`turn_loop.py:1216`，provider 调用在 `:1284`），且本 change 没有判据覆盖「goal 消息已写、首条 `context/assembled` 未写」时的失败，`rounds_started` 不被消耗这条 MUST 无测试可证伪。建议：把场景改成注入/折叠/装配内压缩失败等真实早失败点，并补一条能断言 `rounds_started` 不变的测试。

3. `/Users/vincento/work/develop/mini-harness/src/mini_harness/events/fold.py:26-28`（并 `/Users/vincento/work/develop/mini-harness/src/mini_harness/goals.py:143`） · Spec · **minor** — 政策文本把续跑条件写成「active + 已武装 + 有额度 + 无未决问题」四条，但 `next_round` 还有停滞闸门（`goal_driver.py:67`），满足四条仍可能被停掉；目标轮正文又写死「连续两轮」而 `stall_rounds` 可配。建议：政策补「除非连续空转触发停滞」，正文改成不绑定具体阈值（或按配置渲染）。

4. `/Users/vincento/work/develop/mini-harness/src/mini_harness/events/fold.py:24-30` 与 `/Users/vincento/work/develop/mini-harness/src/mini_harness/loop/goal_driver.py:59-69` · Standards · **minor** — 续跑条件是同一事实的两处定义（政策字符串与 `next_round`），版本化只保旧日志 replay、不保语义同步；现有测试只断言关键词「写满步数上限」，改 `next_round` 不会让政策文本红；`GOAL_POLICY_VERSION` 与字典键 `"v1"` 也是同一版本事实的两处写法。建议：把条件摘要抽成一处或加交叉引用/判据，并让版本常量与映射键只保留一个来源。

5. `/Users/vincento/work/develop/mini-harness/openspec/changes/goal-round-pacing/specs/cli/spec.md:16-19` · Spec · **minor** — 「政策版本不可由调用方覆盖」场景没有判据：没有测试写 `goal_policy = "off"` 的配置、没有传同名 flag，也没有在配置了 `append_system_prompt` 时断言头部仍含政策段；通用未知键测试不绑定这条 MUST。建议：补一条黑盒（配置写 `goal_policy="off"` → 未知键/`INVALID_ARGUMENT`，正常会话仍 `goal_policy=="v1"`），并补配置值下的头部断言。

6. `/Users/vincento/work/develop/mini-harness/openspec/changes/goal-round-pacing/tasks.md:15`（`/Users/vincento/work/develop/mini-harness/tests/test_goal_rounds.py:692`） · Standards · **minor** — 任务写「单测（经 `settle_turn`）」覆盖 FENCE_DENIED/CONTEXT_WINDOW_EXCEEDED 与 MAX_STEPS 的武装位，但新增测试直接调 `close_failed_round`（绕过 `settle_turn`），MAX_STEPS 的「武装位保持」只在 e2e 间接体现，任务记录的测试层级与实际不符。建议：测试改为经 `settle_turn`，或把任务文字改成「经 `close_failed_round` + e2e」。

7. `/Users/vincento/work/develop/mini-harness/src/mini_harness/events/fold.py:30` · Spec · **minor** — 政策段会注入所有新会话（含子代理/无 goal 工具），但最后一句「真正完成时才调用 update_goal 标 complete」是无条件命令；design D3 与验证契约称用条件句避免误导，实际只有 `create_goal` 那句是条件句。建议：改成「若你有 update_goal 工具，真正完成时才…」，或在没有 goal 工具的会话不注入该段，并同步 design/契约的取舍。

Standards 轴：查了 GLOSSARY 术语（轮/步/目标，新文本未混用旧词）、依赖方向（`events/fold.py` 仍只依赖 `events.record`，`loop` 依赖 `events` 合法）、错误处理（无裸异常，沿用 `LogWriteFailure`/`TurnOutcome`）、注释纪律（新注释解释 why）、单一真源与重复真源（版本常量集中但续跑条件重复，已报）、测试 harness（`tool_harness.build_session_env`、`cli_blackbox`，未自造装配）、完成判据与 UAT（已报）、改动范围（无越界重构）；判为无问题：命名、依赖方向、错误处理、注释、测试 harness、范围控制。

Spec 轴：逐条核对 goal/context-projection/cli 的 Requirement 与 Scenario；重点三条——`MAX_STEPS` 移出 `NO_CONTINUE_REASONS` 且 `settle_turn` 不再解除武装（通过，黑盒 `test_max_steps_is_a_round_boundary_and_the_cap_still_stops` 可杀死变异）、`goal_policy` 不被 `--append-system-prompt` 覆盖且无字段旧日志 replay 不变（通过，fold/replay/CLI 三处判据齐）、政策文本与 `render_goal_round` 口径（有缝，已报）；轮边界/停滞/取消/额度/append 顺序/旧日志均有判据；已报缺口：早失败场景不可达且无判据、配置覆盖场景无判据、无 goal 工具时政策句可能误导。

## 处置

| # | 裁决 | 理由与落点 |
|---|---|---|
| F1 | **接受** | UAT 状态行原写「已完成」，与文末「归档时需人确认」矛盾。改为「已跑完；场次 4 降级为单测覆盖，归档时一并确认」。代跑本身有人 2026-11-25 的明确授权，不重新讨论。 |
| F2 | **接受** | 原 WHEN 双重不可达：`turn/start` 与 goal 消息同批写、provider 只在 `step/start` 之后调。改成真实早失败点（首条 `context/assembled` 之前装配失败），并按 `window=50`/`reserve=10` 构造判据 `test_an_assembly_overflow_before_context_assembled_keeps_the_round_count`：断言 `CONTEXT_WINDOW_EXCEEDED`、本轮无 `context/assembled`、`rounds_started == 0`。 |
| F3 | **接受** | 政策 `v2` 补「且没有连续零动作触发停滞」；`render_goal_round` 把「连续两轮」改成「连续零动作的轮数达到停滞阈值」，不再硬编码可配值。新增两条判据：`test_the_goal_policy_mentions_the_stall_gate`、`test_the_goal_round_text_does_not_hardcode_the_stall_threshold`。 |
| F4 | **部分接受** | 版本常量与映射键：新增 `test_the_current_policy_version_has_a_text` 断言 `GOAL_POLICY_VERSION in GOAL_POLICY_VERSIONS`，两个事实不再能各写各的。续跑条件的自然语言摘要**不消除重复**：政策是给人/模型看的摘要，`next_round` 是唯一判定，两者不可能同源；改为在 `GOAL_POLICY_VERSIONS` 上方加注释指明「摘要，判定看 `next_round`」。接受这条重复的代价并记账。 |
| F5 | **接受** | 补两条黑盒：`test_the_goal_policy_is_not_a_config_key`（配置未知键 → `INVALID_ARGUMENT`、无日志）、`test_the_goal_policy_is_not_a_cli_flag`（`--goal-policy` → `unrecognized arguments`、无日志）。 |
| F6 | **接受** | `test_fence_and_overflow_disarm_without_pausing` 改为经 `settle_turn`（任务文字本来就是这么写的）；另加 `test_max_steps_keeps_the_goal_armed_through_settle_turn`，把 `MAX_STEPS` 的「结论 continue + 武装位保持 + 轮次不推进」从 e2e 间接证据升级为直接判据。 |
| F7 | **接受** | `v2` 最后一句改成「若你有 update_goal 工具：真正完成时才调用它标 `complete`」；`test_a_new_session_carries_the_goal_policy` 断言该条件句。为不误导无 goal 工具的会话，选「条件句」而不是「按工具裁剪政策」——后者会让头部依赖工具集，属于另一层设计。 |

## 结论

7 条全部处置：6 条接受、1 条部分接受（F4 的续跑条件摘要）。两个 major（F1、F2）都已修到有判据。政策文本因此升到 `v2`，`v1` 原文保留在 `GOAL_POLICY_VERSIONS` 里供旧日志重算——升版本机制在本次被真实使用了一次。
