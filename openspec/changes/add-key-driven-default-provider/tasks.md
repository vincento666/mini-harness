# Tasks

## 1. 预设表这一处事实（seam ②）

- [x] 1.1 红：写判据——生效 provider 为 `openai` 且未给端点三项时，装配出的端点是 `https://api.openai.com/v1` / 无 model / `MINIHNS_API_KEY`；为 `deepseek` 时是 `https://api.deepseek.com` / `deepseek-chat` / `DEEPSEEK_API_KEY`；为 `mock` 时没有端点对象。确认它红（今天 openai 落到 deepseek 的默认）。**实测红**：`tests/test_config_presets.py::test_the_openai_preset_is_openai_not_deepseek` 红在 `assert 'https://api.deepseek.com' == 'https://api.openai.com/v1'`，`test_the_mock_preset_has_no_endpoint` 红在 `assert 'https://api.deepseek.com' is None`；`test_the_deepseek_preset_is_the_deepseek_triple` 当时就绿——今天那四个默认恰好就是 deepseek 那一套，这条判据的作用是不让它再当所有人的默认。
- [x] 1.2 绿：把 `loop/settings.py` 的四个常量换成按 provider 名索引的预设表（`model` 在 `openai` 预设里是 `None`），1.1 变绿且 `uv run mypy --strict src` 无新错。**实测**：`PROVIDER_NAMES` + `ProviderPreset` + `PROVIDER_PRESETS` 三条；`EffectiveSettings` 的端点三项改成 `str | None`（`None` 是「这一项没有默认」，不是空串），`layer_settings` 里 `provider` 与端点三项从 `BUILTIN_DEFAULTS` 挪出来单独算；`cli/main.py` 因此必须处理 `None`——缺 model 当场 `INVALID_ARGUMENT` 指出 `--model`（组 4 的规则提前落地，见 4.1 那一笔）。
- [x] 1.3 红：写覆盖规则判据——CLI 给过 `--base-url` 时预设不覆盖它、配置文件给过 `model` 时预设也不覆盖它、两者都没给时预设填上。确认它红或确认它已绿（若已绿，用变异确认它咬得住，并记在这里）。**实测：三条落地即绿**（1.2 已把覆盖规则写进 `layer_settings`），红不是当场踩的；它咬不咬得住由组 8 的变异 ②「预设总是覆盖」判，结果记在 `docs/verification/add-key-driven-default-provider-mutation.md`。

## 2. 默认 provider 由密钥在场决定（seam ② 与 ⑥）

- [ ] 2.1 红：写判据——CLI 与配置文件都没给 `provider` 时，`MINIHNS_API_KEY` 已设且非空 → 生效 provider 为 `openai`；未设或为空串 → 生效 provider 为 `mock`。判据显式构造子进程环境，MUST NOT 继承本机真实密钥。确认它红。
- [ ] 2.2 绿：实现这一条内置默认规则，2.1 变绿；既有的「配置文件覆盖内置默认」「命令行覆盖配置文件」「与默认同值的命令行开关仍是显式值」三条判据全部仍绿。
- [ ] 2.3 红：写「配置文件写 `provider = "openai"` 时不看密钥在场」的判据（该变量未设 → 退出码 2、`INVALID_ARGUMENT` 与变量名）。确认它红。

## 3. 词表加 `deepseek`，地雷拆掉（seam ⑥）

- [ ] 3.1 红：`minihns run -p "x" --provider deepseek`（`DEEPSEEK_API_KEY` 在假环境里已设、base_url 用 loopback 假 server）→ 退出码 0、`session/start` 的 payload 里 `provider` 为 `deepseek`、请求打到预设地址。确认它红（今天 `UNKNOWN_PROVIDER`）。
- [ ] 3.2 红：`--provider claude` 仍打 `UNKNOWN_PROVIDER`、退出码 2、没有 session 日志。确认它已绿，并用变异确认它咬得住。
- [ ] 3.3 红：`--provider openai` 不带 `--base-url` 时装配出的端点是 `https://api.openai.com/v1`（黑盒里用 `--dry-run` 类判据不可用，改为断言 stderr 里缺 `--model` 的那条 `INVALID_ARGUMENT` 与日志未创建）。确认它红。
- [ ] 3.4 绿：实现词表与端点构造，3.1 与 3.3 变绿；既有的「未知 provider」「密钥变量未设」「密钥只进请求头」三条判据仍绿。

## 4. 缺 model 当场失败（seam ② 与 ⑥）

- [ ] 4.1 红：`--provider openai --api-key-env <已设的假变量>` 且未给 `--model` → 退出码 2、stderr 含 `INVALID_ARGUMENT` 与 `--model`、session 目录里没有新文件、假 server 没收到任何请求。确认它红。
- [ ] 4.2 绿：实现这一条，4.1 变绿；`--provider deepseek` 不带 `--model` 仍成功（预设给了）。

## 5. `--help` 写出默认值（seam ⑥）

- [ ] 5.1 红：`minihns chat --help`、`minihns run --help`、`minihns serve --help` 的 `--provider` 说明里同时含 `mock`、`openai`、`deepseek`、`MINIHNS_API_KEY`；`--api-key-env` 说明里含两个变量名；输出里不含任何假密钥的值。确认它红。
- [ ] 5.2 绿：实现 help 文本（写规则不写运行期值），5.1 变绿。
- [ ] 5.3 跑 `tests/test_vocabulary_reachability.py` 确认 `UNKNOWN_PROVIDER` 仍可达、没有新增 `code`。
- [ ] 5.4 跑 `openspec validate --all --strict` 确认两份 delta 结构合法（ADDED 2、MODIFIED 3，被改的每条保留全部既有 scenario 名）。

## 6. 真实端点验收（完成判据的第二半，ADR-0024）

- [ ] 6.1 本机 Strata：`MINIHNS_API_KEY` 设成端点密钥、`--base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs`，**不给 `--provider`** → 确认默认落到 openai 且会话正常跑完。
- [ ] 6.2 同一端点跑 `--provider deepseek` 的失败形状：确认它打的是 `https://api.deepseek.com` 而不是本机端点（看 `error/model` 的 `detail`），并确认这条失败是「名字与端点一致」的证据。
- [ ] 6.3 观察记进 `docs/verification/add-key-driven-default-provider-real-endpoint.md`。

## 7. UAT 验收（完成判据的第三半，ADR-0025，人跑）

- [ ] 7.1 手册骨架已立：`docs/verification/add-key-driven-default-provider-uat.md`（三场：裸跑现在说什么 / `--provider deepseek` 能对话 / `--help` 看得见默认）。
- [ ] 7.2 等人跑完那三场并填回观察表；**表没填完本 change 不得归档、不得合入 `main`**。

## 8. 变异测试一轮

- [ ] 8.1 四条变异跑全量并记进 `docs/verification/add-key-driven-default-provider-mutation.md`：① 预设表里 `openai` 的 `api_key_env` 改回 `DEEPSEEK_API_KEY`；② 覆盖规则改成「预设总是覆盖」；③ 密钥在场规则改成「总是 mock」；④ 缺 model 的检查删掉。每条必须被至少一条测试杀死。

## 9. Learning Gate

- [ ] 9.1 扫本轮证据写进 `docs/lessons.md` 收件箱；**收件箱已到上限 15 条，先消化再收新条**。
- [ ] 9.2 立 ADR-0027（provider 名字是端点预设名、默认 provider 由 `MINIHNS_API_KEY` 在场决定、为什么不猜 model），并改 `AGENTS.md` 技术选型里「默认 `DEEPSEEK_API_KEY`」那半句（一进一出）。
