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
