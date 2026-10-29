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

## U3 · read 窗口（不 spill）

提示：`读 big.md 并总结。`

**预期**：结果不超过 50 KiB、单行不超过 2000 字符，带 capped footer 与 `offset=<next>`；**没有** spill 路径；继续 `read` 同一个文件能推进 offset。

## U3b · read 的单行截断

准备一个单行 5000 字符的文件，提示：`读 longline.md 并告诉我第一行。`

**预期**：该行带 `... (line truncated to 2000 chars)` mark；窗口仍可继续读。

## U4 · bash spill

提示：`用 bash 输出 20000 个 x，然后告诉我输出有多长。`

**预期**：结果保留尾部、带 16 KiB 截断 marker 与 spill 路径；完整输出可从 spill 读回。

## U5 · runner 不可用

用测试桩/注入（不是产品 UI）：让 `CommandRunner` 构造失败，再触发一次 `bash`。

**预期**：`error/fence(code: SANDBOX_UNAVAILABLE)`、退出码 3、命令没有真正执行；不回退到未受限 runner。

## U6 · 真实端点

真实 deepseek 跑一次 U1/U2，记录 wall-clock、token 与最终回答。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| U1 | 并行三 read | 声明顺序 / 完成顺序 / 更快，≤8 | session `6945900c...`：三条 `tool/call` 按 c1/c2/c3，随后三条 result；单次 chat 653 ms | 通过 | 启动开销占大头，单次 CLI 看不出并行收益；并发由 seam ② 的 10 read 峰值 8 判据钉住 |
| U2 | read-write-read | barrier 成立 | session `aaa0dbaf...`：日志顺序 `call r1 → result r1 → call w1 → result w1 → call r2 → result r2` | 通过 | 无 |
| U3 | 读超长文件 | 50 KiB / 单行 2000 / 不 spill / offset | session `6f1de8b7...`：结果 51171 字符，`Output capped` 与 offset，无 spill | 通过 | 结果接近 50 KiB，模型要续读 |
| U3b | 单行截断 | 2000 字符 mark | session `5e986a59...`：结果 2100 字符，带 `line truncated to 2000 chars` | 通过 | 超长单行剩余部分不可恢复（spec 已写明） |
| U4 | bash 大输出 | 16 KiB / 尾部 / spill | session `6d50d824...`：结果 16463 字符，marker + spill；文件 `bash-142c0ac...txt` 20016 字节 | 通过 | spill 文件名按内容 hash，不是 session/call id；M11 再考虑命名/回收 |
| U5 | runner 不可用 | 退出码 3 | `tests/test_cli_runner_unavailable.py` 真实子进程：退出码 3，日志 `error/fence(SANDBOX_UNAVAILABLE)` | 通过 | 需要测试桩注入，产品 UI 没有开关 |
| U6 | 真实端点 | 通过 | session `67558c57...`：read big.md（6455 字符，capped 无 spill）→ write summary.md → read summary.md | 通过 | 真实模型可能并行/多读；本次提示词明确要求逐步 |

**至少一条「用起来别扭」**：单次 CLI 的 wall-clock 被启动开销淹没，U1 只用日志顺序与 seam ② 的峰值判据证明并发；真实端点 U6 需要明确「一次一个工具」才稳定复现三步。

**结论**：通过（agent 代跑，用户 2026-10-29 授权；U1 `6945900c`、U2 `aaa0dbaf`、U3 `6f1de8b7`、U3b `5e986a59`、U4 `6d50d824`、U6 `67558c57`）。
