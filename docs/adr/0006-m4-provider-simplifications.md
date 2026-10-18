# M4 真实 Provider 的四处简化，与适配器不继承代理环境变量

M4 接真实模型时，mini 版相对 DSH 故意把 provider 层塌缩成最小形状；其中 `trust_env=False` 是被一次真实故障逼出来的，值得单独记。

1. **一个适配器、非流式、最多一次重试、没有 usage 预算。** DSH 的 provider 层有多模型路由、流式增量、重试策略与用量预算；mini 只有一个 `provider/openai_compat.py`，`generate()` 发一次请求、429 或 5xx 时重试一次，`finish_reason` 只记录不分支（分支看 `tool_calls` 有没有），`Usage` 只落进日志不参与预算判断。重试次数与可重试状态码写死在模块里，不做成参数——「不加没被要求过的可配置性」（编码四规第 2 条）。代价：换协议（Anthropic 原生、流式 SSE）要新写一个适配器而不是改这个；「重试策略」要真正可配置时得重开这块。多模型路由与重试策略本来就在 AGENTS.md 的「明确不做」清单里。
2. **`httpx.AsyncClient(trust_env=False)`：不继承 `HTTP_PROXY` / `NO_PROXY` / netrc。** 起因是实测故障：本机 `NO_PROXY=localhost,127.0.0.1,::1,[::1]`，httpx 默认 `trust_env=True` 在构造客户端时抛 `httpx.InvalidURL: Invalid port: ':1]'`，而它不是 `httpx.HTTPError` 的子类，于是绕过适配器对传输层失败的捕获，直接给用户一个未捕获 traceback——违反不变量 B（失败也是结果）与 F（全程可观测）。被否掉的三个选项：解析并改写 `NO_PROXY`（否：那是把第三方库的解析缺陷吸收进我们的失败语义）；要求用户自己清环境变量（否：故障不在用户那一侧）；把 `InvalidURL` 也捕成 `PROVIDER_TRANSPORT`（否：默认继承代理这件事本身就没被要求过）。**代价：处在公司代理之后的用户无法经代理访问远端端点**，要支持得新开一份 ADR。判据在 `tests/test_cli_provider.py` 的三条 openai 黑盒里——把 `trust_env` 改回 `True` 它们全红。
3. **密钥只走变量名。** CLI 收 `--api-key-env <NAME>`（默认 `DEEPSEEK_API_KEY`），适配器拿的是值、日志与 `session/start.payload` 里只出现名字。代价：不能从配置文件或命令行传密钥，脚本化必须先 export；判据是「日志里搜不到值、搜得到名字」这种可断言的形状（变异 D3 把它守住了）。
4. **验收顺序是先本地端点、后远端。** 人手验收先打 `http://127.0.0.1:8300/v1`（DSH 自己用的端点，单流 FIFO），再打 DeepSeek。理由：本地端点没有网络与计费变量，失败一定是 harness 的失败；远端那一次才用来比对模型行为差异。代价：本地端点只有一个流，真实 smoke 必须短 prompt、小 `--max-turns`、一次一个 session。
5. **决策 22 里的「指数退避」没做。** 429 或 5xx 之后立即重发，不睡。理由：只重试一次时，退避要挡的东西（连续失败下的雪崩）不存在——一次立即重发就是全部策略；加一个 sleep 常量会让 seam ⑤ 的每条重试判据多等那么久，却没有判据能区分「退避 1 秒」与「退避 2 秒」是不是策略。**代价：真实服务端用 `Retry-After` 告诉我们应该等多久时，我们不看它**（本地 8300 与 DeepSeek 的实测回复里都没有这个头）。要支持退避得先决定读不读 `Retry-After`，那是改规格，不是改实现。
6. **`AssistantTurn` 多带一个 `attempts`，扩了决策 20 锁死的形状。** 决策 20 写的是 `AssistantTurn{content, tool_calls, usage, finish_reason}`。重试事实必须随结果回到回合循环才能写成 `model/retry`（provider 不写日志，不变量 A），而成功路径（429 → 200）也要带它，所以它挂在成功结果上而不只是挂在 `ProviderFailure` 上。**代价与守卫**：`AssistantTurn` 同时是 mock fixture 的形状，pydantic 不禁额外字段，于是 fixture 写 `"attempts": [...]` 就能凭空造出一条 `model/retry`；`FixtureProvider` 因此显式剥掉它（tasks 9.2），判据是「fixture 写 attempts 也不出现 `model/retry`」。第二个真实适配器必须自己填 `attempts`，否则它的重试不进日志。

Considered options（第 1 条）：照 DSH 做 provider 注册表 + 路由（否：MVP 不做多模型路由，且没有第二个 provider 之前注册表是空抽象）；用 stdlib `urllib` 省掉 httpx 依赖（人裁决否掉，选了加依赖——理由是 `MockTransport` 让 seam ⑤ 的判据不必真发网络请求）。

覆盖的范围：`src/mini_harness/provider/`、`openspec/changes/m4-real-provider/specs/provider/spec.md` 的「适配器不继承代理环境变量」那条 Requirement。
