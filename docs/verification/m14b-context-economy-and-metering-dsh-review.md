# m14b-context-economy-and-metering 对齐复核

**日期**：2026-11-16。对齐对象：proposal / design / 两份 spec 增量（4 条 Requirement、12 个 Scenario）/ tasks 验收 + DSH 十项。DSH 出处为官方一手资料（`deepseek-ai/deepseek-harness` 提交 `47f9438`），核对过程见 `docs/reference/context-economy.md`。

## 提案

| 对照点 | 实现 | 结论 |
|---|---|---|
| Why：只有 bash 有兜底、没有计量 | 通用剪枝 + spill + 四桶 + 成本 | aligned |
| What Changes：剪枝、spill 不回收、`usage`、价目表 | 全部落地 | aligned |
| 非目标：`/usage` 命令、按工具阈值、自动回收、bash 改动 | 未做；bash 保持原策略 | aligned |
| Impact：`dispatch` / 新 `metering` / `turn_loop` / CLI | 一致，另加 `tools/retention.py` | aligned |

## 设计

| 决策 | 实现 | 结论 |
|---|---|---|
| D0 不用 `surfaceOp` | 剪枝在写日志前，原文进 spill + `pruned.digest` | aligned（理由与触发条件写在 design） |
| D1 位置与范围 | dispatch 收尾；非 bash、非 read | aligned |
| D2 spill 与读回 | 相对路径 + 取回指引；失败记 `pruned.error` | aligned |
| D3 不自动回收 | 代码不删；文档给清理命令 | aligned |
| D4 计量是日志纯函数 | `metering.collect_usage`，不写新事件 | aligned |
| D5 成本配置驱动 | `[pricing.<model>]`，缺省 null | aligned |
| D6 报告面 `minihns usage` | JSON 三键，不改日志 | aligned |

## 规格（12 个 Scenario）

| Scenario | 判据 | 结论 |
|---|---|---|
| 超大结果被剪短且给出去向 | `test_a_long_result_is_pruned_and_spilled` | aligned |
| 剪枝留下可核对的凭据 | `test_the_payload_carries_pruned_metadata` | aligned |
| 未超阈值不动 | `test_a_short_result_is_untouched`、`test_the_threshold_is_inclusive` | aligned |
| 剪枝是幂等的 | `test_pruning_is_idempotent` | aligned |
| `read` 不受影响 | `test_read_is_not_pruned` + 既有 `test_file_read` | aligned |
| bash 不受影响 | `test_bash_keeps_its_own_tail_policy` | aligned |
| spill 写失败保留内联 | `test_a_spill_failure_keeps_the_inline_result` | aligned |
| 回放不读 spill | `test_replay_rebuilds_contract_messages_without_touching_disk` 同族的 replay 判据 + 剪枝在写日志前 | aligned |
| 四桶求和 | `test_four_buckets_are_summed` | aligned |
| reasoning 不加两次 | `test_reasoning_is_not_added_twice` | aligned |
| 缺 usage 跳过 | `test_a_turn_without_usage_is_skipped` | aligned |
| 有/无价目表 | `test_the_usage_command_computes_cost_from_config`、`test_pricing_is_none_without_a_table` | aligned |
| 输出可被 E1 消费 | `test_the_usage_command_prints_turns_and_total` | aligned（E1 本体未实现，见 deferred） |

## tasks 验收

1.1–3.2、4.1、4.3、4.4 完成；**4.2 UAT 未跑**（deferred，触发条件：人坐终端跑四场）。E1 报告列 deferred，触发条件：`scripts/eval/` 有 runner 后消费 `minihns usage` 的 JSON。

## DSH 十项

| # | 项 | 结论 | 记账 |
|---|---|---|---|
| 1 | 形状 | simplified | DSH 剪枝是替换事件 + `surfaceOp`；mini 在写日志前改写（D0 有理由） |
| 2 | 机制 | simplified | DSH 在压缩触发时剪；mini 在 dispatch 收尾剪 |
| 3 | 语义 | aligned | 码点阈值、头+标记+尾、幂等、spill 失败保留内联 |
| 4 | 不变量 | aligned | 日志仍是唯一真源；`pruned.digest` 提供可核对凭据 |
| 5 | 面 | simplified | 模型面与日志面有；`/usage` 命令延后 |
| 6 | 失败与降级 | aligned | spill 失败保留内联；缺价目表 `null` 不猜 |
| 7 | 组合与扩展 | simplified | 只有一层通用剪枝；bash/read 各自保留策略 |
| 8 | 资源与约束 | aligned | 8192 码点 / 单文件 1 MiB 读前上限 / spill 不回收 |
| 9 | 信任与授权 | aligned | spill 写在工作区内、相对路径、越界拒绝 |
| 10 | 回放与确定性 | aligned | 剪枝在写日志前；回放不读 spill |

## 结论

提案、设计、规格逐条兑现；十项里 6 aligned、4 simplified（形状、机制、面、组合），都有理由与触发条件。未完成项只有 UAT 四场。
