# 真实端点验收：`add-platform-facts-to-protected-header`（tasks 6.1）

**场景**：接真实端点（DeepSeek）跑一次 `chat`，看模型拿到的头部里有没有那块运行环境，以及它列目录时选什么。

## 跑法

```powershell
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY","User")
# 工作区 .tmp\real-platform 里放 a.md / b.md 两个文件
"看看这个目录里有什么，用一句话回答。`n" | uv run minihns chat --provider openai `
  --base-url https://api.deepseek.com/v1 --model deepseek-flash --api-key-env DEEPSEEK_API_KEY `
  --workspace .tmp\real-platform --session-dir .tmp\real-platform\sessions --max-turns 3 --yes
```

会话 `4d05e370b49247e596c566a3abc917ec`，退出码 0，`session/end` 是 `MODEL_COMPLETED`、turns=2。

## 模型实际拿到的头部（第一条 `context/assembled` 的 system 消息，逐字）

```
你是 mini-harness 的 agent。在回合里先装配上下文，再调用工具或回答；工具失败也是结果，不是异常。

可用工具：
read
write
edit
glob
grep
bash

运行环境：os=nt，bash 经 cmd.exe /c 执行。列目录用 dir、搜内容用 findstr、看文件用 Get-Content；不要用 ls / grep / cat。命令输出按 UTF-8 解码，不是合法 UTF-8 的字节会显示为替换字符。
```

三块都在预期的位置：内置常量 → 工具块 → 运行环境块。

## 观察

- **平台事实到位**：`os=nt`、`cmd.exe /c` 都在，且这句建议是从日志里的 `platform` 推出来的（判据见 seam ④）。
- **第一次调用就用了 `dir`**：`bash {"command": "dir"}`。对比 2026-10-24 那次 UAT——模型先跑 `ls`、失败、再在屏幕上写「这是一台 Windows shell」，这次一次成功，没有试错正文。
- **它没有用 `glob`**：虽然工具描述里写着「要列目录就用 glob」，它仍选了 `bash` + `dir`。头部那句建议（「列目录用 dir」）与描述那句引导（「列目录用 glob」）在同一次装配里同时出现，模型挑了前者——**这是本项目第一次看见这两句在同一个头部里竞争**。
- 回答里报了两个 `10 字节` 的文件与 `sessions` 子目录：`dir` 的输出给到的信息，没有依赖任何猜测。

## 对这一条的三条判读（留给人裁）

1. 本 change 的判据是「模型收到的头部里有这两个事实与本平台建议」——**已通过**，UAT 那一半才会判「它实际怎么做」。
2. 「用 `dir` 而不是 `glob`」说明 ADR-0030 的引导软于 ADR-0029 的建议：一边说「列目录用 dir」，另一边说「列目录用 glob」。两种做法都不错（都一次成功、都不试错），但**如果要让原生工具优先**，头部那句应该改成「列目录用 glob（要跑 shell 命令时这个平台上用 dir）」这类把两层摆清的说法。
3. 这条不改本 change 的规格与判据，记在这里供 UAT 那一半一起裁。

## 门禁

真实端点验收不进 CI，也不替代四道门禁；它判的是「连上真东西之后形状还对」。这次连着四道门禁都绿（见提交信息）。
