# Proposal

## Why

M10 给了 bash 一条「尾部 16 KiB + spill」的兜底，但只有 bash 有：`read`、`glob`、`grep`、`web` 这些结果要么各自硬截断、要么原样进上下文，模型看到的既不是全文也不是可控的摘要。同时会话里没有任何 token / 成本的可见数字——`budget_reading` 只在压缩判定时读一次 `usage`，没人把它记下来给报告用。

M14b 把这两件事收口：**单条结果的通用剪枝 + spill 读回**，以及**按会话/回合的 token 计量与配置驱动的成本估算**。

## What Changes

- 新增通用剪枝：非 bash 的纯文本 `tool/result` 超过 8192 码点时，保留头 4096 + 标记 `\n\n[... tool result middle pruned ...]\n\n` + 尾 1024，全文写进工作区 `.mini-harness/spill/`，结果里留相对路径与 `read`/`grep` 取回指引。
- spill 不自动回收：文件按 `<tool>-<digest>.txt` 落在工作区；文档里给清理命令，代码不删（`--resume` 的会话可能还引用旧路径）。
- 新增 `usage-metering`：每回合从 `model/response.usage` 聚合未缓存输入 / cache-read / cache-write / 输出四个 bucket，会话级累加；`reasoning` 是输出的细分，不再加一次。
- 成本估算：价目表由配置提供（每百万 token 的输入/输出/缓存单价），缺省不出金额，报告里标 `n/a`；不猜价。
- E1 报告加 `context` 与 `cost` 两列（token 四桶与金额，金额缺省为空）。

## DSH 十项

一手来源：`deepseek-ai/deepseek-harness`（提交 `47f9438`）的 `compaction-tool-result-pruner`、`spill-local`、`spill-policy`、`token-meter`；核对见 `docs/reference/context-economy.md`。

**形状**：DSH 剪枝是「追加一条带 `surfaceOp` 的 `tool/result` 替换」，原文留日志；spill 是「预览 + 定位信息 + 取回指引」；计量是 `measure()` 返回压力与表层、三个投影。mini 的剪枝在 dispatch 收尾直接改 `content`（人裁决），全文进 spill；计量做成日志聚合而非服务。建议：simplified。

**机制**：DSH 的 pruner 在压缩触发时扫表层，spill 在 `tools/post-execute`，meter 按日志 revision 推进。mini 都在 dispatch 收尾与回合收尾做。建议：simplified。

**语义**：剪枝按码点、`head+marker+tail ≤ threshold`、幂等；spill 的替换不超上限、失败保留内联；计量四桶不重复加 reasoning；成本 DSH 未记载。建议：aligned（剪枝/spill），成本 simplified。

**不变量**：日志仍是唯一真源——剪枝后的 `content` 就是日志里的结果，spill 只是可读回的副本；不改写历史。建议：aligned。

**面**：模型面看剪后结果与 spill 路径；日志面记四桶用量；人机面与宿主面本 change 不加命令。建议：simplified（`/usage` 延后）。

**失败与降级**：spill 写失败保留内联并记警告（bash 现在是抛错，通用层按 DSH 的尽力而为）；价目表缺失出 `n/a` 而不是猜。建议：aligned。

**组合与扩展**：只有一层通用剪枝 + bash 自己的尾部保留；没有按工具配置阈值。建议：simplified，触发条件：某个工具需要不同阈值。

**资源与约束**：码点预算 8192、单条消息上限；spill 文件落在工作区、不自动删。建议：aligned。

**信任与授权**：spill 写在工作区内、相对路径、越界拒绝；不写绝对路径。建议：aligned。

**回放与确定性**：剪枝在写日志前完成，回放看到的就是当时日志里的内容；spill 不参与折叠。建议：aligned。

## Capabilities

### Modified Capabilities

- `tool-pipeline`：通用的单条结果剪枝与 spill 读回指引。

### New Capabilities

- `usage-metering`：每回合/每会话的 token 四桶聚合与配置驱动成本估算。

## Impact

- 代码：`tools/dispatch.py`（收尾剪枝）、新增 `src/mini_harness/metering.py`、`loop/turn_loop.py`（回合收尾记账）、`cli`/报告侧加列。
- 测试：seam ②（剪枝与 spill）、①（回合记账）、④（日志 payload）、⑥（黑盒一条）。
- 非目标：`/usage` 命令、按工具配置阈值、自动回收、bash 尾部策略的改动。
- 验收：超大结果被剪短且 spill 可读回；token 四桶与 provider usage 对得上；E1 能出两列。
