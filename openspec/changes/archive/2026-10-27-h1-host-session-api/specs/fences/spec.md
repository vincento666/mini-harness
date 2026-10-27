# Spec Delta

## MODIFIED Requirements

### Requirement: ask 档位往 stdin 提问并记录问与答

CLI 入口在 approval 为 ask 且 stdin 是 tty 时，系统 SHALL 往 stdin 打印一次提问（含工具名与关键参数），并 SHALL 将答案记录进日志：批准 SHALL 写 `approval/response` 的 `decision: APPROVED` 并继续执行；`y` 或 `yes`（不区分大小写）之外的任何输入 SHALL 写 `decision: DENIED`。

#### Scenario: 回答 y 后执行
- **WHEN** 提问时输入 `y`
- **THEN** `approval/response` 的 `decision` 为 `APPROVED`，随后该 `tool/result` 的 `outcome` 为 `OK`

#### Scenario: 回答 n 是审批被拒
- **WHEN** 提问时输入 `n`
- **THEN** `approval/response` 的 `decision` 为 `DENIED`，该调用产出 `outcome: DENIED_BY_APPROVAL` 的 `tool/result`，run 以退出码 3 结束

### Requirement: 非 tty 且未 --yes 是不可问人拒绝

CLI 入口在 approval 为 ask、stdin 不是 tty 且未给出 `--yes` 时，系统 SHALL 拒绝该次会改动的调用（`outcome: DENIED_BY_APPROVAL`，`approval/response` 的 `decision: UNAVAILABLE`），MUST NOT 挂起等待输入，也 MUST NOT 默认批准。

#### Scenario: 管道里的写请求被拒
- **WHEN** 在 stdin 不是 tty 的进程里执行一次会触发 `write` 的 run 且不带 `--yes`
- **THEN** 该调用产出 `DENIED_BY_APPROVAL`，日志写 `error/fence`（`code: APPROVAL_UNAVAILABLE`），退出码为 3

## ADDED Requirements

### Requirement: 非 CLI 入口的 approval 门由入口提供

`ask` 档位的提问 SHALL 由一个可替换的 approval 门承担：CLI 入口的门读 stdin，host 入口的门读 HTTP 回程；门 SHALL 只返回 `APPROVED`、`DENIED` 或 `UNAVAILABLE`，MUST NOT 默认批准，MUST NOT 让非 CLI 入口读 stdin。门拿到的 `tool_call_id` SHALL 足以让入口把应答对回那条 `approval/request`。

#### Scenario: host 的门不读 stdin

- **WHEN** host 入口的段因 `write` 停在审批上，stdin 是 tty 且没有任何 HTTP 应答
- **THEN** 该调用不会因为 stdin 有输入而被批准；300 s 后以 `APPROVAL_UNAVAILABLE` 收尾
