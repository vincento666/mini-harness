---
status: accepted
---

# provider 名字是端点预设名，默认 provider 由 `MINIHNS_API_KEY` 在场决定

`--provider` 的三个词 `mock` / `openai` / `deepseek` 是**端点预设名**，不是 Provider 实现的类名：
`loop/settings.py` 里 `PROVIDER_PRESETS` 把每个名字映射到 `(base_url, model, api_key_env)` 三项，
`layer_settings` 只用它填 CLI 与配置文件都没给的那几项。在此之前这四个默认住在同一处却属于两套不相关
的东西——provider 默认 `mock`、端点默认 deepseek 那一套——于是 `--provider openai` 不带 `--base-url`
连的是 `https://api.deepseek.com`，而 `--provider deepseek` 这个词根本不存在。默认 provider 现在由
`MINIHNS_API_KEY` 是否已设且非空决定，且**只在内置默认这一层生效**：CLI 或配置文件给了就不看环境。
`openai` 预设**不给 model 默认**，缺它当场 `INVALID_ARGUMENT` 指出 `--model`。

## Considered options

- **默认端点沿用 `DEEPSEEK_API_KEY` 那一套（原状）**：被否。它让「指定 provider」这件事只影响请求头
  里的名字，不影响打到哪儿——这是地雷本身，不是它的文档。
- **默认 provider 写死 `openai`**：被否。裸跑没有密钥就当场失败，CI 没有密钥，「装好就能跑一条」这条
  基线判据（M9 立的）会立刻红。
- **用约定名 `OPENAI_API_KEY`**：被否。这个名字说的是某一家厂商，而它要当的是「本包的默认密钥变量」；
  `MINIHNS_*` 前缀是本包自己的命名空间，`--api-key-env` 早就能指定任意变量名。
- **给 `openai` 预设一个 model 默认**：被否。model 是端点上的东西，本机端点的 model 名不是 openai 的，
  猜一个等于替人做决定（L-056 那一类）。缺它当场失败说清的是「这一项没有默认，给一个」。
- **环境变量当第四层优先级**：被否（design D4）。这一条只填内置默认那一层，配置文件与 CLI 的相对顺序
  一条没动；做成一层会让「谁覆盖谁」多出一件要记的事。

## Consequences

- **`EffectiveSettings` 的端点三项是 `str | None`**：`None` 表示「这一项没有默认」，不是空串。CLI 因此
  必须处理它，缺 model 那条检查排在密钥检查之后——既有判据 `test_a_missing_required_item_leaves_no_log_file`
  与 `test_a_config_supplied_provider_is_checked_the_same_way` 都要求缺密钥先报，规格没规定这两件事的顺序。
- **裸跑仍然不能对话**：这台机器上 `MINIHNS_API_KEY` 平时不在进程环境里（只住在 User 作用域）。要裸跑
  能用，人得自己把变量设上——这是 UAT 的 U1 要人亲手做的事，不是实现能替人做的。
- **默认 provider 随环境变**，所以 `--help` 写的是规则不是运行期值：出现的是三个名字与两个变量名，
  不出现「当前默认是 X」。
- **`AGENTS.md` 技术选型那一行随之改写**（一进一出）：默认变量从「`DEEPSEEK_API_KEY`」改成随 provider
  而定。
- **不新增 Provider 实现**：`deepseek` 走的是 `OpenAICompatProvider`。哪天要接一个不兼容的 API，预设表
  与 Provider 类的对应关系要重新想，届时另开一份 ADR。
