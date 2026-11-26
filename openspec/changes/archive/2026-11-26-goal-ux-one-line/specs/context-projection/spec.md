# context-projection Delta

## MODIFIED Requirements

### Requirement: 系统提示与工具描述是内置常量且只能追加

系统 SHALL 使用内置常量系统提示作为受保护头部的第一条；内置常量之后 SHALL 注入一段 `tool:goal` 政策（取自 `GOAL_POLICY_VERSIONS[goal_policy]`，当前版本 `"v3"`），当且仅当该会话的 `session/start.payload.goal_policy` 命中表里的某个版本。政策文本 MUST 说明：轮由若干步组成且步数有上限；写满上限只是本轮结束不是失败；人输入开的轮不推进目标轮次；目标 `active`、已武装、还有轮次额度、没有待回答的问题**且未触发停滞闸门**时，轮结束会自动开下一目标轮（MUST NOT 承诺无条件续跑）；创建目标后想分轮就结束本轮；真正完成才调用 `update_goal` 标 `complete`。政策文本 MUST 还说明：任务要写文件、改代码、跑命令验证或查多处资料时（哪怕用户只给一句话）第一步就建目标、`objective` 复述用户目标；**建目标的那一轮只做计划、不产出正式内容，正式内容从目标轮 1 开始**；每个目标轮只推进一块可验收的工作、写完停在轮边界，每轮收尾用 `todo` 记一句进度；纯问答、寒暄或一步能做完的小改动不建目标；建完若发现一步能收尾，当轮标 complete。涉及 `create_goal` / `update_goal` 的句子 MUST 写成条件句，MUST NOT 给没有这些工具的会话下无条件命令。

政策文本 MUST 按版本冻结：改文案 MUST 新增版本并保留旧版本原文，MUST NOT 就地改写已有版本——`context/assembled` 存了完整 messages，就地改写会让按旧版本记录的日志重算不一致。`GOAL_POLICY_VERSION`（新会话写入的值）MUST 命中 `GOAL_POLICY_VERSIONS` 的某个键。

`--append-system-prompt` SHALL 把文本追加在政策段之后，MUST NOT 覆盖或移除政策段；MUST NOT 提供替换内置系统提示的入口。折叠 SHALL 从该会话的 `session/start` 取追加文本与 `goal_policy`，MUST NOT 读进程内的当前配置——没有 `goal_policy` 字段的旧日志不注入政策，折叠结果 MUST NOT 因本能力改变。

#### Scenario: 新会话默认带政策段

- **WHEN** 开一个新会话（不传 `--append-system-prompt`）
- **THEN** `session/start.goal_policy` 为 `"v3"`；首条 `context/assembled` 的头部以 `SYSTEM_PROMPT` 开头、含政策段的「写满」「目标轮」「停滞」等句子

#### Scenario: 旧版本按原文本重算

- **WHEN** 回放一份 `session/start.goal_policy` 为 `"v1"` 的日志
- **THEN** 头部注入的是 v1 原文；`context/assembled` 的逐点一致判据不变

#### Scenario: 一句话任务也有分轮依据

- **WHEN** 读取当前版本（`"v3"`）的政策文本
- **THEN** 文本含「要写文件」「第一步就建目标」「建目标的那一轮只做计划」「每个目标轮只推进一块」「纯问答」五处语义；用户提示词里不写任何流程说明也能据此分轮
