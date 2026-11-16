# 上下文经济与计量（M14b）的 DSH 一手调研

**日期**：2026-11-14。来源均为官方一手资料，同一提交 `47f943859bef60e4160492346772ded9b24f765a`：

- `packages/compaction/compaction-tool-result-pruner`：<http://dsh.pub/zh/plugins/compaction-tool-result-pruner>
- `packages/spill/spill-local`：<http://dsh.pub/zh/plugins/spill-local>
- `packages/spill/spill-policy`：<http://dsh.pub/zh/plugins/spill-policy>
- `packages/llm/token-meter`：<http://dsh.pub/zh/plugins/token-meter>

只记录该来源明确写出的行为；没写到的标「未记载」。

## 1. 单条结果剪枝（tool-result pruner）

**形状**：`pruneSession(session)` 扫当前表层的一个稳定快照。超预算的结果被**新追加**一条 `tool/result` 替换，携带 `{ surfaceOp: { op: 'replace', start: originalSeq, end: originalSeq }, sourceEventSeqs: [originalSeq] }`；替换「展开完整原始数据，只更改 `content`，保留 `turn`、`step`、`callId`、错误字段、`meta`」。原始事件仍在日志里，可供回放与精确检查。

**语义**：
- 文本按 **Unicode 码点**计；`measureContent(blocks)` 只统计 `text` 块。
- 保留头 `headChars` + 固定标记 + 尾 `tailChars`；标记原文是 `\n\n[... tool result middle pruned ...]\n\n`。
- 默认 `thresholdChars 8192`、`headChars 4096`、`tailChars 1024`；`head + marker + tail ≤ threshold`，因此**第二次扫描不会再改**（幂等）。
- 非文本块保持原相对位置；不拆 UTF-16 代理项对，但可能拆字素簇。
- 会话拒绝替换时同步抛错；本次已提交的替换保留。

**限制（原文）**：字符预算不是 token 预算；剪枝只基于语法，不判断中间哪几行重要；可能拆字素簇。

## 2. spill：外置、读回与回收

**spill-policy**（`tools/post-execute` 转换器）：
- 超过 `maxInlineBytes`（UTF-8 字节；**省略即禁用**）的纯文本结果，经 `ctx.spillStore` 保存全文，替换为「有界首尾预览 + 后端定位信息 + 取回指引」。
- 通知原文形如：`(Omitted N bytes. Full formatted result stored at: /…/session-…/…-web_fetch.txt. Use read with offset/limit, or grep this path to search within it.)`
- 整个替换（预览 + 空行 + 通知）不超过上限：先从预算里留出通知字节，再缩预览；通知自己就占满时预览为空；若连「只有通知」都超限，保留内联结果。
- 不处理：`read` 结果（避免 read → spill → read 循环）、嵌套执行、非 `accept` 决策、含非文本块的结果。
- 失败尽力而为：没有 store、没有会话所有者、`saveText` 拒绝 ⇒ 记警告并原样返回，不把成功调用变成 `isError`。

**spill-local**：
- 布局 `<root>/session-<sha256前缀>/<random>-<safeName>`；根默认是进程私有（0700）临时目录。
- 写入排他且仅所有者可读写（`open(path,'wx',0o600)`），预置的符号链接无法重定向。
- 定位信息是文件路径，取回指引让模型用 `read` / `grep`。
- **回收：DSH 明确不做**——「本地 spill 文件会持续存在，直到外部清理为止」，理由是已恢复或 fork 的会话可能仍在引用该路径。

## 3. token 计量与成本

**token-meter**：
- 固定启发式：**每 4 个字符算 1 token**，再加角色、块与请求 envelope 的结构开销；**没有配置项**。
- `measure(session, requestHeader?)` 在同一日志 revision 上返回请求压力与已计价表层；`estimateMessage(message)` 给单条消息计价。
- **提供方用量复用条件**：最新成功调用的规范请求 envelope 与已测量 envelope 匹配，且总量不低于该调用的完整启发式锚点；后续成功会替换较早锚点；否则完整估算。
- 用量求和不重叠的 **未缓存输入 / cache-read / cache-write / 输出** 四个 bucket；**推理（reasoning）不再加一次**，它是输出的细分。
- 三个会话投影：`tokenUsage`（四个 bucket）、`contextPressure`（`pressureTokens` / `projectedTokens` / `contextWindow`）、`contextBreakdown`（`systemTokens` / `toolsTokens` / `messageTokens`）。
- `projectedTokens` = 提供方锚点 + 自取样以来表层增减的启发式重估，下界钳零；存在理由是压缩本身不追加用量，`pressureTokens` 会滞后。
- **占用率是刻意近似**：「既不是计费记录，也不是门控输入」；harness 里没有任何环节拿它做决策。
- 限制：CJK 与 JSON schema 会被低估；每次测量克隆表层是 O(surface)；envelope 任何字段变了就回退到完整估算。

**成本估算**：DSH 的公开文档**未记载**按金额的成本；只到 token 与四个 bucket。mini roadmap 的「成本估算」需要在 mini 侧自定（价目表从哪来、是否随模型路由）。

## 4. mini 的现状

| 维度 | mini 已有 | 缺口 |
|---|---|---|
| 单条剪枝 | `bash` 只保留 16 KiB 尾部 + spill；`read` 有 `READ_MAX_BYTES`；`glob`/`grep` 各有上限 | 没有通用「头 + 标记 + 尾」剪枝；没有 surfaceOp 式替换 |
| spill | `bash` 超限写 `.mini-harness/spill/bash-<digest>.txt`，结果里留相对路径 | 只有 bash；没有读回指引的统一措辞；没有回收 |
| 计量 | `budget_reading` 读 `usage`；`estimate_tokens` 是 4 字符 1 token | 没有会话/回合聚合，没有成本，没有投影 |
| E1 报告 | 未查（E1 是并行支撑轨） | 上下文/成本列待接 |

## 5. 需要裁决的分叉

1. **剪枝写在哪里**：DSH 用「追加一条替换事件 + `surfaceOp`」，原文留在日志里。mini 的日志是 append-only，选项有两个：
   - A：照 DSH 新增 `surfaceOp` 语义（折叠时用替换节点覆盖旧节点），代价是 fold 与 replay 都要认这个新字段；
   - B：在 dispatch 收尾时直接改 `content`（不保留原文），实现最小，但日志不再有全文、replay 也只能看到剪过的版本。
2. **spill 的回收**：DSH 明确不删。mini 选项：
   - A：照 DSH，不自动删，只在文档里写「由外部清理」；
   - B：会话收尾删本会话的 spill 目录（与 DSH 的恢复/fork 理由冲突，但 mini 没有 fork）。
3. **成本估算**：DSH 未记载按金额计价。mini 要么只做 token（不做金额），要么内置一张价目表（会过时，需要人维护）。

## 6. 概念边界（prune / spill / compaction / projection）

这一节把容易混的五个概念分开。**判断依据是「它改的是哪一层」**：日志（事实）／表层（派生视图）／外部存储（全文副本）。

| 概念 | 改哪一层 | DSH 的载体 | mini 的载体 | 触发点 | 原文还在吗 |
|---|---|---|---|---|---|
| 事件日志 | 事实 | append-only JSONL + zstd | append-only JSONL | 每写一条 | 是（真源） |
| 表层 surface | 派生 | 由日志折叠出的消息序列 | `fold()` 的输出 | 每次装配 | 从日志重算 |
| 剪枝 prune | 进入上下文的形状 | 压缩触发时追加替换节点 + `surfaceOp` | **dispatch 收尾改写 `content`** | 单条结果超 8192 码点 | DSH 在日志；mini 在 spill |
| 外置 spill | 全文放哪 | `spillStore`（`session-<hash>/<random>-<name>`） | `<workspace>/.mini-harness/spill/<tool>-<digest>.txt` | 同一阈值（本 change 合并成一步） | 是（文件里） |
| 压缩 compaction | 历史留多少 | 替换节点遮蔽旧区间 | `compaction/summary.shadowed_range` | 接近窗口压力线 | 是（日志保留，重放可见） |
| 投影 projection | 派生（给 UI/宿主） | `tokenUsage` / `contextPressure` / `contextBreakdown` | 本 change 只出 `minihns usage` 的 JSON | 每次读 | 从日志聚合 |
| 回收 cleanup | 外部存储 | 不做，靠外部清理 | 不做，只给清理命令 | 人工/外部 | — |

三条边界要背下来：

1. **剪枝 ≠ 外置**。剪枝决定上下文里留下什么形状（头 + 标记 + 尾）；外置决定全文去哪（文件/存储）。mini 把两者合成一步，但语义是两件事。
2. **压缩 ≠ 剪枝**。压缩作用于「一段历史」，结果是摘要 + `shadowed_range`，原文仍在日志、重放可见；剪枝作用于「单条结果」，mini 的日志里只留剪后版本。
3. **投影 ≠ 事实**。DSH 明说占用率「既不是计费记录，也不是门控输入」；mini 的 `usage` JSON 同理，只做报告数据源。

### 数据模型上的四个字段

| 字段 | 出处 | 含义 |
|---|---|---|
| `surfaceOp: {op: 'replace', start, end}` | DSH 剪枝 | 用新节点覆盖表层的一段；mini **不采用**（见第 5 节分叉 1 的裁决） |
| `sourceEventSeqs` | DSH 剪枝 | 替换节点引用的原始事件 seq，供回放/审计 |
| `shadowed_range: {start, end}` | mini 压缩 | 被摘要遮蔽的区间，折叠时不产出消息；头部与 `session/start` 不被遮蔽 |
| `pruned: {chars, digest, spill}` | mini M14b | 剪前码点数、剪前全文 sha256、相对路径；用于核对 spill 与原文一致 |

一句话记忆：**日志记事实，表层是折叠，剪枝改形状，外置挪全文，压缩折历史，投影只是读数。**
