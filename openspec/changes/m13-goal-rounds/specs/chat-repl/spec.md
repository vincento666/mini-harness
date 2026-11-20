## ADDED Requirements

### Requirement: 自动轮次在 stderr 留下边界

REPL 里由目标驱动自动开的段（带 goal 轮次），系统 SHALL 在该段开始前向 stderr 打印一行 `[轮] <n>/<cap>`。收尾时：额度用尽 SHALL 打印一行含 `已用尽 <n>/<cap>` 与 `round-limit`；因未决问题交回控制权 SHALL 打印一行含 `目标保持 active` 与「回答后自动继续」；零工具调用的空转 SHALL 打印一行含「已停止自动推进」与 `/goal resume` / `/goal complete`。这些行 MUST NOT 写进事件日志、MUST NOT 出现在 stdout；人工段、`run` 与 `serve` 上的输出 MUST NOT 因此改变。「段不以 `MODEL_COMPLETED` 收尾时打印一行」那条既有规则不变。

#### Scenario: 两轮续跑看得见边界

- **WHEN** 一个上限为 2 的目标在 chat 里连跑两轮
- **THEN** stderr 依次出现 `[轮] 1/2`、`[轮] 2/2` 与含 `已用尽 2/2` 的一行；stdout 里没有这些行

#### Scenario: 未决问题停在哪里看得见

- **WHEN** 第 1 轮问了一个人答不了的问题
- **THEN** stderr 有 `[轮] 1/3` 与含 `目标已暂停` 的一行，没有 `[轮] 2/3`；提示符回到人手里
