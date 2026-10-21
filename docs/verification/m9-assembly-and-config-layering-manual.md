# M9 人手验收（`m9-assembly-and-config-layering`）

**状态：agent 这一半跑完（2026-10-21 15:28–15:35，真 PowerShell 终端，五次 run）；真模型那一半待人跑（见最后一节）。**

跑法：真终端 Windows PowerShell 5.1，真工作区 `.tmp/m9-manual/workspace/`（gitignored），里面是一份真文件 `notes/plan.md` 与真内容。任务是真事——「把 notes/plan.md 重写一遍」，回放 fixture 用仓库里现成的 `tests/fixtures/scenarios/read_then_write/turns.json`（一条 `read` → 一条 `write` → 停）。日志在 `.tmp/m9-manual/workspace/sessions/`。

## 场景 A：没有配置文件（session `78bd2c13dedd450aa389798982588891`）

退出码 0，`notes/plan.md` 真被重写。

| 观察点 | 期望 | 实际 |
|---|---|---|
| `session/start` payload | 内置默认 | ✓ `max_turns: 8`、`window: 128000`、`reserve: 8192`、`sandbox: workspace-write`、`tools` 六项 `read,write,edit,glob,grep,bash` |
| 端点三条 | mock 路径不在 payload | ✓ payload 里没有 `base_url` / `model` / `api_key_env` |
| 真事办成 | 文件内容变了 | ✓ 两行计划 → `重写过的计划` |

## 场景 B：工作区根放着 `mini.config.toml`（session `746a821f71bd410298062049397b0f27`）

配置文件内容三行：`max_turns = 3`、`tools = ["read", "write"]`、`append_system_prompt = "只改 notes 目录。"`。命令行一字没改（跟场景 A 同一份 argv）。退出码 0。

| 观察点 | 期望 | 实际 |
|---|---|---|
| payload 跟着配置换 | `max_turns` 3、`tools` 两项、`append_system_prompt` 那句 | ✓ 三条都换 |
| 白名单走到模型那一侧 | 每条 `model/request` 的 `tools` 只有 `read,write` | ✓ 三条 `model/request` 全是 `read,write` |
| 真事照样办成 | 文件照样重写 | ✓ |

## 场景 C：`--config` 指向工作区外那份（session `ba6804ace11045e4a66969860364221a`）

`--config .tmp/m9-manual/other.toml`，那份写 `max_turns = 5`、`tools = ["read", "write", "edit"]`、`sandbox = "read-only"`。工作区根那份（场景 B 的）还在。退出码 **3**。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 显式路径优先 | 5 而不是 3、三项而不是两项 | ✓ payload `max_turns: 5`、`tools: read,write,edit` |
| 没写的键回落到默认 | `append_system_prompt` 是空串（不是场景 B 那句） | ✓ |
| 配置设的档位真生效 | `read-only` 挡住 `write` | ✓ `tool/result` 是 `OK, DENIED_BY_FENCE`，stderr `SANDBOX_DENIES_WRITE: read-only 档位不许可会改动的操作：notes/plan.md`，退出码 3 |

## 场景 D：缺密钥的 openai run

`--provider openai --base-url http://127.0.0.1:9/v1 --api-key-env MINIHNS_MANUAL_KEY`，该变量未设。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 退出码 | 2 | ✓ 2 |
| stderr | 含 `INVALID_ARGUMENT` 与变量名 | ✓ `INVALID_ARGUMENT: 环境变量 MINIHNS_MANUAL_KEY 未设置或为空：--provider openai 需要密钥` |
| 不建日志 | 目录里文件数不变 | ✓ 7 → 7 |
| 不发请求 | 端点本来就没在监听，照样不是 `PROVIDER_TRANSPORT` | ✓ 报的是参数错误，不是传输错误 |

「设为空串」那一半在 PowerShell 5.1 里造不出来：`$env:X = ""` 是**删除**变量，不是设成空串。所以人手这一半只测了「未设」；空串那一半由 seam ⑥ 的判据覆盖。

## 场景 E：配置里的白名单有未注册的名字

`tools = ["read", "web_search"]`。退出码 2、stderr `INVALID_ARGUMENT: 工具白名单里有未注册的名字：web_search`、目录文件数 7 → 7 ✓。

## 别扭在哪（四条）

1. **带 BOM 的配置文件被判成非法 TOML，报错不提 BOM。** 第一次用 PowerShell 5.1 的 `Set-Content -Encoding UTF8` 写 `mini.config.toml`，run 当场失败：`INVALID_ARGUMENT: …mini.config.toml: Invalid statement (at line 1, column 1)`。原因在文件头三个字节 `EF BB BF`：`tomllib` 不吃 BOM。Windows 上记事本与 PowerShell 5.1 的默认 UTF-8 都带 BOM，所以「在 Windows 上手写一份配置」这条路第一次是断的，而报错把人指向「语法」而不是「编码」。绕法：`[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false))`。要不要在读配置这一层剥掉 BOM，是待人裁决的一条（记进 ADR-0018 的代价，未动实现）。
2. **不给 `--workspace` 时工作区就是进程 cwd，出事之前看不出来。** 第一次 run 忘了切 cwd（在仓库根跑），配置文件在仓库根找不到（这是对的），但工具照跑，并在**仓库根**建出 `notes/plan.md` 与 `sessions/`。`session/start.payload.workspace` 记的是 resolve 之后的 cwd，人要到事后看目录才发现边界在哪儿。已删掉那两个目录（`git status` 干净）。
3. **配置能把档位设成 `read-only`，命令行没有「撤销配置」的开关。** 场景 C 里真 write 被围栏拦下、退出码 3——这是不变量 E 在真 run 里的样子，不是 bug；但第一次遇到时的观感是「工具不让我写」，要回头看 payload 才知道是配置里那行 `sandbox` 干的。命令行优先只意味着「你能用 `--sandbox` 覆盖它」，不意味着「有一条不读配置的跑法」。
4. **六条配置失败码在黑盒里共用 `INVALID_ARGUMENT` 这一个词。** 场景 B 的 BOM、场景 D 的密钥、场景 E 的白名单名，stderr 前缀一模一样，只有后面的文本不同。这也是 6.3 那条判据落在 seam ② 而不是 ⑥ 的原因：`code` 这个事实只在模块层可见。

## 待人跑的那一半（真模型）

需要人在真终端跑，agent 的子进程里没有密钥。命令（端点与密钥沿用 M5 记下的那套）：

```powershell
cd S:\Develop\mini-harness\.tmp\m9-manual\workspace
$env:MINIHNS_STRATA_KEY = "<密钥>"
# 1) 工作区根一份配置：tools 白名单只留 read / write，max_turns = 3
uv run minihns run -p "把 notes/plan.md 重写一遍" --provider openai `
  --base-url http://127.0.0.1:8300/v1 --model qwen3.8-flash-next-iq3_xxs `
  --api-key-env MINIHNS_STRATA_KEY --yes
# 2) 同一份工作区、删掉配置文件，看 payload 回到六工具
# 3) --config 指向另一份、把 sandbox 设成 read-only，看真模型被围栏拦下之后怎么办
```

想看的形状：白名单只剩两条时，真模型会不会改用被筛掉的工具名（那会落成 `UNKNOWN_TOOL`），以及配置设的档位在真模型手里会不会被绕。
