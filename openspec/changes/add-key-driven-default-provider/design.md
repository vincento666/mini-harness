# Design

## 今天的事实长什么样

`loop/settings.py:22-26` 里四个常量是**两套不相关的东西**：

```
DEFAULT_PROVIDER    = "mock"
DEFAULT_BASE_URL    = "https://api.deepseek.com"
DEFAULT_MODEL       = "deepseek-chat"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
```

provider 的默认是 mock，端点三项的默认是 deepseek。后果有两条，都实测过：

1. 裸跑 `minihns chat` 退出码 2、stdout 空、stderr `INVALID_ARGUMENT: --provider mock 需要 --fixture 指向 JSON 数组`（U6 场次）。一个已经配好密钥的人从这句话里看不出该做什么。
2. `--provider openai` 不带 `--base-url` 时，`cli/main.py:291-298` 用的是 `layered.base_url`，也就是 deepseek 那个默认——provider 名字说 openai，实际连的是 deepseek 端点、用 `DEEPSEEK_API_KEY` 认证。这颗地雷没有任何判据保护过。

## 决策

**D1 provider 名字是「端点预设名」，不是适配器名。** 词表 `mock` / `openai` / `deepseek`；后两个都由既有的 openai 兼容适配器执行，差别只在预设的三项默认。实现里不新增 Provider 类。

- 被否的读法甲：只把 `--provider deepseek` 翻译成「`openai` + `DEEPSEEK_API_KEY`」。它修了报错，没修地雷——provider 名字与实际端点仍然可以不一致。
- 被否的读法乙：加一个 `--preset` 开关。多一个能与 `--provider` 互相矛盾的事实源，且 `--provider` 这个词已经在那儿了。

**D2 默认 provider 由 `MINIHNS_API_KEY` 在场决定，且只在 CLI 与配置文件都没给 `provider` 时生效。** 这是「内置默认」这一层内部的一条规则，不是第四层优先级：给了就用给的。

变量名选 `MINIHNS_API_KEY` 而不是 `OPENAI_API_KEY`：包名 `mini_harness`、命令名 `minihns`，`MINIHNS_*` 是本包自己的命名空间；`OPENAI_API_KEY` 是 OpenAI 官方 SDK 的命名空间，读它等于替别人的工具做决定，而且用户往往已经为别的程序设了它——那种「设过就必须生效」的隐式绑定正是这次要避免的。

**D3 `openai` 预设不给 model 默认（待人裁决，推荐不给）。** 猜一个模型名（`gpt-4o-mini` 之类）会静默打到可能不存在的模型，错误在端点那一侧才暴露，形状是 `PROVIDER_HTTP_STATUS`；当场 `INVALID_ARGUMENT` 指出缺 `--model` 是把错误留在它该在的位置（session 开始之前、没有日志、没有请求）。被否的读法：给一个默认模型名。

同样被否的读法：**缺 model 时退化成 mock**。那会让「明明设了密钥却打不到模型」比今天更难懂。

**D4 不把 `base_url` / `model` 做成环境变量可配。** 设置只有三层（内置默认 / 配置文件 / CLI flag），加第四层会让「哪一层生效」变成四条规则打架，且配置文件已经就是「常驻设置该待的地方」：想让裸跑可用，就把 provider / base_url / model 写进工作区的 `mini.config.toml`。密钥是唯一的例外，因为它不进配置文件（既有判据）。

**D5 `--help` 写规则，不写运行期解析出的值。** help 文本对同一份代码是确定的，判据不依赖环境；写运行期值会让 `--help` 的判据要控制环境变量才能断言。

**D6 兼容性：`--provider openai` 不带 `--base-url` 的行为改变是刻意的。** 今天它静默打到 `https://api.deepseek.com`；没有任何判据断言过这个行为，拆它不是破坏既有契约。

## 测试策略

- **seam ⑥（CLI 黑盒，真实子进程）**：裸跑（有 / 无 `MINIHNS_API_KEY` 两种环境）、`--provider deepseek`、`--provider claude` 仍打 `UNKNOWN_PROVIDER`、`--help` 文本含四个词、`--provider openai` 缺 model 的退出码与 stderr。
- **seam ②（装配与配置）**：预设覆盖规则（CLI 给过的那项不被覆盖、配置文件给过的也不被覆盖）、`session/start` payload 里 `provider` 与端点三项的配对、mock 路径没有端点三项。
- 词表守卫 `tests/test_vocabulary_reachability.py`：`UNKNOWN_PROVIDER` 仍可达（`--provider claude`）；不新增 `code`。
- 环境隔离：判据 MUST NOT 读真密钥。跑子进程时显式构造环境（`env=` 传一份只含假值的字典），MUST NOT 继承本机 User 作用域里的真实密钥。

## 已知代价

- 裸跑仍然不能对话（缺 model 或没有配置文件时）：本 change 修的是「默认说得清」与「名字与端点一致」，不是「零配置可用」。零配置可用需要一份用户级配置文件，那是另一件事。
- 默认 provider 随环境变，意味着同一份命令行在不同机器上可能跑不同 provider。缓解：`session/start` 的 payload 写生效值，日志里看得见；`--help` 写明规则。
