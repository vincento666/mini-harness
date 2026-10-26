# Proposal

## Why

`minihns chat` 不带任何档位参数时不能对话。实测（U6 场次，`docs/verification/m5-m6-m7-uat.md`）：裸跑 `minihns chat --workspace <目录>` 退出码 2、stdout 为空、stderr 是 `INVALID_ARGUMENT: --provider mock 需要 --fixture 指向 JSON 数组`。原因在 `loop/settings.py:22-26`：内置默认 `DEFAULT_PROVIDER = "mock"`，而 `DEFAULT_BASE_URL` / `DEFAULT_MODEL` / `DEFAULT_API_KEY_ENV` 三项是 deepseek 的形状——**内置默认里 provider 与端点三项不是同一套**。于是「有密钥就能跑」这条最自然的用法走不通，而 `--help` 里 `--provider` 那行不写默认值，用户看不出错误与真实默认之间差了什么。

第二处：`cli/main.py:241-244` 只接受 `mock` 与 `openai` 两个取值，`--provider deepseek` 当场 `UNKNOWN_PROVIDER`。但 `openai` 预设今天缺 base_url 与 model 时**静默落到 deepseek 的默认**（`DEFAULT_BASE_URL = "https://api.deepseek.com"`、`DEFAULT_MODEL = "deepseek-chat"`）——`--provider openai` 不带 `--base-url` 会打到 deepseek 端点，用 `DEEPSEEK_API_KEY` 认证。这是一颗地雷：provider 名字与它实际连的端点可以不一致。

人的裁决（2026-10-23）：**「不是应该有 `MINIHNS_API_KEY` 就走默认 openai 吗，如果 provider 参数有 deepseek 则走 `DEEPSEEK_API_KEY`」**。

## What Changes

- **provider 词表加一个预设名**：`mock` / `openai` / `deepseek`。`deepseek` 不是新适配器，执行它的仍是 openai 兼容适配器，差别只在预设的三项默认。`UNKNOWN_PROVIDER` 这个词不删（`--provider claude` 仍打它）。
- **默认 provider 由密钥在场决定**：CLI 与配置文件都没给 `provider` 时，`MINIHNS_API_KEY` 已设且非空 → 默认 `openai`；否则 → 默认 `mock`（今天的形状，fixture 驱动测试照旧）。
- **预设表填的是「没被给的那几项」**：`openai` 预设 = `base_url https://api.openai.com/v1`、`api_key_env MINIHNS_API_KEY`、**model 无默认**；`deepseek` 预设 = `https://api.deepseek.com` / `deepseek-chat` / `DEEPSEEK_API_KEY`。CLI 或配置文件给过的那一项不被预设覆盖。
- **地雷拆掉**：`openai` 预设不再落到 deepseek 的默认。缺 model 时当场 `INVALID_ARGUMENT` 并指出 `--model`，不发出任何请求。
- **`--help` 写出默认值**：设置类 flag 的 help 文本写明它当前的默认，`--provider` 那行写明「未给时按 `MINIHNS_API_KEY` 是否在场选 `openai` 或 `mock`」这条规则。

**本 change 明确不做**：不新增 provider 实现（`deepseek` 走既有适配器）；不猜 OpenAI 的模型名；不把 `base_url` / `model` 做成环境变量可配（设置只有内置默认 / 配置文件 / CLI 三层，加第四层会互相矛盾）；不改「密钥只走环境变量、不进日志与配置文件」这条；不改 `session/start` 的 payload 键集（`provider` 那一格的取值多一个词，键不变）；不动 `--fixture` 与 mock 路径；不做多模型路由与重试策略（roadmap 的「始终不做」）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cli`：修改「provider 选择与密钥是装配的必需项」（词表加 `deepseek`、密钥默认变量名随预设）；新增「`--help` 写出设置类 flag 的默认值」。
- `config-layering`：修改「取值优先级是内置默认、配置文件、CLI flag」（内置默认这一层的 `provider` 由密钥在场决定）；新增「provider 预设表填的是没被给的那几项」；修改「端点必需项缺失当场失败」（缺 model 当场失败）。

## Impact

- 代码：`loop/settings.py`（默认值从「四个常量」变成「一张按预设名索引的表 + 一条密钥在场规则」）、`cli/main.py` 的 `_prepare`（provider 解析、端点构造、`--help` 文本）。
- 判据：seam ⑥（真实子进程：裸跑、`--provider deepseek`、`--provider claude`、`--help` 文本）、seam ②（装配：预设覆盖规则、缺 model 的结果）。
- 文档：立 **ADR-0027**（provider 名字是端点预设名，默认 provider 由 `MINIHNS_API_KEY` 在场决定，以及为什么不猜 model）；`AGENTS.md` 技术选型那句「默认 `DEEPSEEK_API_KEY`」要改；`docs/CURRENT.md` 的「裸跑默认档位」那条缺口关闭。
- 兼容性：`--provider openai` 不带 `--base-url` 的既有行为改变（从静默打到 deepseek 变成当场失败）。这是刻意的：那条行为没有判据保护过它。
- 依赖：无新增依赖。
