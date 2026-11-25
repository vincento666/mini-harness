# Spec Delta: cli

## MODIFIED Requirements

### Requirement: run 参数记录进 session/start

系统 SHALL 在 `session/start` 的 payload 里记录本次运行的**有效参数**（层叠之后的结果）：`entry`（`run`、`chat`、`serve`、`host` 或 `subagent`）、`workspace`（绝对路径）、`provider`、`max_steps`、`window`、`reserve`、`compaction_threshold_ratio`、`compaction_headroom_tokens`、`compaction_retain_ratio`、`compaction_retain_tokens`、`append_system_prompt`、`goal_policy`（内置 goal 政策段的版本，当前为 `"v1"`）、`sandbox`、`approval`（`ask` 或 `auto`）、`tools`（装配筛出来并送给模型的工具名列表），以及用户 prompt 原文——`entry` 为 `chat` 或 `host` 时 prompt MUST 是空串，人话住在 `user/message` 里。payload MUST NOT 重复携带 `schema_version`。

`goal_policy` MUST NOT 来自配置或 flag：它由内置常量决定，调用方不能关掉或改写政策段。

#### Scenario: payload 与命令行一致

- **WHEN** 执行 `minihns run -p "x" --max-steps 3 --workspace <dir> --sandbox read-only`
- **THEN** `session/start` 的 payload 里 `entry` 为 `run`、`max_steps` 为 3、`workspace` 为 `<dir>` 的绝对路径、`sandbox` 为 `read-only`、`approval` 为 `ask`、`prompt` 为 `x`、`goal_policy` 为 `"v1"`

#### Scenario: 政策版本不可由调用方覆盖

- **WHEN** 配置文件写 `goal_policy = "off"` 或命令行尝试给同名 flag
- **THEN** 配置键不存在（按未知键拒绝或忽略的既有规则）；`session/start.goal_policy` 仍是 `"v1"`
