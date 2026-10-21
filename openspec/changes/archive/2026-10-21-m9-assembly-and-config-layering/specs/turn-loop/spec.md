# Spec Delta

## MODIFIED Requirements

### Requirement: 未注册工具是 UNKNOWN_TOOL 结果
系统 SHALL 把模型请求的每个工具调用派发到本次运行装配出的工具注册表；注册表的内容由装配决定（见 `config-layering`），未注册的工具名 SHALL 产生一条 `tool/result` 且 `outcome` 为 `UNKNOWN_TOOL`，回合 MUST NOT 因此中断。

#### Scenario: UNKNOWN_TOOL 不打断回合
- **WHEN** Provider 返回一个调用未注册工具名的回复
- **THEN** 该调用有配对的 `tool/call` 与 `tool/result`，`outcome` 为 `UNKNOWN_TOOL`，且该回合正常写 `turn/end`

#### Scenario: 工具结果喂回下一回合
- **WHEN** 某回合产生了 `tool/result` 记录
- **THEN** 下一回合的装配里这些结果作为工具消息出现

#### Scenario: 空白名单下任何工具调用都是 UNKNOWN_TOOL
- **WHEN** 配置文件写 `tools = []`，Provider 仍返回一个工具调用
- **THEN** 该调用产出 `outcome: UNKNOWN_TOOL` 的 `tool/result`，且回合正常写 `turn/end`
