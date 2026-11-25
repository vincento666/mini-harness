# 验证契约

**日期**：2026-11-25（补记：本 change 的 apply 期没有落契约文件，归档前按已完成的实现与判据回写，不新增行为）。

## 目标

把时间词从 v1 的「段 / 回合」改成「轮 / 步」，事件名 `segment/* → turn/*`、旧 `turn/* → step/*`，日志 schema 升到 v2 并拒绝 v1。**行为、事件顺序、额度与退出码 MUST NOT 因改名改变。**

## 可观察行为

1. **新日志只出现 v2 名字**：一次新会话里的事件类型取自 v2 词表，没有 `segment/start`、`segment/end`，也没有 v1 语义的 `turn/start`（它只能是轮的开始）。
2. **v1 日志被版本门拒绝**：`schema_version == 1` 的行读到 `SCHEMA_UNSUPPORTED`（退出码 1），不改写磁盘字节。
3. **flag 与配置键用新名**：`--max-steps` / `[session] max_steps` 生效；`--max-turns` 是未知参数（退出码 2、`unrecognized arguments`、不建日志），`[session] max_turns` 是未知键。
4. **宿主视图的计数语义**：`turns` 数 `turn/start`（轮），`steps` 数 `step/start`（步）；一轮两步时 `turns == 1`。
5. **usage 与 SSE 的键**：`minihns usage` 输出 `steps[]`（每项带 `step_id`）；`model/delta` 帧用 `step_id`；旧键 `turns[]` / `turn_id` 不再出现。
6. **人可见文案按轮/步**：stderr 的收尾行是 `[轮] 收尾 <stop_reason>`；目标轮边界仍是 `[轮] n/cap`。
7. **模型可见文本不变**：`SYSTEM_PROMPT`、工具 `description`、工具结果不动；v1 金样本在新代码下 `replay` 逐点相等（改造期的一次性证书，见 tasks 5.2）。
8. **规格与文档用新词**：主规格与 `docs/reference/` 的当前用法按轮/步；历史说明与迁移映射（`goal-rounds.md` 的术语段、`storage-resume-and-cache.md` 的 v1→v2 表）保留旧词并标注。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | `tests/test_event_vocabulary.py` 全文（词表只含 v2 名）；`tests/test_event_schema_v2.py::test_a_new_log_is_written_as_v2_with_current_names` |
| 1 | `tests/test_vocabulary_reachability.py`：词表里每个取值都有生产者可达，没有词表外的值被写出 |
| 2 | `test_a_v1_line_is_rejected_with_schema_unsupported`、`test_other_schema_versions_are_rejected`（`tests/test_event_schema_v2.py`） |
| 3 | `tests/test_cli_run.py` 的 `--max-steps` 用例与 `tests/test_cli_config.py` 的 `max_steps` 层级用例；旧名拒绝见 `tests/test_cli_run.py` 的 `unrecognized arguments` 断言 |
| 4 | `test_the_session_view_counts_turns_not_steps`、`test_a_restarted_list_rebuilds_turns_from_turn_starts`（`tests/test_cli_host.py`） |
| 5 | `test_the_usage_command_prints_steps_and_total`（`tests/test_metering.py`）；`test_the_event_stream_mixes_durable_and_delta_frames`（`tests/test_cli_host.py`，含键集合与「与同一步 `model/response` 对齐」两条断言） |
| 6 | `tests/test_cli_chat.py` 的 `[轮] 收尾` 断言（stderr 有、stdout 无） |
| 7 | v1 金样本 `replay` exit 0（一次性证书，tasks 5.2，2026-11-24 02:00）；删除兼容层后同一份样本变 `SCHEMA_UNSUPPORTED`（tasks 5.5） |
| 8 | `openspec validate --all --strict` 全绿；`grep` 扫描主规格与 `docs/reference/`，旧名只剩历史说明 |

## 坏法清单（变异种子）

1. **版本门拆掉**：读取时不看 `schema_version`、直接 `model_validate` → 行为 2 红（v1 行报 `LOG_UNREADABLE` 而不是 `SCHEMA_UNSUPPORTED`）。
2. **词表留旧名**：把 `segment/start` 加回 `CONCRETE_EVENT_TYPES` → 行为 1 红（词表判据与可达性判据各打死一次）。
3. **宿主视图按步数轮**：`turns` 数 `step/start` → 行为 4 红（一轮两步时 `turns == 2`）。
4. **usage 键回退**：输出改回 `turns[]` → 行为 5 红。
5. **重启后不重建轮数**：列表扫描只看内存 → 行为 4 的 `test_a_restarted_list_rebuilds_turns_from_turn_starts` 红。

## 不验什么

- **不改模型可见文本**：`SYSTEM_PROMPT`、工具描述、工具结果原样保留（2026-11-24 实测改 `SYSTEM_PROMPT` 会让金样本在 seq=3 报 `REPLAY_MISMATCH`）。那是行为面，另立 change。
- **不改历史文档与归档 change 的用词**：它们保留当时的词，靠 `GLOSSARY.md` 的 `_历史_` 一行换算。
- **不验 v1 上迁**：兼容层已在合入前删除（design D4）；上迁只作为改造期的等价性证据存在过。
- **不改 `max_steps` / `max_rounds` 的默认值**，也不改 `turn/end` 的停止词表。
