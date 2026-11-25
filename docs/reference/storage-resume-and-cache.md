# 存储、恢复与 fold 缓存

**定位**：M11 的设计说明，不是规格。对外行为以 `m11-storage-resume-and-projection-cache` 的 delta spec 为准。

## 1. 真相与恢复

```text
JSONL 日志 = 唯一真源
  ├─ session/start / user / model / tool / error ...
  ├─ seq 单调，只追加
  └─ session/end 闭合
```

- `EventLog.open` 读最后 `seq`，续写从 `last+1`；
- `chat --resume <id>` 重新装配同一份日志，不写新 `session/start`；
- 硬杀留下未闭合的段时，resume 在 EOF 补 `session/end`，旧记录不改；
- Host 启动时扫 `session/start` + `session/end`，把 ended 会话放进 index；`GET /sessions` 合并进程内活会话与 index；
- 当前 Host resume 只复用同一进程的 ended 会话；完全重启后的 Host resume 仍需把 index 条目重新装配。

## 2. schema 迁移

- 只支持相邻 `N-1 → N`；
- 跳版返回 `SCHEMA_UNSUPPORTED`，不改日志；
- 迁移只改内存副本。

### 2.1 上迁（upcast）是什么

**上迁 = 读的时候把旧版本的记录翻译成当前形状，磁盘上的字节一个都不动。** 它是 append-only 日志的标配：日志是证据，重写历史会让「回放」和「审计」失去可信度；翻译放在读取入口（`read_events` / `LogTail` 共用的 `_records_from_lines`），一次翻译，下游只看见一种形状。

```text
磁盘（v1 行保持原样）
  └─ read_events → EventRecord(v1) → migrate_schema → _upcast_v1 → EventRecord(v2)
                                                                    │
                                              fold / 投影 / replay / SSE 只看见 v2
```

### 2.2 为什么 C 方案必须升到 `SCHEMA_VERSION = 2`

改名不是「加几个别名」那么简单，因为**同一个字符串在两版里意思相反**：

| v1 名字 | v1 含义 | v2 名字 | v2 含义 |
|---|---|---|---|
| `segment/start` | 段（旧词，即今天的轮） | `turn/start` | 轮（新词） |
| `turn/start` | 回合（旧词，即今天的步） | `step/start` | 步（新词） |

如果只把旧名留在词表里当同义词，读到一条 `turn/start` 就无法判断它是 v1 的步（当时叫「回合」）还是 v2 的轮——**不是不认识，而是认错**。所以版本号在这里不是可选的元数据，而是消歧的唯一依据。

`_upcast_v1` 按**一张映射表、逐条记录**翻译，不能做两遍字符串替换（`segment→turn` 的产物会被第二遍 `turn→step` 再改一次，全部塌成 `step`）：

- 类型：`segment/start|end → turn/start|end`；`turn/start|end → step/start|end`；
- 键：`segment_id → turn_id`；`turn_id → step_id`；`turns → steps`；
- `seq` / `ts` / `session_id` / payload 里的值不变。

### 2.3 词表拆成两套

- `CONCRETE_EVENT_TYPES`：**只放 v2 名字**，新写入的唯一合法集；
- `LEGACY_EVENT_TYPES`：只放 v1 名字，**只允许读**，交给上迁；
- `is_known_type` 对两套都真（读侧校验），`is_current_type` 只认 v2（写侧校验）。

这样内部只有一种形状，投影与 replay 不用到处分支。代价是兼容窗口内两套名字都在代码里，测试要同时覆盖「v1 能读」与「v2 才写」。

### 2.4 混合文件与删除点

信封有逐行 `schema_version`，所以同一文件里 v1/v2 混排也能逐行翻译；新追加永远写 v2。删除兼容层的条件（design D4，三条同时成立）：距合并至少两个里程碑、`sessions/` 下不再有需要 `replay` 的 v1 日志、没有外部消费者依赖 v1 事件名。删除时 `LEGACY_EVENT_TYPES`、`_upcast_v1`、旧 CLI/配置别名一起删，`SCHEMA_VERSION` 不动——v1 变成「不支持」，读到即 `SchemaUnsupported`。

**现状（2026-11-23）**：1.x 已落——`SCHEMA_VERSION = 2`，`_upcast_v1` 在 `events/record.py`，写入只认 v2 名字；v1 金样本 `tests/fixtures/logs/v1-goal-tools.jsonl` 的 `replay` 仍通过。2.x 起的标识符改名还没做。

## 3. fold 缓存到底是什么

```text
JSONL --read_events()--> EventRecord[] --fold(cache?)--> AssembledContext
                                              ↑
                          同一前缀才命中；读文件仍要做
```

key：

```text
session_id + 首 seq + 末 seq + 条数 + 内容指纹
```

它缓存的是**日志前缀的 fold 便签**：

- 模型 messages；
- header fingerprint。

它不缓存：

- running/idle、队列、取消、approval future；
- active attempt、delta；
- tool/error/thinking 的 UI 行；
- 远端壳的 projection。

### 什么场景受益

| 场景 | 是否命中 | 说明 |
|---|---|---|
| 同一空闲会话被多个客户端拉 snapshot | ✅ 第一个之后 | 同一 `last_seq` |
| 刷新/断线重连，期间没有新事件 | ✅ | 前缀没变 |
| 连续对话每轮装配 | ❌ | 每轮 seq 都变 |
| `replay` 跑多个装配点 | ❌ | 每点前缀不同，且新进程缓存为空 |
| Host SSE / chat 工具行 | ❌ | 不经过 fold |
| 进程重启后 resume | ❌ | 新进程缓存为空 |

命中也不等于不读日志：key 仍由事件内容计算，省的是重复 fold，不是磁盘读。

DSH 的对应物是常驻 Session 的 `deriveMessages()` 增量缓存和 append 失效；思想相同，mini 是文件后端的降级 memo。

## 4. 投影三态

`projection_states(events)` 给每个 source seq：

- `in_context`：进模型上下文；
- `shadowed`：被压缩遮蔽，日志里还在；
- `log_only`：只留档，如 `error/*`、边界。

重叠 `shadowed_range` 取并集；`session/start` 与 `compaction/summary` 不被误标 shadowed。

## 5. 不做什么

- fork；
- 跨进程共享缓存；
- 跳版迁移；
- 远端日志下载。
