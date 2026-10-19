# Spec Delta

## MODIFIED Requirements

### Requirement: 工作区边界只约束会改动的操作
系统 SHALL 要求 `write` 与 `edit` 的目标路径解析后落在工作区根之内；`read`、`glob`、`grep` MUST NOT 受该边界约束。边界判定发生在执行之前。没有目标路径的会改动工具（`bash`）MUST NOT 被边界轴判定：它对边界的唯一体现是命令的工作目录固定为工作区根，档位轴照常约束它（ADR-0008）。

#### Scenario: 越界写被拒
- **WHEN** 工作区为 `<dir>` 且模型 `write` 一个解析后在 `<dir>` 之外的路径
- **THEN** 该调用产出 `outcome: DENIED_BY_FENCE` 的 `tool/result`，且该路径上没有任何文件被创建或修改

#### Scenario: 读工作区外不受边界约束
- **WHEN** 模型 `read` 一个工作区之外的绝对路径
- **THEN** 结果是 `OK`，run 不因边界而终止

#### Scenario: 边界轴对 bash 恒真
- **WHEN** 一次 `--sandbox workspace-write` 的 run 里 `bash` 在工作区内写一个文件
- **THEN** 结果是 `OK`，日志里没有 `error/fence`

#### Scenario: 两个档位对 bash 没有可观察差别
- **WHEN** 同一条命令分别在 `--sandbox workspace-write` 与 `--sandbox danger-full-access` 下各跑一次
- **THEN** 两次的 `tool/result.outcome` 相同，围栏没有对命令实际写到哪儿做任何判定

### Requirement: read-only 档位拒绝一切会改动的工具
当 `--sandbox` 为 `read-only` 时，系统 SHALL 拒绝 `write`、`edit` 与 `bash`（`outcome: DENIED_BY_FENCE`），并 SHALL 照常允许 `read`、`glob`、`grep`。

#### Scenario: read-only 下读成功写被拒
- **WHEN** 一次 `--sandbox read-only` 的 run 里模型先 `read` 再 `write` 同一文件
- **THEN** `read` 结果是 `OK`，`write` 结果是 `DENIED_BY_FENCE`

#### Scenario: read-only 下命令不执行
- **WHEN** 一次 `--sandbox read-only` 的 run 里模型请求 `bash`
- **THEN** 结果是 `DENIED_BY_FENCE`，`error/fence` 的 `code` 是 `SANDBOX_DENIES_WRITE`，且命令的副作用没有发生

### Requirement: 围栏拒绝是终止结果
围栏或审批拒绝时，系统 SHALL 先写与该 `tool/call` 配对的 `tool/result`（`outcome` 为 `DENIED_BY_FENCE` 或 `DENIED_BY_APPROVAL`），再写 `error/fence`（payload 字段表由 `event-log` 的「围栏拒绝写 error/fence」规定）与 `session/end`，并以退出码 3 结束。MUST NOT 抛出未捕获异常，也 MUST NOT 继续派发同一回合里尚未开始的工具调用。同一批次里已经开始执行的调用 SHALL 照常写出它自己的 `tool/result`，MUST NOT 因终止而被吞掉。

#### Scenario: 每个 tool/call 仍有配对结果
- **WHEN** 一次 run 因越界写终止
- **THEN** 该越界调用有一条配对的 `tool/result`，日志以 `error/fence` 与 `session/end` 收尾，退出码为 3

#### Scenario: 终止后不再派发后续调用
- **WHEN** 同一回合里模型先请求一次越界写、再请求一次合法读
- **THEN** 只有越界那一次有 `tool/call` 与 `tool/result`，合法读没有被派发

#### Scenario: 已在跑的并发调用不被吞掉
- **WHEN** 同一回合里一个 `read` 已经开始执行、同批的另一个 `write` 被围栏拒绝
- **THEN** 那个 `read` 仍有一条配对的 `tool/result`，日志仍以 `error/fence` 与 `session/end` 收尾，退出码为 3
