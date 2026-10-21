# M9 变异测试轮（`m9-assembly-and-config-layering`）

跑法：改坏一处实现 → 跑测试 → 记录「变异 / 改法 / 哪些测试变红」→ 还原并确认回到基线。施加变异前先看 `git status --short`：本轮工作树里有与 M9 无关的未提交改动（`docs/tools/`、`repowiki/`、`.gitignore`），还原只针对本轮改过的 `src/` 文件（用 `edit` 逐条还原，不用 `git checkout`，避免把未提交的相关改动一起回滚）。

**13 条变异分两段**：编号 1–9 是各组实现落地时顺手跑的**定向轮**（跑受影响的三到四个测试文件，33–91 条），编号 10–13 是收尾的**全量轮**（`uv run pytest -q`，321–323 条）。定向轮的记录同时写在对应的提交信息里。

轮末基线：**323 passed / 2 skipped**，`TOTAL 1505 / 69 未覆盖 / 95%`，`mypy --strict` 28 个源文件干净，`ruff check` 干净（66 个文件），`ruff format --diff` 空，`openspec validate --all --strict` 10 项全过。

## 变异与结果

| 编号 | 改法 | 轮次 | 结果 |
|---|---|---|---|
| 1 | 配置文件压过命令行：`layer_settings` 的 `if from_flag is not None` → `if from_flag is not None and name not in config` | 定向 | 杀：2.2 `test_the_cli_flag_overrides_the_config_file`、2.3 `test_a_flag_equal_to_the_builtin_default_is_still_explicit` |
| 2 | 配置文件那一层整个删掉：`elif name in config` → `elif False` | 定向 | 杀：1.1 / 1.2 / 2.1 / 2.4 / 2.5 |
| 3 | 白名单被忽略：`build_registry` 的 `if names is None` → `if True` | 定向 | 杀：3.2–3.7 共七条；3.1 `test_the_builtin_registry_has_six_definitions_in_order` 存活（它判的是「`None` 是全开」那一支，白名单忽略与否不影响它——不是覆盖缺口） |
| 4 | 装配处不把端点交给内核：`SessionSettings(endpoint=endpoint)` → `endpoint=None` | 定向 | 杀：4.2 / 4.3 与既有 `test_openai_run_records_base_url_model_and_the_key_variable_name`、`test_the_key_reaches_the_request_header_and_nowhere_else`（四条） |
| 5 | payload 里的 `model` 取 provider 名：`start_payload["model"] = settings.endpoint.model` → `= settings.provider_name` | 定向 | 杀：4.1 / 4.3 与既有那条 openai payload 判据（三条）。4.2 存活——它只判「三条在不在」，不判值 |
| 6 | 空串放过：`if not api_key` → `if api_key is None` | 定向 | 杀：5.2 `test_an_empty_key_env_is_an_argument_error`（只此一条） |
| 7 | 密钥判据反过来：`if not api_key` → `if api_key` | 定向 | 杀：5.1 / 5.2 / 5.3 与另外七条 openai 判据，共十条；5.4 `test_a_mock_run_needs_no_key` 存活（mock 那一支本来不碰密钥，正是它要钉的） |
| 8 | 工作区根那份不认：`discover_config` 末尾 `return candidate if candidate.is_file() else None` → `return None` | 定向 | 杀：6.1 / 6.2 连同 12 条既有配置判据，共十四条 |
| 9 | 白名单里的未知名不判：`if name not in known` → `if name not in known and False` | 定向 | 杀：6.3 `test_every_config_failure_code_is_reachable`、`test_an_unknown_tool_name_in_the_whitelist_is_a_config_failure`、`test_an_unknown_tool_name_in_the_config_is_an_argument_error` |
| 10 | 层叠顺序互换：`layer_settings` 里配置层与命令行层对调（配置压过 flag） | **全量** | 杀：2.2、2.3（`2 failed, 321 passed, 2 skipped`） |
| 11 | 白名单被忽略（全量重跑编号 3）：`if names is None` → `if True` | **全量** | 杀：3.2–3.7、6.1、6.3 与 seam ① 的 `test_a_tool_call_is_unknown_when_the_whitelist_is_empty`、seam ④ 的 `test_a_fold_with_no_tools_still_matches_replay`，共九条（`9 failed, 314 passed, 2 skipped`） |
| 12 | 密钥不是必需项：`if not api_key` → `if not api_key and False` | **全量** | 杀：5.1 / 5.2 / 5.3 与 6.2（`4 failed, 319 passed, 2 skipped`）。失败输出里看得见旧行为：`PROVIDER_TRANSPORT: All connection attempts failed`、退出码 1 |
| 13 | payload 不写端点三条：`if settings.endpoint is not None` → `... and False` | **全量** | 杀：4.1 / 4.2 / 4.3 与既有两条 openai payload 判据（`5 failed, 318 passed, 2 skipped`） |

13 条变异全部被至少一条测试杀死，没有存活项，因此没有需要补的覆盖缺口。每条都改变可观察行为（payload 字段、退出码、日志有无、请求有无），没有语义等价的 dud mutant。

## 两条值得记的形状

**「绿到即钉」的判据要靠变异证明它不是空判据。** 本轮有七条判据写出来时就是绿的（4.2 / 4.3 / 4.4 / 5.3 / 5.4 / 6.1 / 6.2 / 6.3——它们复述的是同一件事在更早切片里已经落地的行为）。它们各自在变异下的表现记在上表：只有 5.4 与 3.1 在针对它们的变异下存活，而两处存活都是**判据本来就该放过那个变异**（mock 不碰密钥；`names is None` 是全开）。真正的覆盖缺口是编号 5 里 4.2 的存活——它只判「三条在不在」、不判值，所以「值取错了」这一类坏法它杀不掉；本轮没有为它补断言，因为 4.1 与 4.3 已经判值，判据面不重复。

**定向轮与全量轮的差别只在覆盖面。** 编号 3 在定向轮杀七条、在全量轮杀九条：多出来的两条在 seam ① 与 seam ④（白名单空表在回合循环与折叠里各有一条判据）。定向轮看不到它们——这是「收尾跑全量」这条规矩的实际收益。
