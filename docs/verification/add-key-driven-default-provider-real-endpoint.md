# 真实端点验收（`add-key-driven-default-provider`）

**状态：agent 这一半跑完（2026-10-23 16:16:26–16:16:51，两次真 run）；UAT 那一半等人跑（`add-key-driven-default-provider-uat.md`）。**

跑法：真 PowerShell 终端，真端点是本机的 Strata 服务 `http://127.0.0.1:8300/v1`，model
`qwen3.8-flash-next-iq3_xxs`。密钥按 ADR-0024 的第二半要求走真环境变量：从 User 作用域取
`MINIHNS_STRATA_KEY` 赋给 `MINIHNS_API_KEY`（长度 35，值不打印、不进日志、不进 argv）。工作区与日志在
`.tmp/realB/sessions/` 与 `.tmp/realB/sessions2/`（gitignored）。命令走
`python -m mini_harness.cli.main`，不经 `minihns.exe` 那个 shim（L-057：长 argv 下 shim 自己崩）。

## 场景 A：不给 `--provider` 的裸跑（session `e6250b8560c74198bfe9dd5679ab2493`）

`run -p "用一句话说明你能读这个工作区里的文件吗" --base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs --yes`。
argv 里没有任何 provider 字样。退出码 **0**。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 默认 provider 落到哪 | `openai`（密钥在场） | ✓ `session/start` payload `provider: openai` |
| 端点三项由谁给 | CLI 给的两项是给的，第三项由预设填 | ✓ `base_url: http://127.0.0.1:8300/v1`、`model: qwen3.8-flash-next-iq3_xxs`、`api_key_env: MINIHNS_API_KEY` |
| 会话正常跑完 | 退出码 0、`MODEL_COMPLETED` | ✓ `session/end` 是 `{"stop_reason": "MODEL_COMPLETED", "turns": 2}` |
| 真事办成 | 模型真调了一次工具 | ✓ 记录序列 `model/request → model/response → tool/call → tool/result`，第二轮 `model/response` 无 tool_calls 后停 |
| 密钥不落工件 | 日志里没有密钥值 | ✓ 全文搜 `sk-` 与 `MINIHNS_STRATA_KEY` 都是 False |

这一场是 6.1 的判据本身：**同一个 argv 在 change 之前跑不通**——那时 `--provider openai` 的默认端点是
`https://api.deepseek.com`、默认 model 是 `deepseek-chat`，不给 `--base-url` 就连不到本机端点；不给
`--provider` 则落到 mock 那句 `--fixture`。

## 场景 B：`--provider deepseek` 打的是谁的端点（session `d3e1246e88c84f4b830093db4db05cd8`）

`run -p "说一句你好" --provider deepseek --yes`，argv 里没有 `--base-url`、没有 `--model`、没有
`--api-key-env`。环境里 `MINIHNS_API_KEY` 是本机真密钥、`DEEPSEEK_API_KEY` 是假值
（`sk-fake-shape-check-…`）。退出码 **1**。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 名字进 payload | `provider: deepseek` | ✓ |
| 端点三项跟着名字走 | 预设的三项，不是本机端点 | ✓ `base_url: https://api.deepseek.com`、`model: deepseek-chat`、`api_key_env: DEEPSEEK_API_KEY` |
| 请求真打到那个名字对应的地方 | 回话的是 DeepSeek，不是本机 8300 | ✓ `error/model` 的 `detail` 是 `HTTP 401：Authentication Fails, Your api key: ****0000 is invalid (request_id: e8588213-…)`——这句是 DeepSeek 服务端的话，本机 Strata 不这么说话 |
| 密钥变量也配对 | 用的是 `DEEPSEEK_API_KEY` 那份假值 | ✓ 401 里被掩成 `****0000` 的就是那份假值；`MINIHNS_API_KEY` 那份真密钥没被用 |
| 失败塌成既有形状 | `PROVIDER_HTTP_STATUS` → `PROVIDER_ERROR` → 退出码 1 | ✓ `session/end` 是 `{"stop_reason": "PROVIDER_ERROR", "turns": 1}` |
| 密钥不落工件 | 日志里没有密钥值 | ✓ 全文搜假值前缀与 `MINIHNS_STRATA_KEY` 都是 False |

这一场是「名字与端点一致」的证据：同一个进程环境里两份密钥都在，`--provider deepseek` 用的是 deepseek
那份、打的是 deepseek 那个地址。**它不是**「deepseek 不可用」的证据——它证明的是配对关系；deepseek
真能不能对话要一份真 deepseek 密钥，本机没有。

## 真实那一半没覆盖的地方

- delta 里「deepseek 预设走自己的默认变量」那条 scenario 写的是「请求打到 `https://api.deepseek.com`」，
  场景 B 证到的就是这一句；它**没有**证 deepseek 端点能跑完一个会话（无真密钥）。
- 「有密钥时裸跑的默认 provider 是 openai」在真实端点上证了（场景 A）；「没有密钥时裸跑仍是 mock」只在
  mock 门禁的 seam ⑥ 上证（`test_a_bare_run_without_the_key_still_defaults_to_mock`），真实端点那一半
  不需要它——那条判据的内容与端点无关。
- 密钥驱动默认这一半在本机有一个前提事实：`MINIHNS_API_KEY` 平时**不在**这台机器的环境里（实测进程
  环境里 `MINIHNS_API_KEY` 与 `DEEPSEEK_API_KEY` 都不在，两个变量只住在 User 作用域）。所以「裸跑就能
  对话」要人自己把变量设上——这正是 UAT 的 U1 要人亲手做的那件事。
