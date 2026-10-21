# Tasks

## 1. 配置文件的读与非法形状（seam ⑥）

- [x] 1.1 seam ⑥：先写红判据 `test_an_explicit_config_file_sets_the_settings`——`minihns run -p "x" --config <dir>/other.toml`（文件写 `max_turns = 3`，工作区根同时有一份 `mini.config.toml`）后 `session/start` 的 payload 里 `max_turns` 为 3 且取自 `other.toml`；实现 `--config` 开关与 `config/load.py::load_config`，判据转绿
- [x] 1.2 seam ⑥：红判据 `test_the_workspace_root_config_file_is_picked_up`——未给 `--config` 且工作区根有 `mini.config.toml` 时其设置生效；实现发现顺序的第二级，判据转绿
- [x] 1.3 seam ⑥：绿到即钉的守卫判据 `test_no_config_file_means_builtin_defaults`——两处都没有时 payload 与 M8 之后的形状逐字段相同（含 `tools` 六个名字）；只加判据，实现不动
- [x] 1.4 seam ⑥：红判据 `test_a_missing_explicit_config_file_is_an_argument_error`——`--config` 指向不存在的路径时退出码 2、stderr 含 `INVALID_ARGUMENT` 与所查找路径、`tmp_path.glob("*.jsonl") == []`；实现 `ConfigFailure("CONFIG_NOT_FOUND", ...)` 到退出码 2 的映射
- [x] 1.5 seam ⑥：红判据 `test_a_malformed_config_file_is_an_argument_error`——内容 `max_turns = = 3` 时退出码 2、stderr 含 `INVALID_ARGUMENT` 与行号、无日志；实现 `tomllib` 的解码失败塌成 `ConfigFailure("CONFIG_INVALID_TOML", ...)`
- [x] 1.6 seam ⑥：红判据两条 `test_an_unknown_key_is_an_argument_error` 与 `test_a_wrong_typed_value_is_an_argument_error`（`max_turns = "three"` 与 `max_turns = true` 各一条）；实现字段表校验，detail 带键名
- [x] 1.7 seam ⑥：红判据两条 `test_prompt_in_the_config_file_is_an_argument_error` 与 `test_a_literal_api_key_in_the_config_file_is_an_argument_error`；实现「`prompt` / `fixture` / `api_key` 不得出现在配置里」，判据转绿
- [x] 1.8 seam ⑥：红判据 `test_an_empty_config_file_equals_no_config_file`——空文件时 run 正常跑完且 payload 是内置默认；实现「零键文件合法」

## 2. 层叠优先级（seam ⑥）

- [x] 2.1 seam ⑥：判据 `test_the_config_file_overrides_builtin_defaults`——配置写 `max_turns = 3`、命令行未给 `--max-turns` 时 payload 里 `max_turns` 为 3；实现 `config/layering.py::layer_settings` 的第一层
- [x] 2.2 seam ⑥：红判据 `test_the_cli_flag_overrides_the_config_file`——配置写 3、命令行给 `--max-turns 5` 时 payload 里为 5；实现 CLI 层覆盖
- [x] 2.3 seam ⑥：判据 `test_a_flag_equal_to_the_builtin_default_is_still_explicit`——配置写 `max_turns = 3`、命令行显式给 `--max-turns 8`（内置默认也是 8）时取命令行这一层；实现 argparse 的 `default=None` 哨兵（design D2），既有 `--window` / `--reserve` 下界判据仍绿。原写法「配置也写 8」在两种实现下都绿、判不出 D2，已改成「配置 3 + 显式 8」
- [x] 2.4 seam ⑥：判据 `test_a_config_value_below_a_bound_is_an_argument_error`——配置写 `window = 0` 时退出码 2、stderr 含 `INVALID_ARGUMENT` 与 `window`、无日志；实现下界判断移到层叠之后统一判（design 的 Risks 第二条）
- [x] 2.5 seam ⑥：判据 `test_a_config_file_setting_a_provider_selects_that_provider`——配置写 `provider = "openai"` 且命令行未给 `--provider` 时走 openai 那一支（用「openai 与 `--fixture` 互斥」这条错误观察走了哪一支，不真发请求）；实现 provider 选择的层叠。原写法「配置写 mock」判不出层叠——mock 也是内置默认

## 3. 工具表从装配来（seam ② 与 ⑥）

- [x] 3.1 seam ②：判据 `test_the_builtin_registry_has_six_definitions_in_order`——`build_registry(None)` 产出 `read, write, edit, glob, grep, bash` 六个且顺序固定；实现 `config/assembly.py::build_registry`
- [x] 3.2 seam ②：判据 `test_a_whitelist_keeps_only_the_listed_tools`——`build_registry(["read", "grep"])` 只留两个且顺序按内置顺序；实现白名单筛选
- [x] 3.3 seam ②：判据 `test_an_empty_whitelist_is_legal`——`build_registry([])` 是空注册表、`specs()` 为空列表；实现「空列表合法」
- [x] 3.4 seam ②：判据 `test_an_unknown_tool_name_in_the_whitelist_is_a_config_failure`——`build_registry(["read", "web_search"])` 返回 `ConfigFailure` 且 detail 含 `web_search`；实现未知名判据
- [x] 3.5 seam ⑥：红判据 `test_the_configured_tool_whitelist_reaches_payload_and_model_request`——配置写 `tools = ["read", "grep"]` 时 `session/start` 的 `tools` 恰含这两个、`model/request` 的工具面也只有这两个；实现 CLI 装配处换掉硬编码那行（`cli/main.py:144`）。另加 `test_an_unknown_tool_name_in_the_config_is_an_argument_error`：config-layering 规格「白名单里的未知名是参数错误」要求退出码 2 与不建日志，这是它的 seam ⑥ 那一半
- [x] 3.6 seam ①：判据 `test_a_tool_call_is_unknown_when_the_whitelist_is_empty`——`tools = []` 时 Provider 的工具调用产出 `outcome: UNKNOWN_TOOL` 且该回合正常 `turn/end`；确认回合循环与派发段无需改动，判据转绿
- [x] 3.7 seam ④：判据 `test_a_fold_with_no_tools_still_matches_replay`——空 `tools` 的一次 run 逐点重放仍相等、头部没有工具块也不炸；确认 `events/fold.py` 的头部派生已能处理空列表

## 4. `ProviderEndpoint` 与「是不是 openai」塌成一处（seam ① 与 ⑥）

- [x] 4.1 seam ①：红判据 `test_the_endpoint_fields_come_from_one_endpoint_object`——`SessionSettings(endpoint=ProviderEndpoint(...))` 时 `session/start` 的 payload 里 `base_url` / `model` / `api_key_env` 三条齐、mock 路径（`endpoint=None`）时三条都不在；实现 `loop/settings.py::ProviderEndpoint` 与 `turn_loop` 的 payload 派生（删掉 `provider_name == "openai"` 那处）
- [x] 4.2 seam ⑥：判据 `test_the_cli_decides_the_endpoint_once`——一次 openai run 的 payload 三条与一次 mock run 的 payload 缺三条，都由装配处的同一个判断决定（既有 `test_openai_run_records_base_url_model_and_the_key_variable_name` 保持绿）；实现 CLI 装配段（`cli/main.py` 三处塌成一处）
- [x] 4.3 seam ⑥：判据 `test_a_config_file_can_supply_the_endpoint`——配置写 `base_url` / `model` / `api_key_env` 且命令行未给时 payload 取自配置；端点三条的层叠随 2.2 的 `layer_settings` 一起到位
- [x] 4.4 seam ⑤：绿到即钉的守卫判据 `test_the_provider_still_accepts_no_key_and_sends_no_header`——`OpenAICompatProvider(api_key=None)` 仍能发出无鉴权请求（既有 `test_the_authorization_header_is_present_only_when_a_key_is_given` 保持绿）；provider 契约与 `generate` 签名不动

## 5. 密钥是装配的必需项（seam ⑥）

- [x] 5.1 seam ⑥：把 `tests/test_cli_provider.py::test_an_unset_key_env_still_sends_the_request` 改写成 `test_an_unset_key_env_is_an_argument_error`——退出码 2、stderr 含 `INVALID_ARGUMENT` 与变量名、无日志、`len(endpoint.requests) == 0`；先跑红，再实现装配阶段的密钥判据（design D6）
- [x] 5.2 seam ⑥：红判据 `test_an_empty_key_env_is_an_argument_error`——变量设为空串时同样退出码 2 且无日志无请求；实现「未设或为空」的同一判据
- [x] 5.3 seam ⑥：判据 `test_a_config_supplied_provider_is_checked_the_same_way`——配置写 `provider = "openai"`、命令行未给 `--provider`、密钥变量未设时同样 2 且无日志；确认密钥判据在层叠之后判
- [x] 5.4 seam ⑥：绿到即钉的守卫判据 `test_a_mock_run_needs_no_key`（计划里的名字是 `test_a_mock_run_never_requires_a_key`，实现时改成前者）——mock 路径不受密钥判据影响（既有 mock 判据全绿）；只加判据

## 6. 完成判据与文档

- [x] 6.1 seam ⑥：完成判据第一条——判据 `test_the_same_cli_under_two_config_files_yields_different_payloads`：同一份命令行分别在「工作区根写着 `max_turns = 2` 与 `tools = ["read"]`」与「没有配置文件」两种情况下跑，两份日志的 payload 里 `max_turns` 为 2 与 8、`tools` 分别只含 `read` 与含六个内置名；确认判据可复现
- [x] 6.2 seam ⑥：完成判据第二条——判据 `test_a_missing_required_item_leaves_no_log_file`：缺必需项（密钥与非法配置各一次）时退出码 2、stderr 含 `INVALID_ARGUMENT`、session 目录里没有任何新文件（用目录快照前后对比断言）
- [x] 6.3 seam ②（不是 ⑥）：判据 `test_every_config_failure_code_is_reachable`——`ConfigFailure` 的每个 `code`（`CONFIG_NOT_FOUND` / `CONFIG_INVALID_TOML` / `CONFIG_UNKNOWN_KEY` / `CONFIG_INVALID_VALUE` / `CONFIG_FORBIDDEN_KEY` / `UNKNOWN_TOOL_NAME`）各有一条构造路径；计划里的第七个码 `MISSING_API_KEY` 不存在——规格定的是 stderr 含 `INVALID_ARGUMENT`，密钥判据是 CLI 层的参数错误，不是 `ConfigFailure`
- [x] 6.4 门禁：跑四道（`ruff format --diff` / `ruff check` / `mypy --strict` / coverage 四步）确认全绿且 `TOTAL` ≥ 95%；`openspec validate --all --strict` 全绿
- [x] 6.5 人手验收：拿它办一件真事——在一个真工作区里放一份 `mini.config.toml`（改 `tools` 与 `max_turns`）、再用 `--config` 指向另一份、再来一次缺密钥的 run，把观察（含「别扭在哪」）记进 `docs/verification/m9-assembly-and-config-layering-manual.md`；不进 CI。**真模型那一半待人跑**（命令在文档末尾），agent 这一半跑了五次 run
- [x] 6.6 文档：用 `domain-modeling` 技能写一份新 ADR（`0018-config-is-three-layer-override`：配置层叠三层、工具白名单、密钥缺失当场失败这三处的取舍与代价，含「DSH 是 patch 层叠 + 环境变量覆盖，mini 版故意简化成 TOML 三层」）；并在 `docs/adr/0002-deferred-refactors.md` 第 14、15 条各加一条「已处理（M9，2026-10-21）」的改判行；顺带把 M9 的五个词（装配 / 层叠 / 工具白名单 / 端点 / 必需项）写进 `GLOSSARY.md`

## 7. 收尾门禁

- [x] 7.1 变异测试一轮：改坏 `config/` 与装配段的实现（层叠顺序、白名单筛选、密钥判据、端点派生各至少一处），跑全量 `uv run pytest -q`，把「变异 / 改法 / 哪些测试变红」记进 `docs/verification/m9-assembly-and-config-layering-mutation.md`，还原前先看 `git status`，还原后确认回到基线。**13 条变异全部被杀**：编号 1–9 是各组实现落地时顺手跑的定向轮（记录也在提交信息里），编号 10–13 是收尾全量轮（层叠顺序互换 / 白名单被忽略 / 密钥不是必需项 / payload 不写端点三条），无存活项、无 dud mutant。还原后基线确认：323 passed / 2 skipped、`TOTAL 1505 / 69 / 95%`
- [x] 7.2 Learning Gate：扫本轮证据（红过的测试、存活的变异、返工过的规格、工具坑）写进 `docs/lessons.md` 收件箱；无可复用信号则写 `NO-PROMOTION`。新收五条 L-041–L-045，关闭零条，留存八条，**AGENTS.md 本轮不晋升（NO-PROMOTION）**；收件箱 13 条

## Workflow follow-up

- 在 change 分支上跑 `code-review`（Standards / Spec 两轴，固定点 `main`）并处理或记账发现。
- 归档前先 sync：把四份 delta（`config-layering` 新建、`cli`、`file-tools`、`turn-loop` 修改）应用进 `openspec/specs/`，`openspec validate --all --strict` 全绿后再 `openspec archive m9-assembly-and-config-layering -y --skip-specs`。
- 跑 `agents-md-slim`。
- 征求人的批准后合并进 `main`、打 tag `m9`、删 change 分支。
