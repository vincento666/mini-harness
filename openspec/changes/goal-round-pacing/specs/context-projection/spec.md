# Spec Delta: context-projection

## MODIFIED Requirements

### Requirement: 系统提示与工具描述是内置常量且只能追加

系统 SHALL 使用内置常量系统提示作为受保护头部的第一条；内置常量之后 SHALL 默认追加一段 `tool:goal` 政策（由 `DEFAULT_APPEND_SYSTEM_PROMPT` 给出），文本 MUST 说明：轮由若干步组成且步数有上限、写满上限只是本轮结束不是失败、人输入开的轮不推进目标轮次、目标进行中时轮结束会自动开目标轮、创建目标后想分轮就结束本轮、真正完成才调用 `update_goal` 标 `complete`。

`--append-system-prompt` SHALL 覆盖这段默认追加文本（层叠语义：flag > 配置文件 > 内置默认），MUST NOT 提供替换内置系统提示的入口。折叠 SHALL 从该会话的 `session/start.payload.append_system_prompt` 取追加文本，MUST NOT 读进程内的当前配置——旧日志里该字段是空串，折叠结果 MUST NOT 因本能力改变。

#### Scenario: 新会话默认带头部政策

- **WHEN** 不传 `--append-system-prompt` 开一个新会话
- **THEN** `session/start.append_system_prompt` 非空且含「轮」与「目标」两个词；第一条 `context/assembled` 的头部以内置常量开头、其后是这段政策

#### Scenario: 显式覆盖只剩用户文本

- **WHEN** 传 `--append-system-prompt "额外规则"`
- **THEN** 头部第一条仍是内置常量，追加段是「额外规则」而不是默认政策——不出现两段来源

#### Scenario: 旧日志的折叠不变

- **WHEN** 回放一份 `append_system_prompt` 为空串的旧日志
- **THEN** 每条 `context/assembled` 与重算结果逐字段相等，`REPLAY_MISMATCH` 不出现；头部里没有政策段
