# M10 工具管线真实端点验收

**日期**：2026-10-29。**端点**：deepseek（真实 key，不进日志）。**入口**：`minihns chat`。

## 场景

工作区 `.tmp/m10-pipeline-real/ws`：`big.md` 800 行、每行约 100 字符；窗口 70000 / reserve 100。

提示词要求严格按顺序三步，每步只调用一个工具：

1. `read big.md`
2. `write summary.md`（内容 `summary from big`）
3. `read summary.md`

## 观察（session `67558c57834a4bc4afa029f9f6312cc1`）

- `read big.md`：`OK`，结果 6455 字符，带 `(Output capped. Showing lines 1-50. Use offset=51 to continue.)`；**没有 spill 路径**。
- `write summary.md`：`OK`。
- `read summary.md`：`OK`，回读第 1 行 `summary from big`。
- 没有 `bash`，没有并行调用；模型自己确认三步按顺序完成。
- 另一次只读 big.md 的 session（`32a20d27661f41b6a02baf9ba12a686a`）也在 `offset=398` 处 capped，无 spill。

## 结论

- `read` 的 50 KiB/2000 字符/2000 行窗口在真实端点生效，且不写 spill；模型能按 `offset` 续读。
- `write` / `read` 回读成功，工具结果逐条落日志。
- 本样本没有触发 `bash` 16 KiB spill；那一条由 seam ③ 与 UAT 的 bash 场景覆盖。
