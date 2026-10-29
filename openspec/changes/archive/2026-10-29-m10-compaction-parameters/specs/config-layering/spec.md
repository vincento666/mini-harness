# Spec Delta

## MODIFIED Requirements

### Requirement: 配置文件只承载设置类字段

配置文件 SHALL 只接受这些键：`provider`、`base_url`、`model`、`api_key_env`、`max_turns`、`window`、`reserve`、`compaction_threshold_ratio`、`compaction_headroom_tokens`、`compaction_retain_ratio`、`compaction_retain_tokens`、`append_system_prompt`、`sandbox`、`approval`、`tools`、`session_dir`、`workspace`。`prompt` 与 `fixture` MUST NOT 出现在配置文件里；密钥的值 MUST NOT 出现在配置文件里（只有环境变量**名字**可配）。压缩参数的类型按数字校验：ratio 接受 float，tokens 接受 int；`bool` MUST NOT 被当成数字。

#### Scenario: prompt 进配置文件是参数错误
- **WHEN** 配置文件里有 `prompt = "任务"`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 并指出该键，且没有创建 session 日志

#### Scenario: 密钥值进配置文件是参数错误
- **WHEN** 配置文件里有 `api_key = "sk-..."`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 空配置文件等价于没有配置文件
- **WHEN** 配置文件存在但没有任何键
- **THEN** 全部设置取内置默认，run 正常跑完

#### Scenario: 压缩参数可以写进配置文件
- **WHEN** 配置文件写 `compaction_retain_ratio = 0.10`、`compaction_headroom_tokens = 0`
- **THEN** session 正常开始，`session/start` 的 payload 里这两个值分别是 0.10 与 0

#### Scenario: compaction 参数类型不对是参数错误
- **WHEN** 配置文件写 `compaction_retain_tokens = true`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志
