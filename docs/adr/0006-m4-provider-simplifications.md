# M4 真实 Provider 的四处简化，与适配器不继承代理环境变量

M4 接真实模型时，mini 版相对 DSH 故意把 provider 层塌缩成最小形状；其中 `trust_env=False` 是被一次真实故障逼出来的，值得单独记。

1. **一个适配器、非流式、最多一次重试、没有 usage 预算。** DSH 的 provider 层有多模型路由、流式增量、重试策略与用量预算；mini 只有一个 `provider/openai_compat.py`，`generate()` 发一次请求、429 或 5xx 时重试一次，`finish_reason` 只记录不分支（分支看 `tool_calls` 有没有），`Usage` 只落进日志不参与预算判断。重试次数与可重试状态码写死在模块里，不做成参数——「不加没被要求过的可配置性」（编码四规第 2 条）。代价：换协议（Anthropic 原生、流式 SSE）要新写一个适配器而不是改这个；「重试策略」要真正可配置时得重开这块。多模型路由与重试策略本来就在 AGENTS.md 的「明确不做」清单里。
2. **`httpx.AsyncClient(trust_env=False)`：不继承 `HTTP_PROXY` / `NO_PROXY` / netrc。** 起因是实测故障：本机 `NO_PROXY=localhost,127.0.0.1,::1,[::1]`，httpx 默认 `trust_env=True` 在构造客户端时抛 `httpx.InvalidURL: Invalid port: ':1]'`，而它不是 `httpx.HTTPError` 的子类，于是绕过适配器对传输层失败的捕获，直接给用户一个未捕获 traceback——违反不变量 B（失败也是结果）与 F（全程可观测）。被否掉的三个选项：解析并改写 `NO_PROXY`（否：那是把第三方库的解析缺陷吸收进我们的失败语义）；要求用户自己清环境变量（否：故障不在用户那一侧）；把 `InvalidURL` 也捕成 `PROVIDER_TRANSPORT`（否：默认继承代理这件事本身就没被要求过）。**代价：处在公司代理之后的用户无法经代理访问远端端点**，要支持得新开一份 ADR。判据在 `tests/test_cli_provider.py` 的三条 openai 黑盒里——把 `trust_env` 改回 `True` 它们全红。
3. **密钥只走变量名。** CLI 收 `--api-key-env <NAME>`（默认 `DEEPSEEK_API_KEY`），适配器拿的是值、日志与 `session/start.payload` 里只出现名字。代价：不能从配置文件或命令行传密钥，脚本化必须先 export；判据是「日志里搜不到值、搜得到名字」这种可断言的形状（变异 D3 把它守住了）。
4. **验收顺序是先本地端点、后远端。** 人手验收先打 `http://127.0.0.1:8300/v1`（DSH 自己用的端点，单流 FIFO），再打 DeepSeek。理由：本地端点没有网络与计费变量，失败一定是 harness 的失败；远端那一次才用来比对模型行为差异。代价：本地端点只有一个流，真实 smoke 必须短 prompt、小 `--max-turns`、一次一个 session。

Considered options（第 1 条）：照 DSH 做 provider 注册表 + 路由（否：MVP 不做多模型路由，且没有第二个 provider 之前注册表是空抽象）；用 stdlib `urllib` 省掉 httpx 依赖（人裁决否掉，选了加依赖——理由是 `MockTransport` 让 seam ⑤ 的判据不必真发网络请求）。

覆盖的范围：`src/mini_harness/provider/`、`openspec/changes/m4-real-provider/specs/provider/spec.md` 的「适配器不继承代理环境变量」那条 Requirement。
