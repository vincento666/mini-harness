# Proposal

## Why

mini 的三层时间词与 DSH 官方词是**错位**的：

| 现在（mini） | DSH 官方 | 关系 |
|---|---|---|
| 段（segment） | turn | 同构，名字不同 |
| 回合（turn） | step | 同构，名字不同 |
| 轮（round） | goal round | 同构；DSH 的 goal round 就是一次 turn |

这层错位已经造成三次真实成本：① 读 DSH 源码时把 `turn/start` 当成 mini 的 `turn/start`，把额度清空点读错；② 写规格时必须每次注明「本项目的段对应 DSH 的 turn」，否则复核者按字面理解；③ `--max-turns` 在 mini 是「一段内几步」，在 DSH 语境里却像「几个 turn」，讨论长任务时反复歧义。

2026-11-20 人裁：**按 C 方案全量对齐**——`segment → turn`、`turn → step`，含事件名与日志 schema；单立 change；旧日志在回放侧兼容，到历史日志作用可忽略时删除兼容层。

## What Changes

- **代码标识符**：`SegmentOutcome → TurnOutcome`、`run_turn_segment → run_turn`、`RunOutcome.turns → steps`、`first_turn_index → first_step_index`、`TurnDeltaSink → StepDeltaSink`；`segment_id → turn_id`、`turn_id → step_id`。
- **事件类型**：`segment/start|end → turn/start|end`；`turn/start|end → step/start|end`。事件总数不变。
- **事件载荷**：`segment_id → turn_id`；所有原来的 `turn_id → step_id`；`segment/end.turns → turn/end.steps`；`session/end.turns → steps`。
- **CLI / 配置**：`--max-turns → --max-steps`；`[session] max_turns → max_steps`；`subagent` 工具的 `max_turns → max_steps`；`MAX_TURNS → MAX_STEPS`。旧 flag / 旧配置键保留一个兼容窗口（见 design D3）。
- **中文术语**：`段 → 轮`（turn）、`回合 → 步`（step）；`轮（goal round）` 保留为「目标轮」，因为它就是一次 goal 来源的 turn。`GLOSSARY.md`、`docs/`、规格里的旧词一并改。
- **日志 schema**：`SCHEMA_VERSION` 从 1 升到 2；`migrate_schema` 对 v1 行做**类型与键的整体上迁**（`segment/* → turn/*`、`turn/* → step/*`），回放与投影读到的都是 v2 形状。旧日志仍可 `replay` 且逐点相等。
- **兼容删除点**：见 design D4。删的时候连同 `LEGACY_EVENT_TYPES`、`_upcast_v1` 与对应测试一起删。

## Capabilities

### Modified

- `turn-loop`：三层词与事件名、`max_steps`、段→轮的边界表述。
- `event-log`：schema v2 与 v1 上迁；词表只写 v2 名字，旧名只读。
- `event-stream`：帧里的 `event` 名随词表变化；游标语义不变。
- `cli`：`--max-steps` 与旧 `--max-turns` 别名；`/goal` 文本里的「轮」不变。
- `config-layering`：`max_steps` 与旧键别名。
- `chat-repl` / `host-api` / `session-resume`：段→轮的可见文案与字段名；行为不变。
- `subagent-delegation`：子会话的 `max_turns` 参数改名。
- `usage-metering`：报告列里的 step 计数改名。

## Impact

- 代码面：`segment` 在 `src` 186 处、`tests` 412 处；`turn` 在 `src` 1329 处、`tests` 1587 处。绝大多数是机械替换，但 `turn_id`/`segment_id` 与事件名必须按映射表成对交换，不能直接全局替换。
- 日志面：所有旧日志是 v1；新日志是 v2。混合目录必须能同时读。
- 文档面：`GLOSSARY.md`、`docs/reference/`、`openspec/specs/` 里的三层词全部要改；`docs/CURRENT-history.md` 与归档 change 不改（历史记录保持原词，避免伪造过去）。
- 兼容窗口：旧 CLI flag / 旧配置键 / 旧日志读取三件事必须同时成立，否则升级即断。

## 非目标

- 不改行为：段数、轮次额度、事件顺序、投影值、退出码都不变；这是纯改名 + schema 上迁。
- 不改 DSH 的 `round` 词：goal 轮仍叫 round，它是「一次 goal 来源的 turn」。
- 不迁移磁盘上的旧日志文件（不重写 `.jsonl`）：上迁发生在读取时。
- 不改归档 change 与历史文档里的旧词。

## 验收

- 同一份 v1 日志在改名前后 `replay` 都退出 0，且逐点 `context/assembled` 相等。
- 新会话的日志只出现 v2 名字；`event-log` 词表里没有旧名。
- `--max-steps` 与 `--max-turns` 等价；旧配置键可用且给出一次弃用提示。
- 全量门禁与覆盖率不降；`openspec validate --all --strict` 绿。
