# Spec Delta: context-projection

## MODIFIED Requirements

### Requirement: 系统提示与工具描述是内置常量且只能追加

系统 SHALL 使用内置常量系统提示作为受保护头部的第一条；内置常量之后 SHALL 注入一段 `tool:goal` 政策（取自 `GOAL_POLICY_VERSIONS[goal_policy]`，当前版本 `"v2"`），当且仅当该会话的 `session/start.payload.goal_policy` 命中表里的某个版本。政策文本 MUST 说明：轮由若干步组成且步数有上限；写满上限只是本轮结束不是失败；人输入开的轮不推进目标轮次；目标 `active`、已武装、还有轮次额度、没有待回答的问题**且未触发停滞闸门**时，轮结束会自动开下一目标轮（MUST NOT 承诺无条件续跑）；创建目标后想分轮就结束本轮；真正完成才调用 `update_goal` 标 `complete`。涉及 `create_goal` / `update_goal` 的句子 MUST 写成条件句，MUST NOT 给没有这些工具的会话下无条件命令。

政策文本 MUST 按版本冻结：改文案 MUST 新增版本并保留旧版本原文，MUST NOT 就地改写已有版本——`context/assembled` 存了完整 messages，就地改写会让按旧版本记录的日志重算不一致。`GOAL_POLICY_VERSION`（新会话写入的值）MUST 命中 `GOAL_POLICY_VERSIONS` 的某个键。

`--append-system-prompt` SHALL 把文本追加在政策段之后，MUST NOT 覆盖或移除政策段；MUST NOT 提供替换内置系统提示的入口。折叠 SHALL 从该会话的 `session/start` 取追加文本与 `goal_policy`，MUST NOT 读进程内的当前配置——没有 `goal_policy` 字段的旧日志不注入政策，折叠结果 MUST NOT 因本能力改变。

#### Scenario: 新会话默认带政策段

- **WHEN** 开一个新会话（不传 `--append-system-prompt`）
- **THEN** `session/start.goal_policy` 为 `"v2"`；首条 `context/assembled` 的头部以 `SYSTEM_PROMPT` 开头、含政策段的「写满」「目标轮」「停滞」等句子

#### Scenario: 旧版本按原文本重算

- **WHEN** 回放一份 `session/start.goal_policy` 为 `"v1"` 的日志
- **THEN** 头部注入的是 `v1` 的原文，不含 `v2` 才有的「若你有 update_goal 工具」；`replay` 退 0，`REPLAY_MISMATCH` 不出现

#### Scenario: 追加文本不覆盖政策段

- **WHEN** 传 `--append-system-prompt "额外规则"`
- **THEN** 头部顺序是 `SYSTEM_PROMPT` → 政策段 → `额外规则`；政策段仍在，不被替换

#### Scenario: 旧日志没有字段就不注入

- **WHEN** 回放一份 `session/start` 不带 `goal_policy` 的日志
- **THEN** 每条 `context/assembled` 与重算结果逐字段相等，`REPLAY_MISMATCH` 不出现，头部里没有政策段

#### Scenario: 政策段不可由调用方移除

- **WHEN** 配置文件写 `goal_policy = "off"`，或在命令行传 `--goal-policy off`
- **THEN** 配置那条报 `INVALID_ARGUMENT`（未知键），flag 那条报 `unrecognized arguments`；两者都留不下日志文件
- **AND** 正常会话的 `session/start.goal_policy` 仍是 `"v2"`，头部仍含政策段
