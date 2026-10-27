# P0 预算读数诊断（2026-10-27）

**目的**：在 `main`（`794536d`，含 dead-zone + H1）上按 `fix-post-compaction-budget-reading` UAT 的 W1/W2 形状跑一次真实 deepseek 端点，判断那条「遮蔽之后 tokens 后 > 前 / 每问必溢出」是否仍能复现。**这是诊断，不是 UAT 验收。**

## 跑法

- 工作区 `.tmp/p0-diag`：`big1.md` / `big2.md` / `big3.md` 各 151,203 字节（1200 行，纯填充文本）。
- W1：`--window 70000 --reserve 100 --max-turns 8 --sandbox workspace-write --yes`，两次输入，各读一份并总结。
- W2：同窗口、`--max-turns 6`，三次读取 + 三句追问。
- 真实端点 `provider=deepseek`；密钥只从用户环境变量注入子进程。
- 输出：`.tmp/p0-diag/w1.out.txt`、`w2.out.txt`；日志在 `.tmp/p0-diag/sessions-w1/`、`sessions-w2/`。

## W1 观察

```text
[遮蔽] 折掉 seq 1 至 24：tokens 13255 降至 192
[遮蔽] 折掉 seq 30 至 36：tokens 13264 降至 397
[遮蔽] 折掉 seq 42 至 63：tokens 13951 降至 564
[遮蔽] 折掉 seq 69 至 73：tokens 26664 降至 702
```

- 四条 `compaction/summary` 全部 **`tokens_after < tokens_before`**，没有出现 `70485 降至 71030` 那种倒挂。
- 两次段都以 `MODEL_COMPLETED` 收尾，没有 `[段] CONTEXT_WINDOW_EXCEEDED`。
- 结论：**W1 形状在当前 main 上没有复现 P0。**

## W2 观察

- 模型没有按指令用 `read` 读完 1200 行，只抽读了开头/结尾，并用 `bash` 核对行数与哈希；因此上下文始终没到压力预算。
- 日志里最大 `usage.input_tokens` 是 **8658**，压力预算 `70000 - 100 = 69900`；没有 `compaction/summary`，也没有 `CONTEXT_WINDOW_EXCEEDED`。
- 结论：**W2 没有触发溢出，无法验证「溢出之后还问得动吗」；本次 W2 是无效样本，不是 P0 通过。**

## 判断

- 代码路径仍在：`context/budget.py::budget_reading` 没有「只看最后一条 `compaction/summary` 之后」的 seq 界；dist 的 `model/response` 回报理论上仍可能钉住压缩后的读数。
- 但当前 main 的**用户可见症状没有复现**：W1 四次遮蔽都下降，W2 根本没到溢出。dead-zone 把溢出判据换成 `W − O` 之后，旧 proposal 里「每问必溢出」的强度可能已不成立。
- 因此：**不要把 P0 的 20 个 task 原样 apply**。要么先做一次能稳定触发溢出的受控真实端点复现，要么把 P0 降级为「未复现的历史缺陷」，不要为旧 proposal 付全量成本。
- 如果后续要修，最小改动仍是 `budget_reading` 的 seq 界 + 少量判据；但需要先有当前 main 上的真实失败样本。

**本诊断不改变 P0 的 tasks 状态**：`change/fix-post-compaction-budget-reading` 仍是 20/20 未勾、未实现、未归档。
