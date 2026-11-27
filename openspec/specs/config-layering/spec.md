# config-layering Specification

## Purpose

定义一次运行的设置从哪儿来：配置文件的发现顺序、可承载的字段、非法形状的结果形状、三层取值的优先级、工具白名单的筛选，以及必需项缺失时在 session 开始之前当场失败。
## Requirements
### Requirement: 配置文件的发现顺序

系统 SHALL 按固定顺序找配置文件：`--config <path>` 显式指定的路径优先；未给 `--config` 时 SHALL 找**发现根**里的 `mini.config.toml`——发现根是显式 `--workspace` 解析后的目录，未给 `--workspace` 时是当前目录（启动目录）；两处都没有时 SHALL 只用内置默认。发现根 MUST NOT 锚默认的会话专属工作区：未给 `--workspace` 时，默认工作区落在 `$MINIHNS_HOME/workspaces/<session_id>/`，配置文件不从那里找，也不因会话目录里恰好有一份同名文件而生效。

#### Scenario: 显式指定的配置文件生效

- **WHEN** 执行 `minihns run -p "x" --config <dir>/other.toml`，且发现根也有一份 `mini.config.toml`
- **THEN** 生效的是 `other.toml`，发现根那份被忽略

#### Scenario: 没有 --config 时读发现根

- **WHEN** 发现根存在 `mini.config.toml` 且未给 `--config`
- **THEN** 该文件里的设置生效

#### Scenario: 未给 --workspace 时发现根是启动目录

- **WHEN** 启动目录放着 `mini.config.toml`，不传 `--workspace` 执行一次 run
- **THEN** 该配置生效；`$MINIHNS_HOME/workspaces/<session_id>/` 里就算有一份 `mini.config.toml` 也不被读取

#### Scenario: 两处都没有时是内置默认

- **WHEN** 发现根没有 `mini.config.toml` 且未给 `--config`
- **THEN** 全部设置取内置默认，`session/start` 的 payload 与 M8 之前的形状一致

#### Scenario: 显式指定的文件不存在是参数错误

- **WHEN** `--config` 指向的路径不存在
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与所查找的路径，且没有创建 session 日志

### Requirement: 取值优先级是内置默认、配置文件、CLI flag
系统 SHALL 按「内置默认 < 配置文件 < CLI flag」派生每一项设置：配置文件里的值覆盖内置默认，命令行显式给出的值覆盖配置文件。判断「命令行显式给出」以该开关是否出现为准，MUST NOT 用「值恰好等于默认」来判断。`provider` 的内置默认由环境决定：CLI 与配置文件都没给 `provider` 时，`MINIHNS_API_KEY` 已设且非空则默认 `openai`，否则默认 `mock`。

#### Scenario: 配置文件覆盖内置默认
- **WHEN** 配置文件写 `max_steps = 3`，命令行未给 `--max-steps`
- **THEN** 本次运行的 `max_steps` 为 3

#### Scenario: 命令行覆盖配置文件
- **WHEN** 配置文件写 `max_steps = 3`，命令行给 `--max-steps 5`
- **THEN** 本次运行的 `max_steps` 为 5

#### Scenario: 与默认同值的命令行开关仍是显式值
- **WHEN** 配置文件写 `max_steps = 8`，命令行给 `--max-steps 8`（内置默认也是 8）
- **THEN** 本次运行的 `max_steps` 为 8，且它取自命令行这一层

#### Scenario: 有密钥时裸跑的默认 provider 是 openai
- **WHEN** `MINIHNS_API_KEY` 已设且非空，配置文件与命令行都没给 `provider`
- **THEN** 生效 provider 为 `openai`，且 `api_key_env` 默认为 `MINIHNS_API_KEY`

#### Scenario: 没有密钥时裸跑的默认 provider 仍是 mock
- **WHEN** `MINIHNS_API_KEY` 未设，配置文件与命令行都没给 `provider`
- **THEN** 生效 provider 为 `mock`，未给 `--fixture` 时以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与 `--fixture`

### Requirement: 配置文件只承载设置类字段

配置文件 SHALL 只接受这些键：`provider`、`base_url`、`model`、`api_key_env`、`max_steps`、`window`、`reserve`、`compaction_threshold_ratio`、`compaction_headroom_tokens`、`compaction_retain_ratio`、`compaction_retain_tokens`、`append_system_prompt`、`sandbox`、`approval`、`tools`、`session_dir`、`workspace`。`prompt` 与 `fixture` MUST NOT 出现在配置文件里；密钥的值 MUST NOT 出现在配置文件里（只有环境变量**名字**可配）。压缩参数的类型按数字校验：ratio 接受 float，tokens 接受 int；`bool` MUST NOT 被当成数字。

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

### Requirement: 非法配置文件是参数错误且不产生日志
配置文件不是合法 TOML、或某个键的值类型不对时，系统 SHALL 以退出码 2 结束、往 stderr 写 `INVALID_ARGUMENT` 与出错位置（键名或 TOML 的行与列），且 MUST NOT 创建 session 日志。

#### Scenario: 语法错误
- **WHEN** 配置文件内容是 `max_steps = = 3`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 类型不对
- **WHEN** 配置文件写 `max_steps = "three"`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与键名 `max_steps`，且没有创建 session 日志

### Requirement: 工具表由内置定义与配置白名单筛出
系统 SHALL 内置 `read`、`write`、`edit`、`glob`、`grep`、`bash` 六个工具定义；本次运行的工具表 SHALL 由配置文件里的 `tools` 白名单对这六个定义筛选得出：未给 `tools` 时六个全部进入，给了则只保留列出的那些。`tools` 里的名字不在六个之内时 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与那个名字，且 MUST NOT 创建 session 日志。`tools = []` SHALL 合法，此时模型没有工具可用。

#### Scenario: 白名单只留两个工具
- **WHEN** 配置文件写 `tools = ["read", "grep"]`
- **THEN** `session/start` 的 payload 里 `tools` 恰含这两个名字，且模型收到的工具面也只有这两个

#### Scenario: 白名单里的未知名是参数错误
- **WHEN** 配置文件写 `tools = ["read", "web_search"]`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `web_search`，且没有创建 session 日志

#### Scenario: 空白名单合法
- **WHEN** 配置文件写 `tools = []`
- **THEN** run 正常跑完，`session/start` 的 payload 里 `tools` 是空列表

#### Scenario: 未配置工具表时六个内置定义全进
- **WHEN** 配置文件没有 `tools` 键
- **THEN** `session/start` 的 payload 里 `tools` 恰含上述六个名字

### Requirement: 端点必需项缺失当场失败
生效 provider 为 `openai` 或 `deepseek` 时，端点三项先由预设表补齐没被给的那几项（见「provider 预设表填的是没被给的那几项」）。补齐后仍缺 `model` 时系统 SHALL 以退出码 2 结束、往 stderr 写 `INVALID_ARGUMENT` 并指出 `--model`。`api_key_env` 指向的环境变量 SHALL 已设且非空；否则系统 SHALL 以退出码 2 结束、往 stderr 写 `INVALID_ARGUMENT` 并指出该变量名，且 MUST NOT 创建 session 日志、MUST NOT 发出任何 HTTP 请求。这一条对取自配置文件与取自命令行的设置同样成立。

#### Scenario: 密钥变量未设
- **WHEN** `--provider openai` 且 `--api-key-env` 指向的变量未设
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与该变量名，且没有创建 session 日志

#### Scenario: 密钥变量设为空串
- **WHEN** `--provider openai` 且该变量被设为空字符串
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: 配置文件指定的 provider 同样判
- **WHEN** 配置文件写 `provider = "openai"`，命令行未给 `--provider`，且 `api_key_env` 指向的变量未设
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT`，且没有创建 session 日志

#### Scenario: openai 预设缺 model 当场失败
- **WHEN** `--provider openai --api-key-env MINIHNS_API_KEY`（该变量已设）且未给 `--model`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `--model`，没有创建 session 日志，也没有发出请求

### Requirement: provider 预设表填的是没被给的那几项

系统 SHALL 内置一张按 provider 名索引的端点预设表：`openai` = `base_url https://api.openai.com/v1`、`api_key_env MINIHNS_API_KEY`、`model` **无默认**；`deepseek` = `https://api.deepseek.com` / `deepseek-chat` / `DEEPSEEK_API_KEY`；`openrouter` = `https://openrouter.ai/api/v1` / `qwen/qwen3.8-27b` / `OPENROUTER_API_KEY`；`mock` 没有端点三项。预设 SHALL 只填 CLI 与配置文件都没给的那几项，MUST NOT 覆盖已给出的那一项。表里 MUST NOT 出现任何密钥的值，只有变量名。

#### Scenario: 预设不覆盖命令行给过的那一项
- **WHEN** 执行 `--provider openai --base-url http://127.0.0.1:8300/v1 --model q --api-key-env TEST_KEY_ENV`
- **THEN** 生效的端点三项就是给进去的这三项，预设一项都没用上

#### Scenario: 配置文件写 provider 时预设同样生效
- **WHEN** 配置文件写 `provider = "deepseek"`，未写 `base_url`、`model`、`api_key_env`
- **THEN** 端点三项取 `deepseek` 预设，`session/start` 的 payload 里 `base_url` 为 `https://api.deepseek.com`

#### Scenario: openai 预设不落到 deepseek 的默认
- **WHEN** `--provider openai` 且未给 `--base-url`
- **THEN** 生效的 `base_url` 是 `https://api.openai.com/v1`，不是 `https://api.deepseek.com`

#### Scenario: 配置文件只写一行 provider 就够
- **WHEN** 配置文件只写 `provider = "openrouter"`，三项端点都没写
- **THEN** 生效的 `base_url`、`model`、`api_key_env` 全取 `openrouter` 预设（`https://openrouter.ai/api/v1` / `qwen/qwen3.8-27b` / `OPENROUTER_API_KEY`）

#### Scenario: mock 预设没有端点三项
- **WHEN** 生效 provider 为 `mock`
- **THEN** `session/start` 的 payload 里没有 `base_url`、`model`、`api_key_env` 三格，与既有形状一致

### Requirement: 子代理 preset 配置

配置文件 SHALL 接受 `[subagent]` 段：`preset`（默认 preset id，字符串）、`allowed_presets`（非空字符串数组，模型可选的白名单）、`[subagent.presets.<id>].tools`（工具名数组）、可选的 `[subagent.presets.<id>].persona`（字符串）与可选的 `[subagent.presets.<id>.skills]`（表：`kind` 只接受 `filesystem`，`dirs` 是必填的字符串数组）。`<id>` SHALL 非空且不重复。

下列情形 SHALL 以退出码 2 结束、stderr 含 `INVALID_ARGUMENT` 与出问题的键，且 MUST NOT 创建 session 日志：`[subagent]` 段里的未知键；`preset` 指向的 id 不在 `[subagent.presets]` 里；`preset` 不在 `allowed_presets` 里（两者都配时）；`allowed_presets` 里有不在 `[subagent.presets]` 里的 id；preset 的 `tools` 里有内置工具之外的名字；`persona` 不是字符串；`skills` 不是表、`kind` 不是 `filesystem`、`dirs` 不是字符串数组；preset id 为空或重复。没有 `[subagent]` 段 SHALL 合法。`dirs` 里的目录不存在 SHALL NOT 是配置错误。

`skill_dirs` 已删除：出现在 preset 里 SHALL 按未知键处理（退出码 2）。

#### Scenario: skills 表是合法配置

- **WHEN** 配置 `[subagent.presets.reader.skills] kind = "filesystem"`、`dirs = ["sk"]`
- **THEN** 配置通过

#### Scenario: 未知 kind 是参数错误

- **WHEN** `kind = "remote"`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `kind`

#### Scenario: dirs 类型错误

- **WHEN** `dirs = "sk"`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `dirs`

#### Scenario: skill_dirs 已删除

- **WHEN** preset 里写 `skill_dirs = ["sk"]`
- **THEN** 退出码为 2，stderr 含 `INVALID_ARGUMENT` 与 `skill_dirs`

#### Scenario: 目录不存在不是配置错误

- **WHEN** `dirs = ["/nope"]`
- **THEN** 配置通过；子会话启动时该层为空

### Requirement: `[goal]` 段承载轮次、停滞与并行策略

`mini.config.toml` SHALL 支持 `[goal]` 段，含四个键：

- `max_rounds`：正整数，缺省 `32`；`create_goal` 未给 `max_rounds` 时用它；
- `blocked_after_consecutive_rounds`：正整数，缺省 `3`，且 MUST 不大于 `max_rounds`——否则阻塞门槛永远够不到，配置层直接拒；
- `allow_parallel_in_progress`：布尔，缺省 `true`；
- `stall_rounds`：非负整数，缺省 `2`。正整数表示「连续 N 个 goal 轮次零工具调用就停自动推进」；`0` 表示关闭闸门（完全对齐 DSH：完成只由模型声明）。

非法取值（非正整数、非布尔、零、负数、非整数）MUST 在会话开始之前以参数错误失败，MUST NOT 产生日志。取值优先级与其它设置类字段一致：CLI flag > 配置文件 > 内置默认。

#### Scenario: 缺省值生效

- **WHEN** 配置文件没有 `[goal]` 段，模型调用 `create_goal` 且未给轮次上限
- **THEN** 快照的 `max_rounds == 32`

#### Scenario: 非法值当场失败

- **WHEN** 配置文件写 `max_rounds = 0`
- **THEN** 命令以参数错误退出，`sessions/` 下不新增日志

#### Scenario: 并行关闭生效

- **WHEN** 配置文件写 `allow_parallel_in_progress = false`，一次 `todo` 调用标两个 `in_progress`
- **THEN** 结果是 `TODO_PARALLEL_DISABLED`

#### Scenario: 默认阈值为 2

- **WHEN** 配置文件没有 `stall_rounds`，连续两个 goal 轮次零工具调用
- **THEN** 第二轮之后不再开新轮、武装位解除，目标 `phase` 仍为 `active`

#### Scenario: 配成 0 关闭闸门

- **WHEN** 配置文件写 `stall_rounds = 0`，goal 轮次连续空转
- **THEN** 驱动一路开到 `max_rounds`；日志里 `turn/end.tool_calls == 0` 只作审计

### Requirement: max_steps 是步数上限的唯一键

`mini.config.toml` 的会话段 SHALL 用 `max_steps` 表示一轮的步数上限。旧键 `max_turns` MUST NOT 被接受：它是一条未知键（`CONFIG_UNKNOWN_KEY`），会话开始之前失败，且不建日志。

#### Scenario: 旧键被拒

- **WHEN** 配置文件只写 `max_turns = 4`
- **THEN** 会话开始之前失败，退出码 2，不建日志

### Requirement: proxy 是端点出口的可配键

`mini.config.toml` SHALL 接受顶层键 `proxy`（字符串），取值优先级与其它可配字段一致：命令行 `--proxy` > 配置文件 `proxy` > 没有（直连）。值 MUST 是 `http://` 或 `https://` 的绝对 URL；类型不对按 `CONFIG_INVALID_VALUE` 拒，形状不对在装配期以 `INVALID_ARGUMENT` 拒。`proxy` MUST NOT 写进 `session/start` 的配置快照。

#### Scenario: 配置文件给 proxy

- **WHEN** 配置文件写 `proxy = "http://127.0.0.1:7897"` 且命令行不给 `--proxy`
- **THEN** 该会话的请求经这个代理发出

#### Scenario: 命令行覆盖配置文件

- **WHEN** 配置文件写 `proxy = "http://127.0.0.1:7897"`，命令行给 `--proxy http://127.0.0.1:8888`
- **THEN** 请求经 `8888` 发出

#### Scenario: 类型不对是配置错误

- **WHEN** 配置文件写 `proxy = 7897`
- **THEN** 会话开始之前失败，`CONFIG_INVALID_VALUE`，退出码 2

