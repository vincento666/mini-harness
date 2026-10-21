# Proposal

## Why

「这次运行用什么」目前只能由 argv 表达：工具表硬编码在 `cli/main.py`（五个文件工具加 `bash`），`base_url` / `model` / `api_key_env` 三条 `str | None` 一路结伴，「是不是 openai」这个判断散在四处（ADR-0002 第 14、15 条）。M6 的 REPL 与 M7 的事件流都要复用同一个内核入口——先立装配与配置层，外壳才不会各自再造一遍 provider 选择与工具注册。

## What Changes

- 新增配置文件 `mini.config.toml`：发现顺序 `--config <path>` > 工作区根 `mini.config.toml` > 内置默认；层叠优先级 **内置默认 < 配置文件 < CLI flag**（roadmap 已定）。
- 配置文件可配设置类字段：`provider`、`base_url`、`model`、`api_key_env`、`max_turns`、`window`、`reserve`、`append_system_prompt`、`sandbox`、`approval`、`tools`、`session_dir`、`workspace`。`prompt` 与 `fixture` MUST NOT 出现在配置里。
- **工具表从装配来**：六个内置工具定义照旧，配置里的 `tools` 是白名单筛选；未知名是参数错误，空列表合法（模型没有工具可用）。`cli/main.py` 里那行硬编码被替掉。
- **BREAKING** `--provider openai` 且 `--api-key-env` 指向的环境变量未设或为空：现在请求照发、401 塌成 `PROVIDER_HTTP_STATUS`、退出码 1 且日志已建；改为**当场失败**——退出码 2、stderr 含 `INVALID_ARGUMENT`、**不创建 session 日志**。
- 配置文件非法（不是合法 TOML、未知键、类型不对、`prompt` / `fixture` 出现）同样是退出码 2 且不建日志。
- 立 `ProviderEndpoint`：那三条收成一个可选端点对象，`session/start` 的 payload 由它派生，「是不是 openai」四处塌成一处（「端点在不在」）。payload 的字段表不变。
- 本里程碑明确不做：多份配置文件的合并与 profile、`MINIHNS_*` 环境变量层、配置热重载、`--config` 指向目录、用户级 `~/.mini-harness/config.toml`、第二个真实 provider、把工具定义本身（描述 / 入参模型 / 执行入口）搬进配置、把密钥写进配置文件、`session/start` 记录配置来源。

## Capabilities

### New Capabilities
- `config-layering`: 一次运行的设置从哪儿来——配置文件的发现顺序、字段表与非法形状、三层取值优先级、工具白名单筛选、必需项缺失当场失败（不建日志）。

### Modified Capabilities
- `cli`: run 参数表加 `--config`；「provider 选择与密钥来源」里「密钥变量未设不提前失败」被推翻，改成缺失即参数错误；payload 的 `tools` 来源从「本次注册」改成「装配筛出来的那一份」；退出码 2 那一类明确「没有日志文件」。
- `file-tools`: 「五个文件工具注册进工具表」改成「五个内置定义，是否进表由装配决定」；「注册表 MUST NOT 为空」这条撤掉（空白名单合法）。
- `turn-loop`: `UNKNOWN_TOOL` 那条里「注册表里内置五个文件工具」的措辞改成「注册表由装配给出」。

## Impact

代码：`cli/main.py`（参数表、装配段、密钥判据）、新模块 `config/`（读 TOML、层叠、白名单）、`loop/settings.py`（立 `ProviderEndpoint`）、`loop/turn_loop.py`（payload 由端点对象派生、去掉那处 `provider_name == "openai"`）、`tools/`（注册表由装配构造）。测试落在 seam ②（工具注册）与 seam ⑥（CLI 黑盒），不新增缝（ADR-0010）。依赖：标准库 `tomllib`，无新依赖。文档：`docs/adr/` 新增一份（配置层叠与「密钥缺失当场失败」这两处简化的代价）、ADR-0002 第 14、15 条改判为已处理。
