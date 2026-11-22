# Tasks

## 0. 前置

- [ ] 0.1 冻结 v1 金样本：从现有 `sessions/` 挑一份含 goal 轮、工具调用、压缩的日志，复制到 `tests/fixtures/logs/v1-*.jsonl`（不改字节）
- [ ] 0.2 写一张机械替换清单（design D1 的表）并核对 `src` / `tests` 的出现面；确认占位符顺序

## 1. 事件 schema v2 与兼容层（seam ④）

- [ ] 1.1 `SCHEMA_VERSION = 2`；`CONCRETE_EVENT_TYPES` 换成 v2 名字（`turn/*` 是段、`step/*` 是步）
- [ ] 1.2 `LEGACY_EVENT_TYPES` + `is_known_type` 读放行 / `is_current_type` 写拒绝
- [ ] 1.3 `migrate_schema` 的 `_upcast_v1`：类型与键的整体上迁；`seq` / `ts` / `session_id` 不动
- [ ] 1.4 旧日志 `replay` 逐点相等；新日志只出现 v2 名字
- [ ] 1.5 投影（`todos` 在 `turn/start` 清空）、折叠、SSE 都只看见 v2

## 2. 内核标识符（seam ①）

- [ ] 2.1 `SegmentOutcome → TurnOutcome`、`run_turn_segment → run_turn`、`_run_turns → _run_steps`
- [ ] 2.2 `segment_id → turn_id`、`turn_id → step_id`；`first_turn_index → first_step_index`
- [ ] 2.3 `RunOutcome.turns → steps`；`SessionSettings.max_turns → max_steps`；`STOP_MAX_TURNS → STOP_MAX_STEPS`
- [ ] 2.4 `TurnDeltaSink → StepDeltaSink`；注释与 docstring 里的「段/回合」改「轮/步」

## 3. 入口与配置（seam ⑥）

- [x] 3.0 会话内命令去 flag（2026-11-23 先落，先于全量改名）：`/goal edit` 只吃正文；`--max-rounds` 移到 `minihns goal <id> edit`；会话内动词不吃参数（`tests/test_goal_commands.py`、`tests/test_cli_goal.py`）

- [ ] 3.1 `--max-steps` 主名 + `--max-turns` 隐藏别名（弃用提示一次）
- [ ] 3.2 `[session] max_steps` 主键 + 旧键 `max_turns` 映射；两者冲突 → `INVALID_ARGUMENT`
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
- [ ] 5.2 全量门禁 + 覆盖率；`openspec validate --all --strict`
- [ ] 5.3 在 `CURRENT.md` 记兼容删除点（D4 三条）与当前 schema 版本
- [ ] 5.4 Learning Gate：把「交换型改名必须用占位符」「schema 上迁优于重写文件」记进 `docs/lessons.md`（若可复用）
