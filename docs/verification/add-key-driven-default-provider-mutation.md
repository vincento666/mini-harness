# 变异测试一轮（`add-key-driven-default-provider`）

**基线**：`424 passed / 5 skipped`，`TOTAL 1960 stmts / 93 missing = 95%`（提交 `5638bb7`）。
**结果：四个变异全部被杀，没有存活的变异。**

跑法：`.tmp/mutB/mut_run.py` + `.tmp/mutB/mutants.json`，**严格串行**——每个变异做一处字面替换 →
跑全量 `pytest -q -rf --tb=no` → `git checkout -- <file>` 还原 → 记 `git status --short -- <file>`
是否为空。四个变异都在已提交的 HEAD 之上跑（runner 的还原是 `git checkout`，未提交的改动会被一起
回滚，所以先提交再跑）。结果 JSON 在 `.tmp/mutB/results2.json`。

| 变异 | 改法 | 红几条 | 判据在哪个 seam |
|---|---|---|---|
| M1 | 预设表里 `openai` 的 `api_key_env` 改回 `DEEPSEEK_API_KEY` | 6 | ② 与 ⑥ |
| M2 | 覆盖规则改成「预设总是覆盖」（`values[name] = fallback if from_layer is None else from_layer` → `values[name] = fallback`） | 18 | ② 与 ⑥ |
| M3 | 密钥在场规则改成「总是 mock」（`_provider_of` 末尾 `return DEFAULT_PROVIDER`） | 2 | ② 与 ⑥ |
| M4 | 缺 model 的检查删掉（`if layered.model is None:` → `if False and layered.model is None:`） | 3 | ⑥ |

## M1（6 红）

- `tests/test_config_presets.py::test_the_openai_preset_is_openai_not_deepseek`
- `tests/test_config_presets.py::test_the_key_present_makes_openai_the_builtin_default`
- `tests/test_config_presets.py::test_the_preset_never_overrides_a_model_the_config_file_gave`
- `tests/test_cli_provider.py::test_a_bare_run_with_the_key_present_defaults_to_openai`
- `tests/test_cli_provider.py::test_a_config_file_provider_does_not_look_at_the_key_presence`
- `tests/test_cli_provider.py::test_openai_without_a_base_url_does_not_run_on_the_deepseek_default`

这一族就是 change 的动机本身：默认变量名回到 deepseek 那一套，六条一起红。

## M2（18 红）

seam ② 两条（`test_the_preset_never_overrides_a_flag_that_was_given`、
`test_the_preset_never_overrides_a_model_the_config_file_gave`）之外，红的是 seam ⑥ 上那些**给了
`--base-url` 的判据**：`test_cli_provider.py` 里十一条（`test_the_cli_decides_the_endpoint_once`、
`test_a_config_file_can_supply_the_endpoint`、`test_the_key_reaches_the_request_header_and_nowhere_else`、
`test_an_unset_key_env_is_an_argument_error`、`test_an_empty_key_env_is_an_argument_error`、
`test_openai_run_records_base_url_model_and_the_key_variable_name`、
`test_a_config_supplied_provider_is_checked_the_same_way`、`test_a_dead_endpoint_collapses_into_a_transport_result`、
`test_a_hostile_no_proxy_does_not_stop_the_request`、`test_a_200_without_choices_is_a_schema_error_at_the_cli`、
`test_the_deepseek_name_is_accepted_and_its_preset_is_recorded`、
`test_a_missing_model_fails_before_any_request_is_sent`）、`test_cli_config.py::test_a_missing_required_item_leaves_no_log_file`、
`test_cli_chat.py` 两条（`test_a_provider_failed_segment_says_so_on_stderr`、
`test_a_chat_that_cannot_start_leaves_no_log`）、`test_cli_serve.py::test_provider_failure_in_serve_is_a_process_exit`。

**这一轮的变异半径最大的一条**：`layer_settings` 里一行改成「预设总是覆盖」，红从 chat / serve / config
一路打到 provider。M2 的红数（18）比 M1（6）与 M3（2）高一个量级，因为覆盖规则是所有端点判据的公共
前提——它们全靠「CLI 给的那一项不被覆盖」才能把请求指到 loopback 假 server。

## M3（2 红）

- `tests/test_config_presets.py::test_the_key_present_makes_openai_the_builtin_default`
- `tests/test_cli_provider.py::test_a_bare_run_with_the_key_present_defaults_to_openai`

只有这两条红，正是设计要的形状：这条规则只在「CLI 与配置文件都没给」时才生效，给了的判据一条都不该
被它影响。红数 2 是这条规则的**边界**证据，不是缺口。

## M4（3 红）

- `tests/test_cli_provider.py::test_a_bare_run_with_the_key_present_defaults_to_openai`
- `tests/test_cli_provider.py::test_openai_without_a_base_url_does_not_run_on_the_deepseek_default`
- `tests/test_cli_provider.py::test_a_missing_model_fails_before_any_request_is_sent`

**代价要写明**：M4 之下后两条判据会真去连 `https://api.openai.com/v1`（argv 没给 `--base-url`，预设
给的就是它），全量跑从基线 3 分 15 秒涨到 **4 分 02 秒**。这是「地雷」那类判据的形状决定的：判「不再
静默连某个第三方默认地址」，判据本身就得带着那个默认地址在场。跑变异时要知道这一条会出网。

## 没有存活的变异

四条都被至少一条测试杀死，本轮没有覆盖缺口要补。

## 流程欠账（记进 `docs/adr/0002`）

AGENTS.md 的顺序是 apply → 两轴 → 变异 + Learning Gate → 归档。本轮**变异跑在两轴之前**，这是连续第三轮
同一笔欠账（上一轮记在 `fix-small-window-compaction-dead-zone` 的 mutation 文档里）。若两轴查出实现要改，
变异轮就得重跑。另：第一次跑时 runner 解析 `FAILED` 行的那一行写歪（`line.split(" ")[0]` 永远得到
`FAILED`），只拿到计数没拿到名字；第二次重跑才拿到名字，**两轮计数逐条相同**（6 / 18 / 2 / 3），重跑的
代价是 12 分钟，换来的是这份文档里能列出判据名字。
