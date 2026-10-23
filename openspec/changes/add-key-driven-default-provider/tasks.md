# Tasks

## 1. 预设表这一处事实（seam ②）

- [x] 1.1 红：写判据——生效 provider 为 `openai` 且未给端点三项时，装配出的端点是 `https://api.openai.com/v1` / 无 model / `MINIHNS_API_KEY`；为 `deepseek` 时是 `https://api.deepseek.com` / `deepseek-chat` / `DEEPSEEK_API_KEY`；为 `mock` 时没有端点对象。确认它红（今天 openai 落到 deepseek 的默认）。**实测红**：`tests/test_config_presets.py::test_the_openai_preset_is_openai_not_deepseek` 红在 `assert 'https://api.deepseek.com' == 'https://api.openai.com/v1'`，`test_the_mock_preset_has_no_endpoint` 红在 `assert 'https://api.deepseek.com' is None`；`test_the_deepseek_preset_is_the_deepseek_triple` 当时就绿——今天那四个默认恰好就是 deepseek 那一套，这条判据的作用是不让它再当所有人的默认。
- [x] 1.2 绿：把 `loop/settings.py` 的四个常量换成按 provider 名索引的预设表（`model` 在 `openai` 预设里是 `None`），1.1 变绿且 `uv run mypy --strict src` 无新错。**实测**：`PROVIDER_NAMES` + `ProviderPreset` + `PROVIDER_PRESETS` 三条；`EffectiveSettings` 的端点三项改成 `str | None`（`None` 是「这一项没有默认」，不是空串），`layer_settings` 里 `provider` 与端点三项从 `BUILTIN_DEFAULTS` 挪出来单独算；`cli/main.py` 因此必须处理 `None`——缺 model 当场 `INVALID_ARGUMENT` 指出 `--model`（组 4 的规则提前落地，见 4.1 那一笔）。
- [x] 1.3 红：写覆盖规则判据——CLI 给过 `--base-url` 时预设不覆盖它、配置文件给过 `model` 时预设也不覆盖它、两者都没给时预设填上。确认它红或确认它已绿（若已绿，用变异确认它咬得住，并记在这里）。**实测：三条落地即绿**（1.2 已把覆盖规则写进 `layer_settings`），红不是当场踩的；它咬不咬得住由组 8 的变异 ②「预设总是覆盖」判，结果记在 `docs/verification/add-key-driven-default-provider-mutation.md`。

## 2. 默认 provider 由密钥在场决定（seam ② 与 ⑥）

- [x] 2.1 红：写判据——CLI 与配置文件都没给 `provider` 时，`MINIHNS_API_KEY` 已设且非空 → 生效 provider 为 `openai`；未设或为空串 → 生效 provider 为 `mock`。判据显式构造子进程环境，MUST NOT 继承本机真实密钥。确认它红。**实测**：seam ② 三条（`test_the_key_present_makes_openai_the_builtin_default` / `test_no_key_means_the_builtin_default_is_still_mock` / `test_a_given_provider_is_not_overridden_by_the_key`）+ seam ⑥ 两条（`test_a_bare_run_with_the_key_present_defaults_to_openai` / `test_a_bare_run_without_the_key_still_defaults_to_mock`）。这一条的红不是当场踩的——1.2 落地时 `_provider_of` 已经写了这条规则（见 1.2 那一笔的提前落地），所以按 L-055 那一套实证（编号在并行分支 `fix-small-window-compaction-dead-zone` 的 `docs/lessons.md` 里，本分支从 `01573b4` 分叉、当时最高是 L-054，合并时不重编号）：把 `_provider_of` 临时改回 `return DEFAULT_PROVIDER` 跑一次，两条红（`assert 'mock' == 'openai'` 与 `assert '--model' in '…--provider mock 需要 --fixture…'`），还原后 `git status --short -- src/mini_harness/config/layering.py` 为空。子进程环境一律 `env=_env_without_default_key()`：先 `pop("MINIHNS_API_KEY")` 再写假值，本机两个真实变量都不继承（实测进程环境里 `DEEPSEEK_API_KEY` 与 `MINIHNS_API_KEY` 都不在）。
- [x] 2.2 绿：实现这一条内置默认规则，2.1 变绿；既有的「配置文件覆盖内置默认」「命令行覆盖配置文件」「与默认同值的命令行开关仍是显式值」三条判据全部仍绿。**实测**：规则在 `layer_settings` 的 `_provider_of`——`_from_layers` 先问 CLI 层与配置文件层，两层都没给才看 `env.get(DEFAULT_PROVIDER_KEY_ENV)`；`env` 是第三个参数、默认 `os.environ`，seam ② 的判据因此能显式喂一份假环境。既有的三条在 `tests/test_cli_config.py`，全量跑里仍绿。
- [x] 2.3 红：写「配置文件写 `provider = "openai"` 时不看密钥在场」的判据（该变量未设 → 退出码 2、`INVALID_ARGUMENT` 与变量名）。确认它红。**实测**：判据是 `test_a_config_file_provider_does_not_look_at_the_key_presence`，落地即绿（1.2 的预设已把 `openai` 的默认变量名换成 `MINIHNS_API_KEY`）。按同一套实证（见 2.1 那一笔）它红过：把预设表里 `openai` 的 `api_key_env` 临时改回 `DEEPSEEK_API_KEY` 跑一次，它红在 `assert 'MINIHNS_API_KEY' in 'INVALID_ARGUMENT: 环境变量 DEEPSEEK_API_KEY 未设置或为空…'`，同一轮里 `test_a_bare_run_with_the_key_present_defaults_to_openai` 也红；还原后 `git status --short -- src/mini_harness/loop/settings.py` 为空。这一处临时改动就是组 8 的变异 ①，正式那一轮在 8.1 跑。

## 3. 词表加 `deepseek`，地雷拆掉（seam ⑥）

- [x] 3.1 红：`minihns run -p "x" --provider deepseek`（`DEEPSEEK_API_KEY` 在假环境里已设、base_url 用 loopback 假 server）→ 退出码 0、`session/start` 的 payload 里 `provider` 为 `deepseek`、请求打到预设地址。确认它红。**实测红**：`test_the_deepseek_name_is_accepted_and_its_preset_is_recorded` 红在 `assert 2 == 0`，stderr 是 `UNKNOWN_PROVIDER: --provider 只接受 mock 或 openai，收到 deepseek`。判据里「请求打到预设地址」那一半没在黑盒判：拿 loopback 假 server 就得给 `--base-url`，给了就不叫预设——地址由 seam ② 的 `test_a_config_file_provider_gets_its_own_preset` 断言（`base_url == https://api.deepseek.com`），真实那一半由 6.2 判。黑盒判的是名字进 payload 且 `model` / `api_key_env` 由预设填上（`deepseek-chat` / `DEEPSEEK_API_KEY`）。
- [x] 3.2 红：`--provider claude` 仍打 `UNKNOWN_PROVIDER`、退出码 2、没有 session 日志。确认它已绿，并用变异确认它咬得住。**实测**：既有判据 `test_unknown_provider_is_exit_2_and_creates_no_log` 加了一条断言 `assert "deepseek" in result.stderr`（词表现在三个词，那句话得写全），加完即红在 `assert 'deepseek' in '…只接受 mock 或 openai…'`，3.4 变绿。咬合由组 8 判。
- [x] 3.3 红：`--provider openai` 不带 `--base-url` 时装配出的端点是 `https://api.openai.com/v1`（黑盒里用 `--dry-run` 类判据不可用，改为断言 stderr 里缺 `--model` 的那条 `INVALID_ARGUMENT` 与日志未创建）。确认它红。**实测：落地即绿**（判据 `test_openai_without_a_base_url_does_not_run_on_the_deepseek_default`，1.2 已把 openai 的默认端点换成 openai 自己的、并把缺 model 写成 `INVALID_ARGUMENT`）。生效地址本身在 seam ② 判（`test_the_openai_preset_is_openai_not_deepseek` 红过，见 1.1）。
- [x] 3.4 绿：实现词表与端点构造，3.1 与 3.3 变绿；既有的「未知 provider」「密钥变量未设」「密钥只进请求头」三条判据仍绿。**实测**：词表那一行从硬编码 `("mock", "openai")` 换成 `PROVIDER_NAMES`（`loop/__init__.py` 导出、CLI 从 `mini_harness.loop` 引），那句话由 `' / '.join(PROVIDER_NAMES)` 生成；端点分支从 `provider_name == "openai"` 换成 `provider_name != "mock"`，`--fixture` 那句也带上名字。既有的三条仍绿。两处连带：`tests/test_cli_run.py::test_unknown_provider_is_rejected` 与 `tests/test_integration.py` 第 94 行原本拿 `deepseek` 当「不认识的 provider」——它现在认识了，两处换成 `claude`；后者在换名之前仍绿但绿的原因变了（从「名字不认识」变成「缺密钥」），换名是为了让它继续测它本来测的那件事。

## 4. 缺 model 当场失败（seam ② 与 ⑥）

- [x] 4.1 红：`--provider openai --api-key-env <已设的假变量>` 且未给 `--model` → 退出码 2、stderr 含 `INVALID_ARGUMENT` 与 `--model`、session 目录里没有新文件、假 server 没收到任何请求。确认它红。**实测：落地即绿**（判据 `test_a_missing_model_fails_before_any_request_is_sent`，`len(endpoint.requests) == 0` 是「一个请求都不发」那一半）。按同一套实证（见 2.1 那一笔）它红过：把 `cli/main.py` 里那条检查临时改成 `if False and layered.model is None:` 跑一次，三条红——它自己红在 `assert 0 == 0`（退出码 0，请求发了）、`test_openai_without_a_base_url_does_not_run_on_the_deepseek_default` 与 `test_a_bare_run_with_the_key_present_defaults_to_openai` 也红；还原后 `git status --short -- src/mini_harness/cli/main.py` 为空。**记一笔代价**：变异 ④ 之下 `test_openai_without_a_base_url_…` 那条会真去连 `https://api.openai.com/v1`（假密钥，连接失败/401），全量跑从 3 分 39 秒涨到 6 分 60 秒——这条判据的形状只能这样立，跑变异时要知道它会出网。
- [x] 4.2 绿：实现这一条，4.1 变绿；`--provider deepseek` 不带 `--model` 仍成功（预设给了）。**实测**：检查在 1.2 落地时就写进 `cli/main.py`（排在密钥检查之后——既有判据 `test_a_missing_required_item_leaves_no_log_file` 与 `test_a_config_supplied_provider_is_checked_the_same_way` 都要求密钥那一先报，delta 没规定两件事的顺序，这一处顺序记进 ADR-0027）；`--provider deepseek` 不带 `--model` 成功由 3.1 的判据证（`payload["model"] == "deepseek-chat"`）。

## 5. `--help` 写出默认值（seam ⑥）

- [x] 5.1 红：`minihns chat --help`、`minihns run --help`、`minihns serve --help` 的 `--provider` 说明里同时含 `mock`、`openai`、`deepseek`、`MINIHNS_API_KEY`；`--api-key-env` 说明里含两个变量名；输出里不含任何假密钥的值。确认它红。**实测红**：`test_the_help_names_the_provider_rule_and_both_variable_names` 红在 `assert 'mock' in 'usage: minihns run [-h] …'`——三个入口的 `--provider` / `--api-key-env` 两行当时只有 metavar，没有说明。
- [x] 5.2 绿：实现 help 文本（写规则不写运行期值），5.1 变绿。**实测**：两条 `help=` 写在 `shared` 那个 parent parser 上，三个入口一起拿到。写的是规则——「没给时这一层看环境变量 MINIHNS_API_KEY：已设且非空就是 openai，否则是 mock」与「没给时随 provider：openai 读 MINIHNS_API_KEY，deepseek 读 DEEPSEEK_API_KEY」。两处刻意不写 `--`：既有的 `test_run_flag_table_is_the_documented_table` 与 `test_chats_flag_table_is_runs_flag_table_minus_two` 都是从 help 输出里捞以 `-` 开头的 token 来判整张 flag 表，说明文字里带 `--` 会让那两条判据捞到不存在的开关。
- [x] 5.3 跑 `tests/test_vocabulary_reachability.py` 确认 `UNKNOWN_PROVIDER` 仍可达、没有新增 `code`。**实测**：该文件在这一轮里跑过（90 passed / 3 skipped），无红、无新增 code。
- [x] 5.4 跑 `openspec validate --all --strict` 确认两份 delta 结构合法（ADDED 2、MODIFIED 3，被改的每条保留全部既有 scenario 名）。**实测**：`{"items":13,"passed":13,"failed":0}`，退出码 0。

## 6. 真实端点验收（完成判据的第二半，ADR-0024）

- [x] 6.1 本机 Strata：`MINIHNS_API_KEY` 设成端点密钥、`--base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs`，**不给 `--provider`** → 确认默认落到 openai 且会话正常跑完。**实测**：session `e6250b8560c74198bfe9dd5679ab2493`，退出码 0，payload `provider: openai` / `api_key_env: MINIHNS_API_KEY`，`session/end` 是 `MODEL_COMPLETED` `turns: 2`，中间真发生一次 `tool/call → tool/result`。
- [x] 6.2 同一端点跑 `--provider deepseek` 的失败形状：确认它打的是 `https://api.deepseek.com` 而不是本机端点（看 `error/model` 的 `detail`），并确认这条失败是「名字与端点一致」的证据。**实测**：session `d3e1246e88c84f4b830093db4db05cd8`，payload 三项是 deepseek 预设的三项，`detail` 是 `HTTP 401：Authentication Fails, Your api key: ****0000 is invalid (request_id: …)`——这句出自 DeepSeek 服务端；同一进程环境里 `MINIHNS_API_KEY` 是本机真密钥而 `DEEPSEEK_API_KEY` 是假值，被掩码的那份是假值，真密钥没被用。退出码 1、`PROVIDER_ERROR`。
- [x] 6.3 观察记进 `docs/verification/add-key-driven-default-provider-real-endpoint.md`。**已记**：两场各一张观察表，另有一节写清真实那一半没覆盖什么（deepseek 端点能否跑完一个会话本机无证据；「没密钥时裸跑仍是 mock」只在 seam ⑥ 判；本机 `MINIHNS_API_KEY` 平时不在进程环境里，所以「裸跑就能对话」要人自己设上——那是 UAT 的 U1）。

## 7. UAT 验收（完成判据的第三半，ADR-0025，人跑）

- [ ] 7.1 手册骨架已立：`docs/verification/add-key-driven-default-provider-uat.md`（三场：裸跑现在说什么 / `--provider deepseek` 能对话 / `--help` 看得见默认）。
- [ ] 7.2 等人跑完那三场并填回观察表；**表没填完本 change 不得归档、不得合入 `main`**。

## 8. 变异测试一轮

- [x] 8.1 四条变异跑全量并记进 `docs/verification/add-key-driven-default-provider-mutation.md`：① 预设表里 `openai` 的 `api_key_env` 改回 `DEEPSEEK_API_KEY`；② 覆盖规则改成「预设总是覆盖」；③ 密钥在场规则改成「总是 mock」；④ 缺 model 的检查删掉。每条必须被至少一条测试杀死。**实测**：M1 6 红 / M2 **18 红** / M3 2 红 / M4 3 红，**没有存活的变异**；每次还原后 `git status --short -- <file>` 为空。两处记在文档里：M4 之下两条判据会真去连 `https://api.openai.com/v1`，全量跑从 3 分 15 秒涨到 4 分 02 秒；变异跑在两轴之前（连续第三轮同一笔欠账），且第一次跑只拿到计数、重跑一次才拿到判据名字。

## 9. Learning Gate

- [x] 9.1 扫本轮证据写进 `docs/lessons.md` 收件箱；**收件箱已到上限 15 条，先消化再收新条**。**实测**：关闭 L-050（`rejected`）与 L-043，合并 L-041 + L-053 → L-036、L-052 → L-048、L-037 → L-039，留存九条各补一条本轮证据，新收 L-058 / L-059 / L-060（编号说明：L-055 至 L-057 由并行分支 `fix-small-window-compaction-dead-zone` 占用，合并时不重编号）。消化后 12 条、空闲 3 条。
- [x] 9.2 立 ADR-0027（provider 名字是端点预设名、默认 provider 由 `MINIHNS_API_KEY` 在场决定、为什么不猜 model），并改 `AGENTS.md` 技术选型里「默认 `DEEPSEEK_API_KEY`」那半句（一进一出）。**实测**：`docs/adr/0027-provider-names-are-endpoint-presets.md`；一进是那句改成「默认变量随 provider 而定」，一出是「MVP 分两阶段」一节里与文件开头重复的两处路径引用（`docs/CURRENT.md` 与 `docs/roadmap.md` 各留一处）。本轮不晋升 lesson。

## 10. `code-review` 两轴之后的补完（固定点 `2f93d44`）

- [x] 10.1 cli delta 那句 SHALL 比两条 scenario 宽——「设置类 flag 的说明里写出该项当前的默认」，可当时只有 `--provider` 与 `--api-key-env` 有说明，`--max-turns` / `--window` / `--reserve` / `--sandbox` / `--base-url` / `--model` / `--fixture` / `--config` / `--workspace` / `--session-dir` / `--append-system-prompt` 一行说明都没有。补完：数值与档位那几行的默认值**取自 `loop/settings.py` 的常量**（help 里不自己另写一份数字），端点那三行写「随 provider」。**实测红**：`test_the_help_names_the_builtin_default_of_each_setting_flag` 红在 `assert '默认 8' in 'usage: minihns run [-h] …'`。判据一侧是 help 输出、另一侧是模块常量本身（不是把常量抄到断言两侧）。
- [x] 10.2 scenario「默认值说明里没有密钥值」的 WHEN 当时没建立：判据没设 `MINIHNS_API_KEY`，断言的 `_KEY_VALUE` 本来也不会出现在 help 里。补：判据把 `MINIHNS_API_KEY` 设成那把假密钥（`env=_env_without_default_key(**{"MINIHNS_API_KEY": _KEY_VALUE})`）再跑三个入口的 `--help`。**如实标注：这一条不红**——它补的是 WHEN，不是新行为。
- [x] 10.3 `cli/main.py` 那两处 `assert layered.base_url is not None` / `assert layered.api_key_env is not None` 的前提是「词表与预设表同名单、且非 mock 预设这两项不是 None」，当时没有任何判据钉这个前提。补 seam ② 一条：`test_every_provider_name_has_a_preset_with_the_two_required_slots`（`PROVIDER_NAMES == tuple(PROVIDER_PRESETS)` + 逐名核这两项）。**如实标注：落地即绿**（前提今天成立），它是守卫——往词表加一个名字而预设表没跟上时，红在这条判据，而不是红在用户面前一条 `AssertionError`（不变量 B / F）。
- [x] 10.4 已提交的 `tasks.md` 里三处写「按 L-055 实证」，而本分支的 `docs/lessons.md` 最高到 L-054——悬空引用。改为「见 2.1 那一笔」并写明编号在并行分支里、合并时不重编号。
- [x] 10.5 两条 scenario 的 THEN 写在 payload 上（`session/start` 的 `base_url` 为 `https://api.deepseek.com`、请求打到那个地址），mock 侧判不到：seam ⑥ 的判据不能真去连第三方（CI 无网络保证）。分工写明：mock 那一半在 seam ② 判同一个值（`test_the_deepseek_preset_is_the_deepseek_triple` 断言三项全值），payload 与「真打到那个地址」那一半由真实端点那一半判（6.2 的 session `d3e1246e88c84f4b830093db4db05cd8`，payload 就是 `base_url: https://api.deepseek.com`，401 出自 DeepSeek 服务端）。
- [x] 10.6 两轴的判断项与本 change 的流程欠账记进 `docs/adr/0002`（不改代码的那几条：`EffectiveSettings` 端点三项变 `str | None` 把收窄推到调用方、`_ENDPOINT_FIELDS` + 位置 `zip` 把已经成束的三项拆开、`provider_name != "mock"` 与预设表重复表达同一件事、`DEFAULT_PROVIDER_KEY_ENV` 一个常量同时当默认 provider 的触发条件与 openai 预设的变量名、`layer_settings` 的 `env` 参数与 `cli/main.py` 直读 `os.environ` 不同源、`PROVIDER_PRESETS.get(...)` 处理 CLI 已拒掉的名字、`ProviderEndpoint` 只活到 payload）。
- [x] 10.7 实现改动之后重跑变异一轮（10.1 动了 `cli/main.py`），确认四个变异仍被杀、回到基线，并更新 `docs/verification/add-key-driven-default-provider-mutation.md`。**实测**：四个锚点逐条核对仍在（`layering.py:89` / `layering.py:116` / `main.py:379` / `settings.py:48`），基线 **426 passed / 5 skipped**，M1 6 红 / M2 18 红 / M3 2 红 / M4 3 红——**与第一轮逐条相同**，无存活变异，四次还原后 `git status --short -- <file>` 都为空。
