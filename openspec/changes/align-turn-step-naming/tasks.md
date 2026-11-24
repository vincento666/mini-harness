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
- [ ] 2.5 注释与 docstring 里的「段/回合」改「轮/步」。**排在 3.5 之后**：同一句注释里常同时出现 `max_turns` 字段名与 help 文案，提前改会出现「注释说步、help 说回合、字段叫 max_turns」的三重不一致；字符串字面量与 help 文案归 3.5。逐处判断，`字段`/`阶段`/`整段替换`/`一段摘要` 这类普通语义不动

## 3. 入口与配置（seam ⑥）

- [x] 3.0 会话内命令去 flag（2026-11-23 先落，先于全量改名）：`/goal edit` 只吃正文；`--max-rounds` 移到 `minihns goal <id> edit`；会话内动词不吃参数（`tests/test_goal_commands.py`、`tests/test_cli_goal.py`）

- [ ] 3.1 `--max-steps` 主名 + `--max-turns` 隐藏别名（弃用提示一次）；同批改 argparse dest、`EffectiveSettings.max_turns`、`SessionSettings.max_turns → max_steps`——它们与 3.2 是同一根线，3.1 与 3.2 必须打包成一个提交
- [ ] 3.2 `[session] max_steps` 主键 + 旧键 `max_turns` 映射；`BUILTIN_DEFAULTS` 键、`config/load.py` 的校验表、`cli/host.py` 的 `_SESSION_INT_FIELDS` 一并改；两者冲突 → `INVALID_ARGUMENT`
- [ ] 3.3 `subagent` 的 `max_turns → max_steps`（旧参数名仍接受）
- [ ] 3.4 host 的会话视图 `turns` 字段语义改成「轮数」，内部 `segments` 计数改名 `turns`
- [ ] 3.5 `chat` / `host` 的可见文案按「轮/步」改口；`[轮] n/cap` 仍专指目标轮

## 4. 规格与文档

- [ ] 4.1 `openspec/specs/` 全量改词：`turn-loop`、`event-log`、`event-stream`、`cli`、`config-layering`、`chat-repl`、`host-api`、`session-resume`、`subagent-delegation`、`usage-metering`
- [ ] 4.2 `GLOSSARY.md`：三层词、`Avoid` 行、2026-11 之前的旧写法说明
- [ ] 4.3 `docs/reference/`、`docs/roadmap.md`、`docs/CURRENT.md` 改词；历史文档与归档 change 不动
- [ ] 4.4 本 change 的 delta 规格：`event-log`（schema v2 + 上迁）、`turn-loop`（词与事件名）

## 5. 收尾

- [ ] 5.1 机械替换漏网扫描：`rg '\bsegment|segment_id|max_turns|first_turn_index' src tests` 只剩兼容层与 v1 fixture
- [ ] 5.2 删除前基线门禁：全量测试 + 覆盖率 + `openspec validate --all --strict`；金样本 `replay` exit 0（一次性证书拿到）
- [ ] 5.3 **删除兼容层**（design D4；合并前必做，未勾不得归档、不得合入 `main`）：`LEGACY_EVENT_TYPES`、`_V1_TYPE_MAP`、`_V1_KEY_MAP`、`_upcast_v1`、`migrate_schema` 的 N-1 分支、`is_known_type`（与 `is_current_type` 合流）、`tests/test_v1_fixture.py`、v1 fixture、`--max-turns` 隐藏别名、`[session] max_turns` 键映射、`subagent` 旧参数名
- [ ] 5.4 版本门前置：`_records_from_lines` 先看 `schema_version` 再 `model_validate`，v1 行读到 `SCHEMA_UNSUPPORTED` 而非 `LOG_UNREADABLE`（`test_event_schema_v2`）
- [ ] 5.5 删除后复跑四道门禁与 `validate`；任取一份 `sessions/*.jsonl` 跑 `replay`，确认报 `SCHEMA_UNSUPPORTED`——不是崩溃，也不是 `LOG_UNREADABLE`
- [ ] 5.6 `CURRENT.md` 记账：schema 版本 2、`sessions/` 14 份 v1 样本作废、兼容层已删与删除提交号
- [ ] 5.7 Learning Gate：把「交换型改名必须用占位符」「金样本是一次性证书不是常驻资产」「删兼容层不需要升 schema 版本」记进 `docs/lessons.md`（若可复用）
