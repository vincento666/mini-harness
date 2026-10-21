# Design

## Context

见 proposal.md - Why。设计要用的现状事实：工具表硬编码在 `cli/main.py:144`（`ToolRegistry([*file_tool_definitions(), *bash_tool_definitions()])`）；「是不是 openai」四处（`cli/main.py:164`、`:178`、`:211`、`loop/turn_loop.py:578`）；`base_url` / `model` / `api_key_env` 三条 `str | None` 从 CLI 一路进 `SessionSettings` 再进适配器；密钥缺失现在的形状是 `os.environ.get(...)` 得 `None` → 请求照发 → 401 → `PROVIDER_HTTP_STATUS` → 退出码 1、日志已建（判据 `tests/test_cli_provider.py::test_an_unset_key_env_still_sends_the_request`）。

约束：不变量 A（日志只追加）、B（失败也是结果）、C（五步显式）、F（可观测）；测试缝不新增，组合层在 ② 与 ⑥ 判（ADR-0010）。

## Goals / Non-Goals

**Goals**：一次运行的全部设置由一个装配点产出；配置层的一切失败都发生在 `EventLog.start` 之前；内核入口（`run_session(prompt, provider, settings, log, registry, ...)`）的形状不变，让 M6 / M7 能复用同一个入口。

**Non-Goals（设计级）**：不引入配置 profile、环境变量层、热重载；不改 `Provider` 契约与 `generate` 签名；不改 `session/start.payload` 的字段表（只改它的取值来源）；不改围栏判定顺序；不让配置文件携带可执行内容。

## Decisions

**D1 装配点是一个新模块 `config/`，不是 CLI 里的一串 if。** `load_config(path) -> dict[str, Any] | ConfigFailure`、`layer_settings(args, config) -> SessionSettings | ConfigFailure`、`build_registry(names) -> ToolRegistry | ConfigFailure` 三个入口，CLI 只在 `EventLog.start` 之前调用它们并把 `ConfigFailure` 映射成 `INVALID_ARGUMENT` + 退出码 2。备选：把层叠写进 `cli/main.py`（否：M6 的 REPL 与 M7 的 serve 会各自复制一遍，正是本里程碑要消除的东西）。

**D2 「命令行显式给出」用 `default=None` 哨兵判断。** argparse 的每个可层叠开关默认值改成 `None`，内置默认只住在 `loop/settings.py`；层叠顺序 内置默认 ← 配置文件 ← 显式 flag。备选：`default=DEFAULT_WINDOW` 这类真实默认（否：「显式给了与默认相同的值」与「没给」不可区分，而 `config-layering` 的 scenario「与默认同值的命令行开关仍是显式值」判的正是这件事）。代价：`--sandbox` 的合法取值仍由 argparse `choices` 判，非法取值仍是 `INVALID_ARGUMENT` + 2，这条形状不变。

**D3 配置文件用标准库 `tomllib`，非法形状是结果不是异常。** 语法错、未知键、类型不对、出现 `prompt` / `fixture` / `api_key` 都返回 `ConfigFailure(code, detail)`，detail 带键名或 TOML 的行列。备选：让 `tomllib.TOMLDecodeError` 冒到 CLI（否：不变量 B 的读法是失败也是结果；且异常里没有我们要的「哪个键」这条事实）。

**D4 工具表 = 六个内置定义 ∩ 配置白名单。** `build_registry(names: Sequence[str] | None)` 按固定顺序 `read, write, edit, glob, grep, bash` 产出注册表；`None` 是全部，`[]` 是空注册表。`cli/main.py` 不再 import `file_tool_definitions` / `bash_tool_definitions`。备选：配置里给完整工具定义（否：入参模型与执行入口没法从 TOML 来，只能内置定义 + 覆盖描述，形状变拧）。payload 里 `tools` 的顺序因此可预测，replay 的头部工具块仍从 payload 派生（`context-projection` 那条不变）。

**D5 立 `ProviderEndpoint`，「是不是 openai」塌成「端点在不在」。** `loop/settings.py` 加 frozen dataclass `ProviderEndpoint(base_url, model, api_key_env)`；`SessionSettings` 带 `endpoint: ProviderEndpoint | None`；`turn_loop` 的 payload 由它派生（`if settings.endpoint is not None:`），`provider_name == "openai"` 那处删除；CLI 里三处判断塌成装配处一处。payload 字段表不变（仍平铺 `base_url` / `model` / `api_key_env`）。备选：payload 里改成嵌套的 `endpoint` 对象（否：payload 字段表是规格事实，M9 不动它——ADR-0002 第 14 条原本就写着「立端点类型会让 payload 多一层嵌套」，这一版把嵌套留在内存里、不落到日志）。收 ADR-0002 第 14、15 条。

**D6 密钥判据前移到装配，provider 层不判。** 装配阶段读 `os.environ`，未设或空串 → `ConfigFailure("MISSING_API_KEY", "<变量名> 未设或为空")`。`OpenAICompatProvider(api_key: str | None)` 的签名保留、仍可发无鉴权请求（seam ⑤ 的判据 `test_the_authorization_header_is_present_only_when_a_key_is_given` 不动）。备选：provider 层自己拒（否：那是 seam ⑤ 的行为改变，而规格改的是 CLI 外部行为）。

**D7 配置文件发现用的 workspace 不来自配置文件。** 存在循环：配置文件位置取决于 workspace，而 `workspace` 本身可配。裁决：发现阶段只用「`--workspace` 或内置默认（当前目录）」；配置文件里的 `workspace` / `session_dir` 只影响围栏工作区与日志位置，MUST NOT 反过来影响配置文件发现。配置文件里的相对路径按当前工作目录解析。备选：两轮发现（先读配置再重找配置）——否：两份配置文件可能互相指，终止性要额外判，而它换来的能力没人要。

**D8 测试策略（seam ② 与 ⑥，不新增缝）。**

| seam | 落点 | 判据 |
|---|---|---|
| ⑥ CLI 黑盒 | 新 `tests/test_cli_config.py` | 发现顺序三条、显式指定不存在、层叠优先级三条（含「与默认同值的开关」）、非法 TOML、类型不对、未知键、`prompt` / `api_key` 进配置、空白名单合法、白名单未知名、缺密钥（退出码 2 + 无日志 + 无请求）、两份配置下 payload 不同 |
| ⑥ CLI 黑盒 | 改 `tests/test_cli_provider.py` | `test_an_unset_key_env_still_sends_the_request` 翻成「退出码 2、无日志、`len(requests) == 0`」；「密钥只进请求头」与 payload 三条不动 |
| ② 工具注册 | 改 `tests/test_tool_registry.py` | `build_registry` 的筛选、`None` 全开、`[]` 空表、未知名是 `ConfigFailure` |
| ① 回合循环 | 改 `tests/test_turn_loop.py` | 空白名单下工具调用仍是 `UNKNOWN_TOOL` 且回合正常 `turn/end` |
| ④ 日志与折叠 | 改 `tests/test_context_fold.py` | 空 `tools` 时头部工具块的形状（没有工具块也不炸） |

## Risks / Trade-offs

- [密钥判据前移推翻一条既有判据] → 它是规格改判的必然结果，delta 里用 REMOVED + ADDED 明写；翻红的那条测试与规格同时改，不留「测试自己改绿」。
- [argparse 默认值改 `None` 后，`--max-turns` 之类仍要判类型与下界] → 下界判断从 `args` 移到层叠之后统一判，错误形状仍是 `INVALID_ARGUMENT` + 2；既有判据 `--window 至少为 1` 那两条要确认仍绿。
- [`tools = []` 让模型没有工具可用] → 合法但别扭；折叠头部与 `model/request` 的 `tools` 都要能是空列表，判据覆盖（D8 最后一行）。
- [配置文件里的 `workspace` 与发现用的 workspace 不一致] → D7 明写，人手验收里演示一次「配置写在旧目录、工作区指向新目录」。
- [新模块 `config/` 拉低覆盖率地板] → 它的每条判据都来自上面的表，不凑低价值测试；`ConfigFailure` 的每个 `code` 都要有可达判据（Active Lesson 1）。
- [`tomllib` 不区分「整数 3」与「布尔 True」在 Python 里是 `bool` 是 `int` 的子类] → 类型判据按声明的字段表逐键判，`max_turns = true` 视为类型不对。

## Migration Plan

无部署与回滚问题（headless CLI，无发布目标）。实现顺序即 tasks 顺序：先立 `config/` 的读与层叠（seam ⑥ 判据先红），再换工具表来源，再立 `ProviderEndpoint`，最后翻密钥那条判据。旧形状没有兼容层：`--config` 未给且没有配置文件时，行为与 M8 之后逐字相同（除密钥缺失）。

## Open Questions

- 配置文件本身要不要进 `session/start` 的 payload（路径或哈希）。当前不记；若 M11 的 resume 需要「同一份配置重放」，那时再立，不影响本 change 的规格与任务拆分。
