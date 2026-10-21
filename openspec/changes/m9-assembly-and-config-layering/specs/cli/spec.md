# Spec Delta

## MODIFIED Requirements

### Requirement: minihns run 一次性完成一个 session
`minihns run` SHALL 一次调用跑完一个 session；参数：`-p/--prompt`（必填、非空）、`--config`、`--workspace`（默认当前目录）、`--session-dir`、`--provider`（默认 `mock`）、`--fixture`、`--base-url`（默认 `https://api.deepseek.com`）、`--model`（默认 `deepseek-chat`）、`--api-key-env`（默认 `DEEPSEEK_API_KEY`）、`--max-turns`、`--window`（默认 128000）、`--reserve`（默认 8192）、`--append-system-prompt`、`--events jsonl`、`--sandbox`（默认 `workspace-write`）、`--yes`。`--provider mock` 时 `--fixture` MUST 同时给出，`openai` 时 MUST NOT 被使用。成功时 stdout 打印 session id。

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
- **WHEN** 工作区根有一份写满设置的 `mini.config.toml`，用 mock fixture 执行 `minihns run -p "任务" --provider mock --fixture <f> --yes`
- **THEN** 退出码为 0，且 `session/start` 的 payload 取自配置文件里的值而不是内置默认

### Requirement: run 参数记录进 session/start
系统 SHALL 在 `session/start` 的 payload 里记录本次运行的**有效参数**（层叠之后的结果）：`workspace`（绝对路径）、`provider`、`max_turns`、`window`、`reserve`、`append_system_prompt`、`sandbox`、`approval`（`ask` 或 `auto`）、`tools`（装配筛出来并送给模型的工具名列表），以及用户 prompt 原文；`provider` 为 `openai` 时还 SHALL 记录 `base_url`、`model` 与 `api_key_env`（**环境变量的名字**，不是它的值）。payload MUST NOT 记录密钥的值或任何 Authorization 内容。payload MUST NOT 重复携带 `schema_version`。

#### Scenario: payload 与命令行一致
- **WHEN** 执行 `minihns run -p "x" --max-turns 3 --workspace <dir> --sandbox read-only`
- **THEN** `session/start` 的 payload 里 `max_turns` 为 3、`workspace` 为 `<dir>` 的绝对路径、`sandbox` 为 `read-only`、`approval` 为 `ask`、`prompt` 为 `x`

#### Scenario: 工具名列表进 payload
- **WHEN** 执行一次 run
- **THEN** `session/start` 的 payload 里 `tools` 含 `read`、`write`、`edit`、`glob`、`grep` 五个名字

#### Scenario: 版本事实只在信封里
- **WHEN** 读取任一 session 日志的 `session/start` 记录
- **THEN** 该记录的信封 `schema_version` 为 1，且 payload 里没有 `schema_version` 键

#### Scenario: openai 的端点、模型与密钥变量名进 payload
- **WHEN** 执行 `minihns run -p "x" --provider openai --base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_KEY`，且 `MINIHNS_KEY` 已设
- **THEN** `session/start` 的 payload 里 `provider` 为 `openai`、`base_url` 为所给地址、`model` 为 `qwen3.8-flash-next-iq3_xxs`、`api_key_env` 为 `MINIHNS_KEY`，且整份日志里找不到 `MINIHNS_KEY` 的值

#### Scenario: 窗口与预留进 payload
- **WHEN** 执行 `minihns run -p "x" --window 4000 --reserve 500`
- **THEN** `session/start` 的 payload 里 `window` 为 4000、`reserve` 为 500

#### Scenario: 同一命令行在两份配置下 payload 不同
- **WHEN** 同一份命令行分别在「工作区根写着 `max_turns = 2` 与 `tools = ["read"]`」和「没有配置文件」两种情况下执行
- **THEN** 两份日志的 `session/start` payload 里 `max_turns` 分别为 2 与 8、`tools` 分别只含 `read` 与含全部六个内置工具名

## REMOVED Requirements

### Requirement: provider 选择与密钥来源
**Reason**: 这条里「该变量未设时系统 SHALL 照常发出请求（不带鉴权头），MUST NOT 以参数错误提前失败」被 M9 推翻——密钥缺失从「provider 侧的 401 失败结果」改成「session 开始之前的参数错误」。它的 scenario「密钥变量未设不提前失败」说的是现在反过来的事实，留着它会让主规格自相矛盾。
**Migration**: 取值集合（`mock` / `openai`）、密钥只从环境变量读、密钥 MUST NOT 进 argv / stdout / stderr / 日志 / payload 这三条原样搬进新增的「provider 选择与密钥是装配的必需项」；判据 `test_an_openai_run_without_an_api_key_*` 从「请求照发、退出码不是 2」改成「退出码 2、没有日志、没有请求」。

## ADDED Requirements

### Requirement: provider 选择与密钥是装配的必需项
系统 SHALL 只接受 `mock` 与 `openai` 两个 provider 取值，其它取值 SHALL 以退出码 2 结束、stderr 含 `UNKNOWN_PROVIDER`，且 MUST NOT 创建 session 日志。`provider` 为 `openai` 时密钥 SHALL 只从 `api_key_env` 指定的环境变量读取（默认 `DEEPSEEK_API_KEY`）；该变量未设或为空时系统 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与该变量名，且 MUST NOT 创建 session 日志、MUST NOT 发出任何 HTTP 请求。密钥 MUST NOT 出现在命令行参数、stdout、stderr、session 日志或 `session/start` 的 payload 里。

#### Scenario: 未知 provider
- **WHEN** 执行 `minihns run -p "x" --provider claude`
- **THEN** 退出码为 2，stderr 含 `UNKNOWN_PROVIDER`，且没有 session 日志

#### Scenario: 密钥变量未设是参数错误
- **WHEN** `--api-key-env` 指向的环境变量未设，执行 `--provider openai` 的 run
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与该变量名，没有 session 日志，也没有发出请求

#### Scenario: 密钥只进请求头
- **WHEN** `--api-key-env` 指向的变量已设，一次 openai run 跑完
- **THEN** 请求带上了该密钥，而 stdout、stderr 与该 session 的日志里都不含它

### Requirement: 配置层失败都在 session 开始之前
配置文件非法、`--config` 指向的路径不存在、工具白名单里的未知名、以及 openai 路径缺失密钥时，系统 SHALL 以退出码 2 结束、往 stderr 写 `INVALID_ARGUMENT`，且 MUST NOT 创建 session 日志、MUST NOT 追加任何事件。这一类失败与既有的参数错误同形，是「每个非零退出都有 `error/*`」的例外之一。

#### Scenario: 配置层失败没有日志
- **WHEN** 上述任一配置层失败发生
- **THEN** 退出码为 2、stderr 含 `INVALID_ARGUMENT`，且 session 目录里没有任何新文件
