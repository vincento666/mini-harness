# Spec Delta

## MODIFIED Requirements

### Requirement: 五个文件工具注册进工具表
系统 SHALL 内置 `read`、`write`、`edit`、`glob`、`grep` 五个文件工具定义，并把进入本次工具表的那些工具的名字与描述送进每次模型调用。它们是否进入本次工具表由装配决定（见 `config-layering`）；未注册的工具名 SHALL 仍产出 `outcome: UNKNOWN_TOOL` 的 `tool/result`。

#### Scenario: 注册表非空
- **WHEN** 一次没有配置文件的 run 写出 `session/start`
- **THEN** 其 payload 的 `tools` 含上述五个名字（同一份工具表里还有 `bash`，它由 `bash-tool` 规定）

#### Scenario: 未注册的名字仍是 UNKNOWN_TOOL
- **WHEN** 模型调用一个不在本次工具表里的工具名
- **THEN** 该调用产出 `outcome: UNKNOWN_TOOL` 的 `tool/result`，且回合继续

#### Scenario: 被白名单筛掉的文件工具不在工具表里
- **WHEN** 配置文件写 `tools = ["read"]`，模型调用 `grep`
- **THEN** 该调用产出 `outcome: UNKNOWN_TOOL` 的 `tool/result`，且回合继续
