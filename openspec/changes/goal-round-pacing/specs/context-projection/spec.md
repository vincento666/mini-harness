# Spec Delta: context-projection

## MODIFIED Requirements

### Requirement: 系统提示与工具描述是内置常量且只能追加

系统 SHALL 使用内置常量系统提示作为受保护头部的第一条；内置常量之后 SHALL 注入一段 `tool:goal` 政策（`GOAL_POLICY_PROMPT`），当且仅当该会话的 `session/start.payload.goal_policy` 等于 `"v1"`。政策文本 MUST 说明：轮由若干步组成且步数有上限、写满上限只是本轮结束不是失败、人输入开的轮不推进目标轮次、目标 `active` 且已武装且还有轮次额度且没有待回答的问题时轮结束会自动开下一目标轮（MUST NOT 承诺无条件续跑）、创建目标后想分轮就结束本轮、真正完成才调用 `update_goal` 标 `complete`。

`--append-system-prompt` SHALL 把文本追加在政策段之后，MUST NOT 覆盖或移除政策段；MUST NOT 提供替换内置系统提示的入口。折叠 SHALL 从该会话的 `session/start` 取追加文本与 `goal_policy`，MUST NOT 读进程内的当前配置——没有 `goal_policy` 字段的旧日志不注入政策，折叠结果 MUST NOT 因本能力改变。

#### Scenario: 新会话默认带政策段

- **WHEN** 开一个新会话（不传 `--append-system-prompt`）
- **THEN** `session/start.goal_policy` 为 `"v1"`；首条 `context/assembled` 的头部以 `SYSTEM_PROMPT` 开头、含政策段的「写满」「目标轮」等句子

#### Scenario: 追加文本不覆盖政策段

- **WHEN** 传 `--append-system-prompt "额外规则"`
- **THEN** 头部顺序是 `SYSTEM_PROMPT` → 政策段 → `额外规则`；政策段仍在，不被替换

#### Scenario: 旧日志没有字段就不注入

- **WHEN** 回放一份 `session/start` 不带 `goal_policy` 的日志
- **THEN** 每条 `context/assembled` 与重算结果逐字段相等，`REPLAY_MISMATCH` 不出现，头部里没有政策段

#### Scenario: 政策段不可由调用方移除

- **WHEN** 调用方给出任意 `--append-system-prompt` 或配置文件值
- **THEN** 政策段仍出现在头部；没有配置键或 flag 能单独关掉它
