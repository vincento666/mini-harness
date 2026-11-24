# Tasks

## 0. 前置

- [x] 0.1 冻结 v1 金样本：`tests/fixtures/logs/v1-goal-tools.jsonl`（50 事件：1 个人类段 + 2 个 goal 轮 + 3 次工具调用 + `blocked{round-limit}`；`minihns replay` 通过）。**压缩样本未含**：现有 14 份 `sessions/` 都没有 `compaction/summary`，压缩上迁先由 `test_turn_compaction` 的 fixture 覆盖，后续补一份 `v1-compaction.jsonl`
- [x] 0.2 机械替换清单与出现面：design D1 的表 + 2026-11-23 实测词频（`segment` 113/261/278、`turn` 275/582/800、`max_turns` 44/167/263）；三个坑已记（`turn_id` 歧义、`turns` 三义、测试读法）

## 1. 事件 schema v2 与兼容层（seam ④）

- [x] 1.1 `SCHEMA_VERSION = 2`；`CONCRETE_EVENT_TYPES` 换成 v2 名字（`turn/*` 是段、`step/*` 是步）
- [x] 1.2 `LEGACY_EVENT_TYPES` + `is_known_type` 读放行 / `is_current_type` 写拒绝；写旧名落 `error/internal`（`test_event_vocabulary`、`test_event_schema_v2`）
- [x] 1.3 `migrate_schema` 的 `_upcast_v1`：类型与键的整体上迁；`seq` / `ts` / `session_id` 不动（`test_event_schema_v2`）
- [x] 1.4 旧日志 `replay` 逐点相等（`v1-goal-tools` 金样本 exit 0）；新日志只出现 v2 名字（`test_a_new_log_is_written_as_v2_with_current_names`）
- [x] 1.5 投影（`todos` 在 `turn/start` 清空）、折叠、SSE 都只看见 v2：读入口统一上迁，消费方的类型与键已改 v2

## 2. 内核标识符（seam ①）

- [x] 2.1 `SegmentOutcome → TurnOutcome`、`run_turn_segment → run_turn`、`_run_turns → _run_steps`
- [x] 2.2 `segment_id → turn_id`、`turn_id → step_id`；`first_turn_index → first_step_index`（裸标识符；API JSON 键仍留旧名到 3.4）
- [x] 2.3 `RunOutcome.turns → steps`（连带 `end_session` / `_segment_failure` / `_abort_turn` 等参数与局部变量）；`STOP_MAX_TURNS → STOP_MAX_STEPS`，值 `MAX_TURNS → MAX_STEPS`，`_upcast_v1` 同步迁这个值。**`SessionSettings.max_turns` 与配置键不在本任务**：它与 argparse dest、`BUILTIN_DEFAULTS` 的键是同一根线，单独改会断，随 3.1+3.2 一次做
- [x] 2.4 `TurnDeltaSink → StepDeltaSink`（`provider/contract.py`、`loop/turn_loop.py`、`tests/tool_harness.py`）
- [x] 2.5 注释与 docstring 里的「段/回合」改「轮/步」，放在 3.5 之后做（同一句里常同时出现旧字段名与旧文案）。口径：`src` 里「回合」只剩 `SYSTEM_PROMPT` 一处（模型可见文本，故意保留，见 3.5）；「段」只剩普通语义——`字段`、`阶段`、`[goal]` 节（已改「节」）、`整段替换`、`一段摘要`、`这段前缀`、遮蔽区间（`budget.py`）、`追加段`。`执行段` 统一改「执行区间」，避免与「轮」混淆

## 3. 入口与配置（seam ⑥）

- [x] 3.0 会话内命令去 flag（2026-11-23 先落，先于全量改名）：`/goal edit` 只吃正文；`--max-rounds` 移到 `minihns goal <id> edit`；会话内动词不吃参数（`tests/test_goal_commands.py`、`tests/test_cli_goal.py`）

- [x] 3.1 `--max-steps` 主名 + `--max-turns` 隐藏别名（`help=SUPPRESS`，用到时 stderr 提示一次）；同批改 argparse dest、`EffectiveSettings.max_steps`、`SessionSettings.max_steps`、`AssemblyRequest.max_steps`——与 3.2 同一根线，打包成一个提交
- [x] 3.2 `[session] max_steps` 主键 + 旧键 `max_turns` 映射（`config/load.py::_fold_legacy_keys`）；`BUILTIN_DEFAULTS` 键、`SETTINGS_FIELDS`、`cli/host.py` 的 `_SESSION_INT_FIELDS` 一并改；两键冲突 → `CONFIG_INVALID_VALUE` 承载、出口 `INVALID_ARGUMENT`
- [x] 3.3 `subagent` 的 `max_steps` + 旧参数名 `max_turns` 仍接受（`model_validator(mode="before")` 搬到同一字段；两个都给且不同 → 校验失败）
- [x] 3.4 host 的会话视图 `turns` 字段语义改成「轮数」（数 `turn/start`），内部 `segments` 计数改名 `turns`；`steps` 仍数 `step/start`（判据：一轮两步时视图 `turns == 1`，`test_the_session_view_counts_turns_not_steps`）
- [x] 3.5 **人可见**文案按「轮/步」改口：`[段]` → `[轮] 收尾`（与目标轮的 `[轮] n/cap` 区分），`usage` 的 help 改「按步汇总」、`SESSION_BUSY` 的 detail 改「会话正在跑一轮」。`[轮] n/cap` 仍专指目标轮。**模型可见文本不改**（`SYSTEM_PROMPT`、工具 `description`、工具结果）：2026-11-24 实测改 `SYSTEM_PROMPT` 会让金样本 `replay` 在 seq=3 报 `REPLAY_MISMATCH`，已回退；那属于行为面，另立 change
- [x] 3.6 **API JSON 键**（2.2 说「留到 3.4」，3.4 只做了 host 视图，漏在这里）：`minihns usage` 输出 `steps[]` / `step_id`（原 `turns[]` / `turn_id`）；SSE `model/delta` 帧 `{step_id, index, text}`（原 `turn_id`）。两处都是「把步的 id 记在轮的键下」，一轮两步时会自相矛盾——真实端点场次 2 第一次跑就露出来了。delta 规格：`usage-metering`、`host-api`；判据：`test_the_usage_command_prints_steps_and_total`、`test_the_event_stream_mixes_durable_and_delta_frames`（后者加了键集合与「与同一步 `model/response` 对齐」两条断言，变异改回 `turn_id` 会被杀）

## 4. 规格与文档

- [ ] 4.1 `openspec/specs/` 全量改词：`turn-loop`、`event-log`、`event-stream`、`cli`、`config-layering`、`chat-repl`、`host-api`、`session-resume`、`subagent-delegation`、`usage-metering`。**延后到 m13 归档之后**：m13 的 delta 会在归档时把旧词写进主规格，现在改会被覆盖
- [x] 4.2 `GLOSSARY.md`：三条时间词重写为「轮（turn）／步（step）／目标轮（goal round）」，加 `_历史_` 一行说明 2026-11 之前写作「段／回合」；`_Avoid_` 行同步换词
- [ ] 4.3 `docs/reference/`、`docs/roadmap.md`、`docs/CURRENT.md` 改词；历史文档与归档 change 不动
- [x] 4.4 本 change 的 delta 规格：`event-log`（schema v2、只接受 2、v1 被拒）、`turn-loop`（三层词与事件名）、`cli` / `config-layering`（`max_steps` 主名与旧名窗口）。**delta 写归档后的最终态**，改造期的上迁只作一次性验证（见 5.2）

## 5. 收尾

- [x] 5.1 机械替换漏网扫描：`rg '\bsegment|segment_id|max_turns|first_turn_index' src tests` 只剩两份「旧名被拒」用例里的 `segment/*`（`test_event_schema_v2.py`、`test_event_vocabulary.py`——判据要钉的就是它被拒）。`src` 里 `segment` / `segments` 标识符全部改 `turn` / `turns`（含 `_segment_failure`、`settle_segment`、`_begin_segment`、`_run_segment`、`_print_segment_note`、`_SEGMENT_NOTE_SUPPRESSED`、SSE 帧的 `segment_id` 键）
- [x] 5.2 删除前基线门禁：**887 passed / 7 skipped**、ruff / mypy / `validate` 绿；金样本 `replay` exit 0（一次性证书，2026-11-24 02:00）。**这是改造期的一次性等价性证据，与归档后的规格不冲突**——`event-log` delta 写的是最终态（v1 记录 `SCHEMA_UNSUPPORTED`），这里要的是「删除兼容层之前，旧输入在新代码下逐点相等」
- [x] 5.3 **删除兼容层**（design D4）：`LEGACY_EVENT_TYPES`、`_V1_TYPE_MAP`、`_V1_KEY_MAP`、`_V1_VALUE_MAP`、`_upcast_v1`、`migrate_schema`、`SchemaUnsupported`、`is_current_type`（与 `is_known_type` 合流）、`tests/test_v1_fixture.py`、v1 fixture、`--max-turns`、`[session] max_turns` 键映射、`subagent` 旧参数名
- [x] 5.4 版本门前置：`_records_from_lines` 先看 `schema_version` 再 `model_validate`，v1 行读到 `SCHEMA_UNSUPPORTED` 而非 `LOG_UNREADABLE`（`test_a_v1_line_is_rejected_with_schema_unsupported`、`test_other_schema_versions_are_rejected`）
- [x] 5.5 删除后复跑：**877 passed / 7 skipped**、ruff / mypy / `validate` 绿；`minihns replay 112b5ce8… --session-dir sessions` 返回 `SCHEMA_UNSUPPORTED`（exit 1）
- [x] 5.6 `CURRENT.md` 记账：schema 版本 2、`sessions/` 14 份 v1 样本作废、兼容层已删（提交 `e9c43a2`）
- [x] 5.7 真实端点验收（ADR-0024 的「真实那一半」）：**2026-11-24 通过**，端点 OpenRouter `qwen/qwen3.8-27b`，会话 `1ef237b3d66f4da98a002a80eda2f7b9`。三场：`run` 退出码 0 / `stop_reason MODEL_COMPLETED` / 16 行全 v2 / 一轮两步 / 无 `segment/*`；`usage` 的 `steps[]` 与两条 `model/response` 逐字段相等（203/2816/0/70、297/2816/0/59，`total` 500/5632/0/129）；同日志 `replay` exit 0（seq=3、seq=10 逐点相等）。明细见 `docs/verification/align-turn-step-naming-real-endpoint.md`；场次 2 当场暴露 3.6 的键名残留，已同批修掉
- [ ] 5.8 UAT 验收（人跑，tty 场次 agent 不得代跑）：三场手册已立 `docs/verification/align-turn-step-naming-uat.md`（run 的词与日志形状、`[轮] 收尾` 提示、host 视图 `turns` 与重启一致）；结果列待填，填完才能归档
- [x] 5.9 变异测试一轮：三条变异，版本门与词表判据各杀死；host 重启扫描那条**存活**，补 `test_a_restarted_list_rebuilds_turns_from_turn_starts` 后杀死。记录在 `docs/verification/align-turn-step-naming-mutation.md`
- [x] 5.10 Learning Gate：L-097（模型可见文本不在改名范围，金样本 `replay` 当场抓出）、L-098（同一语义的两条实现路径要各有一条判据）进收件箱；`basetemp` 残留那条是工具事实，记在 `CURRENT.md` 的环境条目而不是 lessons。未晋升进 AGENTS.md（Seen 1，未达阈值）
