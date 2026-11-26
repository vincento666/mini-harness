# Spec Delta: cli

## MODIFIED Requirements

### Requirement: minihns run 一次性完成一个 session

`minihns run` SHALL 一次调用跑完一个 session；参数：`-p/--prompt`（必填、非空）、`--config`、`--workspace`（默认无——未给时会话工作区是会话专属目录，见「默认工作区是会话专属目录」）、`--session-dir`、`--provider`（默认 `mock`）、`--fixture`、`--base-url`（默认 `https://api.deepseek.com`）、`--model`（默认 `deepseek-chat`）、`--api-key-env`（默认 `DEEPSEEK_API_KEY`）、`--max-steps`、`--window`（默认 128000）、`--reserve`（默认 8192）、`--append-system-prompt`、`--events jsonl`、`--sandbox`（默认 `workspace-write`）、`--yes`。`--provider mock` 时 `--fixture` MUST 同时给出，`openai` 时 MUST NOT 被使用。成功时 stdout 打印 session id；会话工作区的绝对路径 SHALL 写 stderr，MUST NOT 写 stdout。

#### Scenario: 缺少 prompt

- **WHEN** 执行 `minihns run` 且不带 `-p`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 空 prompt

- **WHEN** 执行 `minihns run -p ""`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`

#### Scenario: mock 缺 fixture

- **WHEN** 执行 `minihns run -p "任务" --provider mock` 且不带 `--fixture`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 成功 run 打印 session id

- **WHEN** 用合法 fixture 执行 `minihns run -p "任务" --provider mock --fixture <f> --yes`
- **THEN** 退出码为 0，stdout 含该 session id，且 `sessions/<session-id>.jsonl` 存在

#### Scenario: openai 带 fixture 是参数错误

- **WHEN** 执行 `minihns run -p "任务" --provider openai --fixture <f>`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 配置文件里的设置生效于一次 run

- **WHEN** 发现根有一份写满设置的 `mini.config.toml`，用 mock fixture 执行 `minihns run -p "任务" --provider mock --fixture <f> --yes`
- **THEN** 退出码为 0，且 `session/start` 的 payload 取自配置文件里的值而不是内置默认

#### Scenario: 未给 --workspace 时工作区路径在 stderr

- **WHEN** 在临时目录执行一次成功的 run，不传 `--workspace`
- **THEN** stderr 含该会话工作区的绝对路径（`$MINIHNS_HOME/workspaces/<session_id>` 形态），stdout 不含它

### Requirement: run 参数记录进 session/start

系统 SHALL 在 `session/start` 的 payload 里记录本次运行的**有效参数**（层叠之后的结果）：`entry`（`run`、`chat`、`serve`、`host` 或 `subagent`）、`workspace`（绝对路径，记录的是**会话工作区**——围栏根，不因默认值变化而记录启动目录）、`provider`、`max_steps`、`window`、`reserve`、`compaction_threshold_ratio`、`compaction_headroom_tokens`、`compaction_retain_ratio`、`compaction_retain_tokens`、`append_system_prompt`、`goal_policy`（内置 goal 政策段的版本，当前为 `"v2"`）、`sandbox`、`approval`（`ask` 或 `auto`）、`tools`（装配筛出来并送给模型的工具名列表），以及用户 prompt 原文——`entry` 为 `chat` 或 `host` 时 prompt MUST 是空串，人话住在 `user/message` 里。payload MUST NOT 重复携带 `schema_version`。

`goal_policy` MUST NOT 来自配置或 flag：它由内置常量决定，调用方不能关掉或改写政策段。

#### Scenario: payload 与命令行一致

- **WHEN** 执行 `minihns run -p "x" --max-steps 3 --workspace <dir> --sandbox read-only`
- **THEN** `session/start` 的 payload 里 `entry` 为 `run`、`max_steps` 为 3、`workspace` 为 `<dir>` 的绝对路径、`sandbox` 为 `read-only`、`approval` 为 `ask`、`prompt` 为 `x`、`goal_policy` 为 `"v2"`

#### Scenario: 默认模式下 workspace 记会话目录

- **WHEN** 不传 `--workspace` 执行一次 run
- **THEN** `session/start` 的 payload 里 `workspace` 是 `$MINIHNS_HOME/workspaces/<session_id>` 的绝对路径，不是启动目录

#### Scenario: 政策版本不可由调用方覆盖

- **WHEN** 配置文件写 `goal_policy = "off"` 或命令行尝试给同名 flag
- **THEN** 配置键不存在（按未知键拒绝或忽略的既有规则）；`session/start.goal_policy` 仍是 `"v2"`

## ADDED Requirements

### Requirement: 默认工作区是会话专属目录

未显式给出 `--workspace` 时，系统 SHALL 把会话工作区解析为 `$MINIHNS_HOME/workspaces/<session_id>/`（`MINIHNS_HOME` 未设时为 `~/.mini-harness`），并在装配期创建（含缺失的父目录）。创建失败 SHALL 以 `INVALID_ARGUMENT`（退出码 2）失败，不发任何请求、不建日志。`session_id` SHALL 在工作区解析之前生成。显式 `--workspace` 的解析 MUST NOT 因本条改变。

会话工作区是**围栏根**：file/bash/subagent/present 等一切改动边界与 bash 的工作目录都锚它。发现根（`mini.config.toml`、skills 项目两级根、`AGENTS.md` 项目契约）SHALL 锚**启动目录**——显式 `--workspace` 时为该目录，否则为当前目录——MUST NOT 锚默认的会话工作区。

#### Scenario: 默认模式下产物落会话目录

- **WHEN** 在项目目录启动一次会话（不传 `--workspace`），模型在工作区内 `write snake/core.py`
- **THEN** 文件出现在 `$MINIHNS_HOME/workspaces/<session_id>/snake/core.py`，启动目录与项目仓库根没有任何新文件

#### Scenario: 显式 --workspace 逐点同旧

- **WHEN** 执行 `--workspace <dir>` 的会话，模型在工作区内写文件
- **THEN** 文件出现在 `<dir>` 下，与加默认隔离之前完全一致

#### Scenario: 工作区创建失败当场失败

- **WHEN** `$MINIHNS_HOME` 指向一个只读路径，执行一次 run
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 发现根仍锚启动目录

- **WHEN** 启动目录放着 `mini.config.toml`、`AGENTS.md` 与 `.minihns/skills/<n>/SKILL.md`，不传 `--workspace` 启动会话
- **THEN** 配置、项目契约与项目技能照常生效，就像显式把 `--workspace` 指到启动目录一样
