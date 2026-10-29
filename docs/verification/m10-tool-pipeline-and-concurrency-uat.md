# M10 工具管线 / 并发 / 结果预算 UAT

**状态**：等人跑（ADR-0025：这张表没填完，本 change 不得归档、不得合入 `main`）。

**怎么算办一件真事**：不是跑判据，是在一个真实工作区里让模型做「读 → 写 → 读」和多份只读文件，观察并行是否真的更快、改动是不是 barrier、超长结果有没有 spill，以及 runner 不可用时是不是退出码 3。

## 跑之前

- 真实端点：`DEEPSEEK_API_KEY`；工作区 `.tmp/m10-pipeline-uat/ws`。
- 准备：`big.md`（单行 >32 KiB）、`a.md`/`b.md`/`c.md`（各 2000 行）、`run-bash` 场景。
- 起服务或直接用 `minihns chat`；记录 session id 与日志路径。

## U1 · 并行只读批次

提示：`同时用 read 读 a.md、b.md、c.md，再分别总结第一行。`

**预期**：三个 `read` 的 `tool/call` 按声明顺序；`tool/result` 完成顺序可能不同；批次 wall-clock 小于串行三倍；同时最多 8 个在跑。

## U2 · 改动是 barrier

提示：`先读 a.md，再把 a.md 的第一行改成 hello，然后再读一次 a.md。`

**预期**：第一个 read 完成 → write 完成 → 第三个 read 才开始；日志顺序能看出 barrier；写入内容正确。

## U3 · read 字节上限与 spill

提示：`读 big.md 并总结。`

**预期**：结果不超过 32 KiB，带截断 marker 与 `.mini-harness/spill/...` 路径；spill 文件能读回完整内容。

## U4 · bash spill

提示：`用 bash 输出 20000 个 x，然后告诉我输出有多长。`

**预期**：结果带 16 KiB 截断 marker 与 spill 路径；完整输出可从 spill 读回。

## U5 · runner 不可用

用测试桩/注入（不是产品 UI）：让 `CommandRunner` 构造失败，再触发一次 `bash`。

**预期**：`error/fence(code: SANDBOX_UNAVAILABLE)`、退出码 3、命令没有真正执行；不回退到未受限 runner。

## U6 · 真实端点

真实 deepseek 跑一次 U1/U2，记录 wall-clock、token 与最终回答。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| U1 | 并行三 read | 声明顺序 / 完成顺序 / 更快 | | | |
| U2 | read-write-read | barrier 成立 | | | |
| U3 | 读超长文件 | 32 KiB / spill | | | |
| U4 | bash 大输出 | 16 KiB / spill | | | |
| U5 | runner 不可用 | 退出码 3 | | | |
| U6 | 真实端点 | 通过 | | | |

**至少一条「用起来别扭」**：_

**结论**：通过 / 不通过（写清场次、session id、日志）：_
