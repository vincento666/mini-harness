# fences Specification

## Purpose
定义能力受到的围栏：工作区边界、`--sandbox` 档位、approval 是否问人这三件事各自独立生效，以及围栏拒绝与审批被拒如何作为终止结果落到事件日志与退出码 3。

## Requirements

### Requirement: 围栏两条轴各自独立生效
系统 SHALL 把「能干什么」（`--sandbox` 档位）与「要不要问人」（approval）作为两条互不推导的轴：档位 MUST NOT 决定是否需要问人，`--yes` MUST NOT 改变档位。

#### Scenario: 最高档位仍默认问人
- **WHEN** 执行 `minihns run --sandbox danger-full-access` 且不带 `--yes`
- **THEN** 会改动的工具仍走 approval（tty 时提问，非 tty 时按不可问人拒绝）

#### Scenario: 全自动不放宽档位
- **WHEN** 执行 `minihns run --sandbox read-only --yes`
- **THEN** 写类工具仍被档位拒绝，`--yes` 不使写变得允许

### Requirement: --sandbox 只接受三个档位且默认 workspace-write
系统 SHALL 接受 `--sandbox` 取值 `read-only`、`workspace-write`、`danger-full-access`，默认 `workspace-write`；其它取值 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT`，且在 session 开始之前失败。

#### Scenario: 非法档位不产生日志
- **WHEN** 执行 `minihns run -p "x" --sandbox network-write`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建任何 session 日志

#### Scenario: 默认档位生效
- **WHEN** 执行 run 时不带 `--sandbox`
- **THEN** `session/start` 的 payload 里 `sandbox` 为 `workspace-write`

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

### Requirement: danger-full-access 解除工作区边界但保留写前必读
当 `--sandbox` 为 `danger-full-access` 时，系统 SHALL NOT 施加工作区边界；写前必读与 `edit` 的 CAS 判定 MUST NOT 因此放宽。

#### Scenario: 最高档位可写工作区外
- **WHEN** 一次 `--sandbox danger-full-access --yes` 的 run 里模型先 `read` 再 `write` 一个工作区外的文件
- **THEN** 结果是 `OK` 且该文件被改写

#### Scenario: 最高档位仍要求先读
- **WHEN** 同一次 run 里模型没有 `read` 就 `write` 一个已存在的工作区外文件
- **THEN** 结果是 `WRITE_WITHOUT_READ`

### Requirement: 只有会改动的工具需要问人
在 approval 为 ask（默认）时，系统 SHALL 只对 `write` 与 `edit` 请求人批准；`read`、`glob`、`grep` MUST NOT 产生 `approval/request` 或 `approval/response` 记录。

#### Scenario: 读不问人
- **WHEN** 一次默认档位的 run 里模型调用 `read`、`glob`、`grep` 各一次
- **THEN** 日志里没有任何 `approval/*` 记录

#### Scenario: 每次写恰有一对 approval 记录
- **WHEN** 一次 tty 下的 run 里模型调用 `edit` 两次并都获批
- **THEN** 日志里恰有 2 条 `approval/request` 与 2 条 `approval/response`，每条都带 `turn_id` 与对应的 `tool_call_id`

### Requirement: ask 档位往 stdin 提问并记录问与答
在 approval 为 ask 且 stdin 是 tty 时，系统 SHALL 往 stdin 打印一次提问（含工具名与关键参数），并 SHALL 将答案记录进日志：批准 SHALL 写 `approval/response` 的 `decision: APPROVED` 并继续执行；`y` 或 `yes`（不区分大小写）之外的任何输入 SHALL 写 `decision: DENIED`。

#### Scenario: 回答 y 后执行
- **WHEN** 提问时输入 `y`
- **THEN** `approval/response` 的 `decision` 为 `APPROVED`，随后该 `tool/result` 的 `outcome` 为 `OK`

#### Scenario: 回答 n 是审批被拒
- **WHEN** 提问时输入 `n`
- **THEN** `approval/response` 的 `decision` 为 `DENIED`，该调用产出 `outcome: DENIED_BY_APPROVAL` 的 `tool/result`，run 以退出码 3 结束

### Requirement: 非 tty 且未 --yes 是不可问人拒绝
当 approval 为 ask、stdin 不是 tty 且未给出 `--yes` 时，系统 SHALL 拒绝该次会改动的调用（`outcome: DENIED_BY_APPROVAL`，`approval/response` 的 `decision: UNAVAILABLE`），MUST NOT 挂起等待输入，也 MUST NOT 默认批准。

#### Scenario: 管道里的写请求被拒
- **WHEN** 在 stdin 不是 tty 的进程里执行一次会触发 `write` 的 run 且不带 `--yes`
- **THEN** 该调用产出 `DENIED_BY_APPROVAL`，日志写 `error/fence`（`code: APPROVAL_UNAVAILABLE`），退出码为 3

### Requirement: --yes 全自动且不产生 approval 记录
当给出 `--yes` 时，系统 SHALL 不向人提问、MUST NOT 写 `approval/request` 或 `approval/response`，并 SHALL 照常执行档位与边界允许的会改动调用。

#### Scenario: --yes 下批量改文件
- **WHEN** 一次 `--yes` 的 run 里模型对 5 个 `.md` 各做一次 `read` 与 `edit`
- **THEN** 5 次 `edit` 的结果都是 `OK`，且日志里没有任何 `approval/*` 记录

### Requirement: 围栏拒绝是终止结果
围栏或审批拒绝时，系统 SHALL 先写与该 `tool/call` 配对的 `tool/result`（`outcome` 为 `DENIED_BY_FENCE` 或 `DENIED_BY_APPROVAL`），再写 `error/fence`（payload 字段表由 `event-log` 的「围栏拒绝写 error/fence」规定）与 `session/end`，并以退出码 3 结束。MUST NOT 抛出未捕获异常，也 MUST NOT 继续派发同一回合里尚未开始的工具调用。同一批次里已经开始执行的调用 SHALL 照常写出它自己的 `tool/result`，MUST NOT 因终止而被吞掉。

#### Scenario: 每个 tool/call 仍有配对结果
- **WHEN** 一次 run 因越界写终止
- **THEN** 该越界调用有一条配对的 `tool/result`，日志以 `error/fence` 与 `session/end` 收尾，退出码为 3

#### Scenario: 终止后不再派发后续调用
- **WHEN** 同一回合里模型先请求一次越界写、再请求一次合法读
- **THEN** 只有越界那一次有 `tool/call` 与 `tool/result`，合法读没有被派发

#### Scenario: 终止不吞掉已经派发过的调用
- **WHEN** 同一回合里一个 `read` 先被派发并跑完、同批的另一个 `write` 被围栏拒绝
- **THEN** 那个 `read` 仍有一条配对的 `tool/result`，它在 `error/fence` 之前落盘；日志以 `error/fence` 与 `session/end` 收尾，退出码为 3

### Requirement: error/fence 的 code 词表每个值可达
`error/fence` 的 `code` SHALL 是 `OUTSIDE_WORKSPACE`、`SANDBOX_DENIES_WRITE`、`APPROVAL_DENIED`、`APPROVAL_UNAVAILABLE`；词表外的值 MUST NOT 被写出。

#### Scenario: 四类拒绝各有判据
- **WHEN** 跑完 M2 的围栏测试
- **THEN** 四个 `code` 每个都至少被一条测试断言到

### Requirement: 围栏不做 OS 级强制
系统 SHALL 只由 harness 自身的路径判定与 CAS 判定实施围栏；MUST NOT 依赖或承诺 Windows ACL、job object、受限令牌或 landlock 级别的强制。

#### Scenario: 拒绝只表现为结果与事件
- **WHEN** 一次越界写被拒
- **THEN** 拒绝只体现为 `tool/result`、`error/fence` 与退出码 3，进程没有未捕获异常，也没有对文件系统权限做任何改动
