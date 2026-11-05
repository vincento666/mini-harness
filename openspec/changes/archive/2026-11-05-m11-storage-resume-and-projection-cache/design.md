# Design

## Context

M11 只补数据/恢复层：日志可续写、session 可 resume、schema 可相邻迁移、Host 可从磁盘重建列表、fold 可缓存且能解释遮蔽状态。不引入 fork、跨进程缓存或新事件类型。

## Decisions

**D1 `EventLog.open(path)` 读最后 seq。** 新增类方法或在 `__init__` 里读最后一条；append 从 `last+1`。空日志从 0。已有 `seq` 只读，不重写。

**D2 resume 是同一份日志的新装配。** CLI `chat --resume <id>` 定位 `<session-dir>/<id>.jsonl`，从现有日志 fold 出上下文并复用 `SessionEnv`；不写新 `session/start`。Host `POST /sessions/{id}/resume` 同理。

**D3 硬杀缺口只补收尾。** 日志末尾有未闭合的 `segment/start`/`turn/start` 时，resume 追加一条 `session/end`（stop_reason 用现有词表）并在 stderr 说明；不伪造缺失的 `model/response`/`tool/result`，也不改旧行。

**D4 schema 迁移是显式表。** 只支持相邻 `N→N+1`；迁移函数读到旧字段、写回新字段，先校验；跳版返回 `SCHEMA_UNSUPPORTED`，不创建/改日志。

**D5 session index 从日志扫描。** Host 启动时扫 `*.jsonl` 的 `session/start` 与 `session/end`，建只读索引；`GET /sessions` 合并进程内活会话与索引。索引缓存可选，但 miss 可重建。

**D6 fold 缓存以 seq 为水位。** 进程内 `_FOLD_CACHE`，key 是 `session_id + 首 seq + 末 seq + 条数 + 内容指纹`；日志 seq/内容变化就重算。缓存不落盘、不共享；损坏/不匹配直接丢弃，返回深拷贝。

**D6.1 cache 是“日志前缀的 fold 便签”，不是会话现场。** 它缓存的是 `AssembledContext`（模型 messages + header fingerprint），不缓存：

- session 的 running/idle、队列、取消、approval future；
- active attempt、delta、tool/error/thinking 的 UI 行；
- 远端壳的 projection。

命中时**仍要读日志**（key 需要事件内容），省的是重复 fold，不是磁盘读。主要受益者是同一前缀被反复折叠的路径：Host 重复 snapshot、同前缀的装配/审计；连续对话每轮 seq 都变，基本不命中；另一个进程（`replay`/远端壳）缓存为空。DSH 的对应物是常驻 Session 的 `deriveMessages()` 增量缓存与 append 失效，思想相同，mini 是文件后端的降级 memo。

**D7 三态投影是 fold 的附带输出。** `projection` 给每个 source seq 打 `in_context` / `shadowed` / `log_only`；`messages` 仍是主输出，三态只给审计/UI。遮蔽区间合并为覆盖集合，后写覆盖先写。

## Risks

- 硬杀日志可能缺多条边界：只补 `session/end`，不冒充完整；
- resume 误开活会话：Host 需 409/拒绝；
- 缓存导致旧消息：水位必须用日志 seq，不用 mtime；
- 迁移写坏：先校验、失败不写。
