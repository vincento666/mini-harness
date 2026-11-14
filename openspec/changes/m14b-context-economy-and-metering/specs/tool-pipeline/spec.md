# Spec Delta: tool-pipeline

## ADDED Requirements

### Requirement: 单条工具结果的剪枝与 spill 读回

系统 SHALL 在工具结果写进日志之前，对**非 bash** 的纯文本结果做有界剪枝：文本按 Unicode 码点计数，超过 8192 码点时 SHALL 保留头 4096 码点、固定标记 `\n\n[... tool result middle pruned ...]\n\n` 与尾 1024 码点，MUST NOT 超过阈值。`头 + 标记 + 尾` 之和 SHALL 不大于阈值，因此同一结果第二次处理 MUST NOT 再被改写。

被剪枝的全文 SHALL 写进 `<workspace>/.mini-harness/spill/<tool>-<digest16>.txt`，结果文本 SHALL 只给**相对路径**与一句取回指引（用 `read` 带 offset/limit，或用 `grep` 搜该路径），MUST NOT 写绝对路径。路径越出工作区 SHALL 拒绝写入。

spill 写入失败时 SHALL 保留内联结果（MUST NOT 把成功调用变成失败），并 SHALL 追加一条 `spill/failed` 事件记录工具名与原因。

bash 的结果 MUST NOT 走这条剪枝，它保留现有的「尾部 + spill」策略。

#### Scenario: 超大结果被剪短且给出去向

- **WHEN** 一个非 bash 工具返回 20000 码点的纯文本
- **THEN** 日志里的结果不超过 8192 码点，含标记与相对路径；spill 文件里是全文

#### Scenario: 未超阈值不动

- **WHEN** 结果只有 100 码点
- **THEN** 结果与原文逐字节相等，且没有 spill 文件

#### Scenario: 剪枝是幂等的

- **WHEN** 对同一份已经被剪过的结果再跑一次剪枝
- **THEN** 结果不再变化

#### Scenario: bash 不受影响

- **WHEN** bash 返回超过 16 KiB 的输出
- **THEN** 仍是尾部保留 + 现有 spill 标记，头尾剪枝不触发

#### Scenario: spill 写失败保留内联

- **WHEN** spill 目录不可写
- **THEN** 结果仍是完整内联文本，日志里有 `spill/failed` 事件，调用不被判为失败

### Requirement: 剪枝结果与回放

剪枝 SHALL 发生在写日志之前：日志里的 `tool/result.content` 就是当时模型看到的内容，`replay` MUST NOT 依赖 spill 文件，也 MUST NOT 重新剪枝。

#### Scenario: 回放不读 spill

- **WHEN** 删掉 spill 目录后对同一日志执行 `minihns replay`
- **THEN** 仍逐点相等
