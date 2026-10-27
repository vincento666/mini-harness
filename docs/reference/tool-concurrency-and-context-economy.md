# 工具并发与上下文经济：M10 的设计底稿

**定位**：M10 开工前的设计备忘，不是规格。对外行为以 M10 的 delta spec 为准；本文只把「为什么这样调度」「省上下文省在哪」写清楚，避免实现时把两件事混成一件。

## 1. 两个目标，两套手段

| 目标 | 手段 | 量什么 |
|---|---|---|
| 更快办完一件事（wall-clock） | 只读工具并发、改动工具独占、结果完成即落盘 | 批次 wall-clock、最大并发数、排队时间 |
| 更少 token 装下同一件事 | 单条结果预算、spill、`read` 范围、`grep`/`glob` 上限、整段压缩 | 峰值上下文、输入 token、压缩/剪枝省下的字节 |

并发**不**省 token：十个 `read` 并行跑，结果还是十条。反过来，剪枝**不**降延迟：它只是让下一次装配小一点。两套指标要分开记（E1）。

## 2. 现状（M3 / M8 的基线）

- `MAX_PARALLEL_TOOLS = 8`；只读调用并发，`write` / `edit` / `bash` 串行。
- 实现是一条「相邻调用」链：第 `i` 个调用等第 `i-1` 个「已开始」；若 `i` 或 `i-1` 会改动，再等 `i-1`「已完成」。效果是**改动调用是 barrier**：它之前的先完成，它之后的等它完成。
- `tool/call` 按声明顺序落盘；`tool/result` 按完成顺序落盘（M8，ADR-0012）。
- 一批调用共享同一份日志前缀（`_dispatch_batch` 开头读一次），围栏的「已读过」判定来自这份前缀。
- `bash` 输出上限 16 KB；`read` 有 `offset` / `limit`（默认 2000 行）但**没有字节上限**，且 `_read_body` 仍把整文件读进内存——一行很长时照样撑爆；`grep` 输出 250 条、`glob` 100 条上限；都没有 spill。

## 3. 并发模型（M10 要落成的形状）

**类别**：`parallel`（只读 / 网络 / 无副作用）与 `exclusive`（会改动工作区、或需要独占资源）。`read` / `glob` / `grep` 是 `parallel`；`write` / `edit` / `bash` 是 `exclusive`。类别是 `ToolDefinition` 的属性，不是每个调用现场判断。

**不变量**：

1. 同一时刻在跑的 `exclusive` ≤ 1。
2. `exclusive` 之前声明的调用必须先完成；它之后声明的调用必须等它完成。也就是 barrier，不是「读写锁」。
3. 同一时刻在跑的 `parallel` ≤ 8。
4. `tool/call` 按声明顺序落盘；`tool/result` 按完成顺序落盘。
5. 取消置位后不再开始新调用；未开始的落 `ABORTED_BEFORE_DISPATCH`，已开始的被打断成 `TOOL_CANCELLED`。
6. 围栏拒绝之后，同批未开始的调用不再派发；已开始的照常收尾。

**实现形状**：保留现有的「链 + 信号量 + 独占锁」，只把 `mutating: bool` 换成 `concurrency` 类别；不要改写成通用 DAG 调度器。理由是现有链已经满足 1–6，而且它把「声明顺序」与「barrier」写在了同一处，改写成调度器会多一层状态机，判据也要重写。**只有 E1 量到「读 → 写 → 读」的长批次被 barrier 拖出明显损失时，才讨论更细的调度。**

**与 M12 的关系**：`subagent` 是 `parallel` 类别；同一批多个 `subagent` 可以并发。但「每会话 8 个工具并发」与「每父会话 8 个活子代理」是两套额度，别混：子会话内部有自己的工具槽，父会话的 `subagent` 槽由 M12 的 `maxActiveSubagents` 管。

**不做**：每工具可配并发数、跨会话并发池、优先级/抢占、把工具调用改写成 DAG、PTC 工具面塌缩。

## 4. 上下文经济（M10 要落成的形状）

**第一个切片：压缩参数可配置**（先于并发与结果剪枝，单独一个红绿循环）：

- 把 DSH `dsh-compaction-basic` 的可调键对应成 mini 的配置：`compaction_threshold_ratio`（对应 `thresholdRatio`，默认 0.8）、`compaction_headroom_tokens`（`headroomTokens`，默认 65536）、`compaction_retain_ratio`（`retainRatio`，默认 0.16）、`compaction_retain_tokens`（`retainTokens`，默认 0 = 用 ratio；>0 时它优先）。
- 默认值必须让现有行为逐点不变；配置只在**新会话**生效。
- 有效值 SHALL 进 `session/start.payload`；`replay` 必须从 payload 取回当时的参数，否则改过配置的日志会 `REPLAY_MISMATCH`。
- 校验：`0 < threshold_ratio <= 1`、`0 < retain_ratio <= 1`、`headroom_tokens >= 0`、`retain_tokens >= 0`；压力预算仍要为正。
- 判据：seam ④ 的公式与边界；seam ① 的 `shadowed_range` 跟着 `retain` 走（`retain_tokens` 覆盖 ratio）；seam ⑥ 的配置层叠、payload 与 replay 相等。

**单条结果的预算**（不进配置，先进规格常量；E1 量到再谈）：

- `read`：已有 `offset` / `limit`（默认 2000 行）；补**字节上限**（例如 32 KiB，取行数与字节先到者），单行超长时截断并留 marker；超出部分落 spill 文件，结果里留 `[已截断；完整内容：<path>]`。
- `bash`：保留 16 KB 上限；超出部分落 spill，结果里留同样的 marker；不再静默丢。
- `grep` / `glob`：已有条数上限；补字节上限，超出留 marker 与「缩小范围」提示；不把 spill 当默认路径（它们是导航工具，不是内容读取）。

**spill**：文件落在工作区内的 `.mini-harness/spill/`（或 `session_dir` 下的子目录），按会话 + 工具调用 id 命名；生命周期到会话结束（M10 不做 GC，M11 可做）。spill 路径必须仍在工作区边界内，否则是围栏问题。

**剪枝与压缩分开**：

- 单条剪枝：一条工具结果太长，就地在折叠时剪短（DSH 的 pruner 形状：阈值 8192、头 4096、尾 1024）。日志里仍保留完整记录，折叠读的是剪短后的内容；这与「遮蔽整段」是两条规则。
- 整段压缩：M5 的 `compaction/summary` 遮蔽一段历史；它不替代单条剪枝，也不依赖 spill。

**CAS 与截断必须用同一份窗口**：`read` 的字节上限一旦生效，`edit` 的写前必读判定要拿同一份截断后的窗口去比（现在两边都用 `_numbered_window`，但字节上限还没有）；否则合法编辑会被误报 `STALE_EDIT`。M10 起草时把「读窗口」抽成一个函数，`read` 与 `edit` 共用。

**前缀复用**：一批调用共享一次前缀读；不要每个工具自己 `read_events`。跨回合的折叠缓存是 M11，不在 M10 做。

## 5. 判据（M10 起草时落成 seam 判据）

- seam ②：`ConcurrencyClass` 的映射；注入一个自定义工具，验证 1–6 六条不变量。
- seam ③：`read` 的 range/limit、超限 marker、spill 文件内容与边界；`bash` 的 spill；`grep`/`glob` 双限。
- seam ⑥：真实子进程里「读 → 写 → 读」批次的 wall-clock 与最大并发数（E1 记录），以及 `SANDBOX_UNAVAILABLE` 的退出码 3。
- seam ④：折叠读到的是剪短后的内容，日志里仍是完整记录；`replay` 逐点相等。

## 6. 开放问题

- `read` 的默认 N 取多少？先按 32 KiB / 2000 行，E1 量到误伤再调。
- spill 目录放工作区内还是 `session_dir` 下？前者便于模型 `read` 回来，后者不污染工作区；M10 起草时裁。
- 单条剪枝的阈值照 DSH 的 8192/4096/1024，还是按 token 算？先按字符，和现有 `/4` 估算一致。
- `bash` 的 16 KB 是 stdout+stderr 合算；spill 要分开存还是合一份？先合一份，带流标记。
