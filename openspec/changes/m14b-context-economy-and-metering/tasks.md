# Tasks

## 1. 剪枝与 spill（seam ②）

- [ ] 1.1 `tools/dispatch.py` 收尾：非 bash 纯文本按码点剪枝（8192 / 4096 / 1024 + 标记），幂等
- [ ] 1.2 全文写 `<workspace>/.mini-harness/spill/<tool>-<digest16>.txt`，结果留相对路径与取回指引；越界拒绝；payload 记 `pruned: {chars, digest, spill}`
- [ ] 1.3 spill 写失败保留内联，追加 `spill/failed` 事件（工具名 + 原因）

## 2. 计量（seam ①④）

- [ ] 2.1 `metering.py`：从 `model/response.usage` 聚合四桶，按 `(turn, step)` 后者胜，reasoning 不重复加
- [ ] 2.2 缺 `usage` 的回合跳过；会话总量是求和

## 3. 成本与命令（seam ⑥）

- [ ] 3.1 配置 `[pricing.<model>]` 四类单价（每百万 token）；缺省为 `null`
- [ ] 3.2 `minihns usage <session-id>` 输出 `turns` / `total` / `cost` 的 JSON，不改日志

## 4. 收尾

- [ ] 4.1 真实端点：一次含工具调用的 run，`usage` 的四桶与 provider 报的对得上
- [ ] 4.2 UAT（人跑，场次见 `docs/verification/m14b-context-economy-and-metering-uat.md`）
- [ ] 4.3 变异测试一轮
- [ ] 4.4 Learning Gate
