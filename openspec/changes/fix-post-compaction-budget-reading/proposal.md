## Why

M5 / M6 / M7 的 UAT 第一轮（人跑，2026-10-23）里最硬的一条事实：`[遮蔽] 折掉 seq 1 至 91：tokens 70485 降至 71030`——**「降至」后面那个数比前面那个大**。第二场同理：`54481 降至 54689`。两组的差值 545 与 208 就是那次摘要自己的大小。

机制在预算读数的校准那一路（`context/budget.py:77-97`）：读数 = `max(估算, 未被遮蔽的非 compaction `model/response` 里最大的 `usage.input_tokens` 回报)`。而遮蔽保留尾部（`budget.py:190-198`）**总是留着最后那几条记录**，其中最新那条回报正是把这次请求顶到越线的那个数。遮蔽砍得动估算，砍不动那条回报：`tokens_after = 同一个回报 + 摘要`（`loop/turn_loop.py:678-682`）→ 只增不减。

后果不止措辞。人报的第三场是：一次溢出之后，**每输入一句都立刻再来一次溢出**（「之前问了什么」「读了哪个文件？」各一条 `[段] CONTEXT_WINDOW_EXCEEDED`）。读数被一个描述过去的数字钉住，压缩在真实端点上救不动任何东西。

mock 那一半永远看不见这条：mock 桩的 `usage` 默认全 0（`provider/contract.py:25`），校准那一路恒为 0，读数只剩估算，遮蔽当然砍得动。四道门禁全绿 + 真实端点跑过 M5 的判据，这条照不出来——它是 ADR-0024「mock 全绿不算完成」目前最干净的一条实锤证据。

无密钥复现已经有了：`.tmp/uat-repro/fixture2.json`（fixture 条目带 `usage.input_tokens`，mock 的 `AssistantTurn` 认这个字段）跑出 `tokens 60000 降至 60002`。

## What Changes

- **给校准加一条界**：一次压缩之前写下的 `model/response` 回报 MUST NOT 继续充当压缩之后的表层读数。校准只认「该装配点之前最后一条 `compaction/summary` 之后」写出的回合级回复回报；没有摘要记录时不设界，全部照旧。
- 于是 `tokens_after` 真的下降，`[遮蔽]` 那一行不再说反话；遮蔽之后读数回到估算，下一次真实请求带回的新回报重新参与校准。
- 溢出之后「每问必溢出」的根因消掉一半（另一半是屏幕上没说清楚，在 `fix-chat-screen-feedback`）。
- 判据补在 seam ④（折叠与预算读数）、seam ①（装配点的判定）、seam ⑥（真实子进程看 `[遮蔽]` 那一行的两个数）。

## Out of scope

- **屏幕上说什么**：`[段]` 那一行的形状、重复词、悬空冒号、session id、「降不下去」的说明——全在 `fix-chat-screen-feedback`。
- **精细的 token 预算管理**：提前看当前表层是否即将立刻满、提前预警并提前压缩，并照 DSH 的做法再做决策。这是人的裁决方向，本 change 不做，也不承诺下一个 change 做（记账见 design 的「不做的事」）。
- 触发线、保留预算、压力预算的公式：那是 `fix-small-window-compaction-dead-zone` 的地盘，本 change 不动。

## Impact

- **主规格**：`context-budget`（MODIFIED 1：「预算读数有两个来源」）。
- **代码**：`src/mini_harness/context/budget.py` 的 `budget_reading` 校准那一路。`loop/turn_loop.py` 里 `tokens_after` 的算法不动——读数算对了它自动对。
- **replay 一致性**：新读数是日志前缀的纯函数，只多依赖「该点之前最后一条 `compaction/summary` 的 seq」这一件事，replay 照旧可派生。这条要有一条判据守住，否则 replay 会开始报 `REPLAY_MISMATCH`。
- **分支与合并顺序**：本 change 的分支从 `fix-small-window-compaction-dead-zone` 的 tip 起。那个 change 已经把溢出判据换成压力预算（`W − O`）、把「无可遮蔽的内容」那句 detail 改成含三个数；在它之前写这些判据，数字在合并时必须重写（它落地时已经翻掉过 8 条 seam ⑥ 判据）。合并顺序：`fix-compaction-and-context-overflow` → `fix-small-window-compaction-dead-zone` → 本 change。
- **编号预留**：ADR-0029 归本 change（「遮蔽之前的回报不再充当遮蔽之后的读数」是一条真实取舍：读数可能低估 provider 侧的真实用量）。
