# Design

## Decisions

**D1 剪枝的位置与范围。** 在 `tools/dispatch.py` 的收尾（`_bound` 之后）对**非 bash** 的纯文本结果做剪枝：按 Unicode 码点计数，超过 `PRUNE_CHARS = 8192` 时保留头 `HEAD_CHARS = 4096` + 标记 `\n\n[... tool result middle pruned ...]\n\n` + 尾 `TAIL_CHARS = 1024`。`head + marker + tail ≤ threshold`，第二次不触发（幂等）。bash 保持现有的「尾部 16 KiB + spill」：bash 的尾部才是重点，统一会改已有行为与判据。

**D2 spill 与读回。** 被剪枝的全文写到 `<workspace>/.mini-harness/spill/<tool>-<digest16>.txt`，结果里只留相对路径与一句取回指引（`use read with offset/limit, or grep this path`）。路径越出工作区即拒绝。写失败时保留内联结果，并追加一条 `spill/failed` 事件（工具名 + 原因），让失败可观测而不是静默。

**D3 不自动回收。** spill 文件留在工作区，代码不删；文档给清理命令。理由是 `--resume` 的会话可能还引用旧路径。

**D4 计量是日志的纯函数。** `metering.py` 不写新事件：每回合的用量取自 `model/response.payload.usage`，会话总量是把日志折一遍的求和。四个 bucket：`input_uncached` / `cache_read` / `cache_write` / `output`；`reasoning` 是 `output` 的细分，不再加一次。缺 `usage` 的回合跳过，不猜。

**D5 成本由配置提供。** `[pricing.<model>]` 表给每百万 token 的四类单价；缺表或缺字段时金额为 `null`，报告里显示 `n/a`。不内置任何价目表。

**D6 报告面。** 新增 `minihns usage <session-id>`，输出 JSON：`turns[]` 的四桶、`total`、`cost`（可为 null）。E1 以后消费这份 JSON，不实现 E1 本体。

## Risks

- **剪枝可能切断语义关键的中段**：DSH 自己承认「只基于语法」；这里同样接受，取回指引给了读全文的路。
- **字符预算不是 token 预算**：CJK 密度不同；剪枝只保证字符上限，压力判定仍由现有预算公式负责。
- **`spill/failed` 是新事件类型**：fold 不认它，只做审计；加类型要同步 `EVENT_TYPES` 词表。
- **价目表会过时**：所以不内置，缺省 `n/a`。

## 测试与 seam

- seam ②：剪枝阈值/头尾/标记/幂等、spill 路径与读回、写失败保留内联。
- seam ①：回合收尾记账、四桶不重复、缺 usage 跳过。
- seam ④：`spill/failed` 进日志、`usage` 命令的 JSON 形状。
- seam ⑥：`minihns usage` 黑盒一条。
