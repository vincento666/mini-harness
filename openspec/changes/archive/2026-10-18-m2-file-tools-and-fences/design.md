# Design

## Context

见 `proposal.md` 的 Why。当前实况：`ToolRegistry` 为空、`dispatch_tool_call` 对任何已注册工具只回 `NOT_IMPLEMENTED`、`ToolDefinition` 与 `ToolSpec` 字段相同、`run_session` 有九个关键字参数、`_replay` 折叠时传 `tool_descriptions=()`。六条不变量与已锁定的 38 条决策是硬约束；ADR-0002 记账的 #1 #2 #5 #7 按用户裁决在本 change 处理，#3 #4 #6 继续记账。

## Goals / Non-Goals

**Goals:**

- 让 seam ③（文件工具契约）第一次出现，且能不经回合循环独立测试。
- 让围栏判定只有一处实现，五个工具共用，seam ② 与 seam ⑥ 都能断言它。
- 让「已读过」与「当时有哪些工具」这两个事实都从日志前缀派生，使 `replay` 对注册了工具的日志仍然逐点相等。
- 让围栏拒绝成为可断言的终止结果：配对 `tool/result` → `error/fence` → `turn/end(FENCE_DENIED)` → `session/end` → 退出码 3。

**Non-Goals:**

- 不设计 M3 的并发调度、超时与 `tool/cancelled`；不设计 M5 的窗口预算与投影缓存。
- 不把工具参数的 JSON Schema 送进模型（M2 的参数契约写在工具描述文本里）。
- 不实现 OS 级强制，也不实现 approval 的提权通道。

## Decisions

### D1 落点即 seam 边界

`tools/file_tools.py`（五个工具的执行入口与参数模型）、`tools/fences.py`（工作区边界 + 档位判定 + approval 门）、`tools/dispatch.py`（三段管线：校验 → 围栏 → 执行）、`loop/turn_loop.py`（派发上下文与 `FENCE_DENIED` 终止路径）、`events/vocabulary.py`（词表）、`cli/main.py`（`--sandbox` / `--yes`、退出码 3）。

替代方案：把围栏判定写进每个工具——被否，五份边界代码且 seam ② 无法断言统一行为；写进 `loop`——被否，seam ③ 就没法不经循环独立测。

### D2 派发上下文是一个对象，不是散参数

`dispatch` 收到一个派发上下文：工作区根、`sandbox` 档位、approval 策略、以及从该派发点之前的日志前缀算出的「已读路径集合」。工具只读它，不读进程内状态。

替代方案：把四个事实当四个参数传——被否，与 ADR-0002 第 1 条同病（参数就是 payload）。

### D3 `SessionSettings` 落地（ADR-0002 第 1 条）

新增 pydantic 模型 `SessionSettings`，同时是 `run_session` 的入参与 `session/start.payload` 的来源。M2 参数变多（`sandbox`、`approval`、`tools`），不抽就会让 payload 字段表与函数签名各写一遍。测试改用一个构造 helper。

### D4 `ToolDefinition` 与 `ToolSpec` 分叉（ADR-0002 第 2 条）

分叉确实发生：`ToolDefinition` 需要参数校验模型与「会不会改动」标记（approval 只问改动类），`ToolSpec` 仍是 `name` + `description`。保留两个类型，`specs()` 显式映射。

替代方案：合并成一个——被否，会把围栏标记送进模型契约。

### D5 词表收成 `Literal`（ADR-0002 第 5 条）

`tool/result.outcome`、`turn/end.stop_reason`、`error/fence.code`、`approval/response.decision` 都从 `str` 改成 `Literal[...]`，并与 `events/vocabulary.py` 里的词表常量同源。mypy strict 因此挡得住词表外的值。

### D6 「已读过」集合每次派发前从日志前缀重算

判定 = 该点之前存在针对该规范化路径且 `outcome == OK` 的 `read`。替代方案：进程内 `set[str]`——被否，违反不变量 A（日志之外不得有并列真源），且跨 session 与 replay 的语义会不一致。代价是 O(日志长度) 的重复扫描，M2 场景规模下可接受；缓存属 M5。

路径键 MUST 规范化（解析符号链接与 junction、Windows 上大小写折叠），否则同一文件换一种写法就能绕过 CAS。

### D7 围栏拒绝的终止路径写在 loop 里

`dispatch` 产出「围栏拒绝」结果对象；loop 依次写配对的 `tool/result`、`error/fence`、`turn/end`（`FENCE_DENIED`）、`session/end`，并停止派发同回合剩余调用。内核 MUST NOT 抛异常或 `sys.exit`（M1 的 D6 继续有效）。

替代方案：不终止、只回失败结果——被否，roadmap 的完成判据是「越界写被拒并写事件、退出码 3」。

### D8 approval 门是一个可注入的抽象

`fences.py` 里的 approval 门提供「问一次 → 结论」的接口：CLI 层接真实 stdin（tty 时提问，非 tty 且未 `--yes` 时直接 `UNAVAILABLE`），seam ②① 的测试注入返回 `APPROVED` / `DENIED` 的假门。tty 提问本身用同步读 stdin：M2 工具串行执行，没有并发需求。

替代方案：现在就用 `asyncio.to_thread` 包提问——被否，M2 没有并发收益，且黑盒测试里 stdin 是管道不是 tty。真实 tty 提问只留一条手动 smoke，与 M1 的 Ctrl-C 同一处置（Windows 上 tty 语义经 subprocess 不稳定）。

### D9 既有 M1 场景 fixture 不动，断言搬家

`tool_then_done` 与 `tool_then_exhaust` 调的是 `read {"file_path": "a.md"}`，M1 里产出 `UNKNOWN_TOOL`。M2 里 `read` 真实执行且 `a.md` 不存在，产出 `PATH_NOT_FOUND`（仍是结果，退出码仍 0）。决定：fixture 文件不改，把 `UNKNOWN_TOOL` 的判据移到新增场景 `unknown_tool/turns.json`，既有两条场景的断言改成 `PATH_NOT_FOUND`。

替代方案：给场景配一个 `a.md` 让读成功——被否，会让「M1 场景」的含义变成「M2 场景」，且新增判据本就该由 seam ③ 直接测。

### D10 只读 fixture 仓库

`tests/fixtures/repo/`：5 个 `.md` + 一个可跑的小 pytest 工程（含一个必然失败的用例，供 `grep` 与 `glob` 有真实内容可搜）。每个测试把它复制到 `tmp_path` 当工作区再跑，绝不原地改。

## 测试策略（只在六个 seam 上写）

| seam | M2 覆盖 | 做法 |
|---|---|---|
| ① 回合循环 | 是 | 注入假 approval 门与临时工作区，断言 `FENCE_DENIED` 的终止序列、同回合剩余调用不被派发 |
| ② 工具注册与管线 | 是 | 断言三段顺序（校验失败不做围栏判定、围栏拒绝不执行）、`DENIED_BY_FENCE` 与 `DENIED_BY_APPROVAL` 的区分 |
| ③ 文件工具契约 | **首次出现** | 直接调工具执行入口（不经循环）：五个工具的成功路径与全部文件层失败码；CAS 的读/未读/被外部改动三态；`glob`/`grep` 的排序与上限 |
| ④ 日志追加与折叠 | 是 | 新事件类型与 payload 字段、`error/fence` 的位置、头部工具块从前缀派生 |
| ⑤ Provider 接口 | 是（小） | fixture 声明的 `arguments` 被原样送进派发；既有两条场景的断言按 D9 搬家 |
| ⑥ CLI 黑盒 | 是 | 真实子进程：`--sandbox` 非法取值、`--yes` 批量改 5 个 `.md` 成功、非 tty 未 `--yes` 的写 → 退出码 3、越界写 → 退出码 3、replay 对注册工具的日志仍逐点相等 |

词表可达性判据（Active Lesson 1）：`outcome` 12 个值、`error/fence.code` 4 个值、`approval/response.decision` 3 个值、`stop_reason` 6 个值，每个都至少被一条测试断言到；`tool/cancelled` 与 `model/retry` 各有一条「不出现」的断言。

通用纪律：先写失败测试再写实现，一次一个 red→green 单切片；测试只 mock seam（approval 门、Provider、工作区路径），不 mock 模块内部私有函数；fixture 仓库只读、复制到 tmp 工作区。

## Risks / Trade-offs

- [默认 ask + 非 tty 会让不带 `--yes` 的写场景全部以 3 结束] → stderr 写明 `APPROVAL_UNAVAILABLE` 与被拒工具名，并在 `docs/CURRENT.md` 记一条「跑写场景要带 `--yes`」；不改默认档位（决策 18 已锁）。
- [一次误写就终止整个 session，模型没有重试机会] → `tool/result` 内容里写明被拒路径与原因；这是 roadmap 判据的直接后果，M3 之后再评估「可恢复拒绝」。
- [每次派发前重扫日志算已读集合是 O(n²)] → M2 场景规模小；缓存与投影属 M5，提前做会撞不变量 A。
- [CAS 只防「读过之后被外部改动」，不防同一轮内两个写打架] → M2 工具串行执行，串行本身保证了这一点；并发语义属 M3 的判据。
- [Windows 路径大小写不敏感与 junction 可绕过边界] → 边界与 CAS 都用解析后的规范化路径作键，并有一条「同一文件两种写法」的测试。
- [没有 OS 级强制，工作区内的 `.git` 等目录同样可写] → mini 版故意简化，代价记进 `docs/adr/0003-m2-fence-simplifications.md`，不承诺强制。
- [seam ⑥ 的判据只在 Windows 上跑绿过，仓库没有 CI] → M2 不承诺跨平台；平台绑定点收在四处（路径大小写与 junction、`isatty()`、SIGINT、纯 Python 的文件工具），M3 起按 `docs/roadmap.md` 的裁决加 Windows + Linux 矩阵并让 CI 跑门禁。M2 里不写任何 Windows-only API，所以移植面是稳定的。

## Migration Plan

无破坏性迁移：`--sandbox` 默认 `workspace-write`、approval 默认 ask，M1 的既有场景不含写类工具，行为不变；只有断言按 D9 搬家。M2 合入 `main` 后按流程 archive，六份 delta 同步进 `openspec/specs/`，简化决策写进 `docs/adr/0003-m2-fence-simplifications.md`，`docs/CURRENT.md` 与 `docs/roadmap.md` 的 M2 行更新。

## Open Questions

- `approval/request` 里「关键参数」具体记哪几个字段（只记 `file_path` 还是连 `content` 摘要）——只影响 payload 排版，不影响判定。
- `glob` 的排序时间戳取 mtime 还是 ctime——fixture 仓库里两者一致，可延后。
- `grep` 对读不动的文件（非 UTF-8）是跳过还是计入一条说明——M2 只搜 UTF-8 文本，两种排版都不改判定。
