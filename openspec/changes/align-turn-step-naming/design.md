# Design

## D1 三层词与映射表

目标形状：**会话（session）⊃ 轮（turn）⊃ 步（step）**；一次目标轮（goal round）就是一次 goal 来源的 turn。

| 现名 | 新名 | DSH 对应 | 说明 |
|---|---|---|---|
| `segment` / `SegmentOutcome` / `run_turn_segment` | `turn` / `TurnOutcome` / `run_turn` | turn | 一条输入展开的那串 step |
| `turn` / `turn_id` / `_run_turns` | `step` / `step_id` / `_run_steps` | step | 一次「装配 → 调模型 → 派发」 |
| `segment_id` | `turn_id` | turn 的 id | 事件载荷 |
| `turns`（段内计数、`RunOutcome`、`session/end`） | `steps` | step 计数 | 数量词 |
| `first_turn_index` | `first_step_index` | step 序号 | 会话内连续 |
| `max_turns` / `--max-turns` / `MAX_TURNS` | `max_steps` / `--max-steps` / `MAX_STEPS` | 单 turn 的 step 上限 | 部署/单次 run 配置 |
| `TurnDeltaSink` | `StepDeltaSink` | step 的流式增量 | 回调名 |
| `segments`（host 的段计数） | `turns` | turn 计数 | host 运行时字段 |
| `rounds_started` / `max_rounds` | 不变 | goal round | 只改中文解释：目标轮号 / 单目标轮数上限 |

**替换顺序**：不能直接 `segment→turn` 再 `turn→step`，否则第二遍会把刚改出来的 `turn` 再改成 `step`。必须用一个临时占位符（`segment→__TURN__`、`turn→__STEP__`、`__TURN__→turn`、`__STEP__→step`），并在每步之后跑测试。事件名同理：`segment/start→__TURN__/start`、`turn/start→__STEP__/start`，再落位。

**`turn_id` 的歧义**：现名 `turn_id` 是 step 的 id；改名后 `turn_id` 是 turn 的 id。所有 `_rec(..., "turn/start", {"turn_id": "t1"})` 之类必须改成 `step/start` + `step_id`，不能只换外层类型名。测试里的 `turn_ids` 变量也要改成 `step_ids`，否则读起来会以为在数 turn。

**出现面（2026-11-23 实测，只算 `.py/.md/.jsonl/.toml`）**：

| 词根 | src | tests | openspec |
|---|---:|---:|---:|
| `segment` | 113 | 261 | 278 |
| `segment_id` | 39 | 71 | 51 |
| `segment/`（事件名） | 17 | 127 | 213 |
| `turn` | 275 | 582 | 800 |
| `turn_id` | 115 | 213 | 99 |
| `turn/`（事件名） | 25 | 136 | 337 |
| `max_turns` / `max-turns` / `MAX_TURNS` | 44 | 167 | 263 |
| `first_turn_index` | 9 | 10 | 8 |

读法：`turn` 的出现面是 `segment` 的 2–3 倍，因为它同时是「旧 turn（将来的 step）」与「turn/start 事件名」。所以**不能按词频估工作量**——真正的顺序必须是「先事件名、再类型名、再变量名」，每步跑测试。

三个已确认的坑：

1. `turn_id` 现在指 step 的 id，改名后指 turn 的 id。`_rec(..., "turn/start", {"turn_id": "t1"})` 必须变成 `step/start` + `step_id`，不能只换外层。
2. 变量 `turns` 同时出现在三处语义：段内计数（→ `steps`）、`RunOutcome` 字段（→ `steps`）、host 的 `segments`（→ `turns`）。第三处是**反向**改名，最容易漏。
3. 测试里的 `turn_ids`、`_segments()`、`first_turn_index` 是断言读法的一部分，改名后测试名也要改，否则「测试说 turn、代码说 step」。

## D2 日志 schema v2：读取时上迁，不重写文件

信封已有 `schema_version`（`events/record.py`），且 `migrate_schema` 只接受 N-1 → N。这正是兼容层的落点：

1. `SCHEMA_VERSION = 2`；新写入一律 v2 名字。
2. v1 行在 `migrate_schema` 里做整体上迁：
   - 类型：`segment/start|end → turn/start|end`；`turn/start|end → step/start|end`。
   - 键：`segment_id → turn_id`；`turn_id → step_id`；`turns → steps`；`session/start` 的配置快照 `max_turns → max_steps`。
   - 封闭词表里的值：`stop_reason` 的 `MAX_TURNS → MAX_STEPS`。只对点名过的键做值映射，载荷里的自由文本不动。
   - `seq` / `ts` / `session_id` 与其余值不变。
3. 词表拆成两套：`CONCRETE_EVENT_TYPES` 只放 v2 名字（新写入的唯一合法集）；`LEGACY_EVENT_TYPES` 只放 v1 名字，**读取时**允许通过校验，交给上迁。`EventRecord._type_is_in_the_vocabulary` 读 `is_known_type`，后者对两套都返回真；写侧另用 `is_current_type` 拒绝旧名。**两套词表只在改造期成立**：删除点见 D4，合并前回到一套。
4. `read_events` 逐行 parse → `migrate_schema` → 交给调用方。投影、折叠、replay、SSE 都只看见 v2。
5. 旧日志文件 MUST NOT 被重写：上迁是纯函数，磁盘上的 v1 行保持原样；下一次追加才写 v2。混合文件不可能出现——一个会话一个文件，schema 在 `session/start` 时固定。

**为什么不把 v1 名字留在词表里当同义词**：那样新日志也可能写出旧名，两种形状会长期并存，投影与 replay 要到处分支。上迁集中在入口一次，内部只有一种形状。

**为什么不用 `session/start.payload.schema`**：信封已经有逐行的 `schema_version`，再加一个会话级字段会出现两个真源。逐行版本足够判定这一行怎么读。

## D3 CLI / 配置的兼容窗口

改名是破坏性的，但用户手里的脚本与 `mini.config.toml` 不该在同一天断：

- `--max-steps` 是主名；`--max-turns` 保留为**隐藏别名**（help 里不列），解析后写同一个字段，stderr 打一次弃用提示。
- `[session] max_steps` 是主键；旧键 `max_turns` 仍被接受，装载时映射并打一次弃用提示；两个键同时出现且值不同 → 拒，不猜。配置层内部用 `CONFIG_INVALID_VALUE` 承载这次拒绝，出口统一是 `INVALID_ARGUMENT`（`assemble` 只把 `ConfigFailure.detail` 搬过去）。
- `subagent` 工具的参数 `max_steps` 是主名；旧 `max_turns` 仍接受（模型可能从旧提示词里学到它），映射到同一字段。
- 事件名与日志 schema **不提供双写**：新日志只写 v2，旧日志只读。
- 兼容窗口到本 change 合并前为止：旧 flag / 旧配置键 / 旧参数名与日志上迁共用同一个删除点（D4）。

## D4 兼容层的删除点：本 change 合并前

**已裁（2026-11-23）**：不留常驻兼容层。依据是可核实的事实——项目未上线，`sessions/` 下 14 份日志全部 `schema_version=1`（其中 12 份含 `segment/*`，每份 2–8 行），仓库外没有消费者，没有任何读者依赖旧日志可读。常驻 `LEGACY_EVENT_TYPES` + `_upcast_v1` 会把本仓库永久维持在两套事件词表上，而它换来的价值接近零。

所以 v1 上迁是**改造期的临时脚手架**，不是产品特性：

1. **它服务什么**：证明这次置换没做错。`turn` 在两版里指称相反（v1=回合，v2=轮），字面替换不可判定；唯一可靠的判据是「旧代码产生的输入 + 新代码跑出的输出 + 逐点相等」，而这份输入必须在动代码之前冻结。该输入就是 `tests/fixtures/logs/v1-goal-tools.jsonl`（50 事件）。
2. **什么时候删**：4.x 改词完成、5.1 漏扫干净、5.2 门禁绿之后，**在本分支上、归档与合并之前**。删除提交排在归档提交之前；5.3 未勾不得归档。
3. **删除动作**（一次提交做全，不留半套）：
   - `vocabulary.py`：删 `LEGACY_EVENT_TYPES`；`is_known_type` 与 `is_current_type` 合流成一个读写共用谓词（只认 v2 名字与 `error/*`）。
   - `record.py`：删 `_V1_TYPE_MAP`、`_V1_KEY_MAP`、`_upcast_v1`、`migrate_schema` 的 `SCHEMA_VERSION - 1` 分支；`migrate_schema` 退化为「版本必须是当前版本，否则 `SchemaUnsupported`」。
   - `reader.py`：版本门**前置**——先看 `schema_version` 再 `model_validate`。否则 v1 行会先在类型校验处失败，得到 `LOG_UNREADABLE` 而不是 `SCHEMA_UNSUPPORTED`。
   - 测试：删 `tests/test_v1_fixture.py` 与 v1 fixture；`test_event_schema_v2.py` 只留 v2 用例；补一条「v1 日志读到 `SCHEMA_UNSUPPORTED`」的判据。
   - 入口：删 `--max-turns` 隐藏别名、`[session] max_turns` 键映射、`subagent` 的旧参数名。
4. **删除后 v1 日志的表现**：`minihns replay sessions/*.jsonl` 对这些文件一律返回 `SCHEMA_UNSUPPORTED`。这是**预期行为**，不是缺陷；那 14 份文件在 `CURRENT.md` 记为作废样本，不再参与任何判据。
5. **`SCHEMA_VERSION` 不动**：保持 2。升到 3 会把现有 v2 日志变成「旧版」，凭空造出新的兼容负担；删兼容层不需要升版本。
6. **不保留「只读旧名」的分支**：那等于把兼容层变成第二套词表，永久存在，正是本节要消除的东西。

## D5 中文术语：段→轮、回合→步

英文对齐之后，中文也必须跟着对齐，否则讨论仍然错位：

- **轮（turn）**：一条输入展开的那串步；`run` 起手一轮，goal 续跑每轮一轮。
- **步（step）**：一次「装配 → 调模型 → 派发」。
- **目标轮（goal round）**：一次 goal 来源的轮；`rounds_started` 数它。
- 现有「段」全部改「轮」；现有「回合」全部改「步」。`[段]` 这行 stderr 文案改成 `[轮]`？不——`[轮] n/cap` 已经被 goal 轮占用。普通轮的收尾提示改成 `[轮]` 会与 goal 轮混淆；保留一个中性的 `[turn]` 或改成 `[轮] 收尾`。设计选 `[轮]` + 明确后缀（见 tasks 3.5），具体文案在实现时由 chat-repl 规格钉住。

**历史文档不改**：`docs/CURRENT-history.md`、`docs/lessons-archive.md`、`openspec/changes/archive/` 保持原词。它们是当时的事实记录，改词等于伪造历史；新文档用新词，并在 `GLOSSARY.md` 留一行「2026-11 之前写作段/回合」。

## D6 不选的方案

- **A（只保留映射表）**：现状。已经三次读错，不改。
- **B（只改面向人的词，代码与日志不动）**：`--max-turns` 与事件名仍是错的，跨仓库对照还要翻译；收益只有一半。
- **只改代码标识符，不改日志 schema**：事件名仍错位，`replay` 与外部消费者继续按旧词理解；而且下一次改 schema 仍要面对同一批旧日志。
- **重写旧日志文件**：不可逆、需要备份、会改变 `seq`/`ts` 之外的字节；读取时上迁更便宜，也保留了原始证据。

## D7 验证策略

- **v1 金样本（一次性证书，不是永久资产）**：`tests/fixtures/logs/v1-goal-tools.jsonl` 在动代码之前冻结；改名的每一步都跑它，`replay` 必须退出 0 且逐点相等。它的有效期到 5.3 删除兼容层为止——验完与兼容层一起删（D4）。
- **v2 形状**：新会话的事件类型集合与 v2 词表完全相等；不出现 `segment/*` 或旧 `turn/*` 语义。
- **别名**：`--max-steps` 与 `--max-turns` 跑同一 fixture，日志除 `session/start` 的配置快照外逐字段相等；旧配置键可用。
- **机械替换的漏网**：`rg '\bsegment|segment_id|max_turns|first_turn_index' src tests` 必须只剩兼容层与历史 fixture；`rg '"turn/start"'` 在 src 里必须只指向 step 的新名（即 `step/start`）。
- **全量门禁**：ruff / mypy / pytest / coverage / `openspec validate --all --strict`。

## 风险

- **交换型替换的顺序错误**：`segment→turn` 与 `turn→step` 互相覆盖；必须用占位符并分步跑测试。
- **`turn_id` 语义翻转**：旧 `turn_id` 是 step，新 `turn_id` 是 turn；任何只改类型名不改键的地方都会让日志自洽校验变松。
- **旧日志在投影层的表现**：`todos` 在 `segment/start` 清空，改名后是 `turn/start`；如果上迁漏了这条，旧日志的待办投影会变成「从不清空」。
- **文档大面积改动**：`openspec/specs/` 里所有提到 `turn/start` 的 requirement 都要改；漏一处就会在 `validate` 或下一次 apply 时暴露。
- **删除动作被拖延**：兼容层拖过一次合并就变成常驻负债，而它换来的价值接近零（项目未上线、无外部消费者）。D4 的删除点是硬条件，5.3 未勾不得归档、不得合入 `main`。
