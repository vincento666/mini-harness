# m14b-context-economy-and-metering 代码审查（两轴）

**日期**：2026-11-16。范围：`change/m14b-context-economy-and-metering` 的全部提交。两轴：Standards 与 Spec。

## Standards

| # | 发现 | 处置 |
|---|---|---|
| C1 | `_bounded` 用逐字符缩尾的循环来卡总长；最坏要走几千次 | 记账：预算固定、文本上限 8192，实际循环次数很小；若将来把阈值调大再改成一次性算余量 |
| C2 | `usage` 命令用 `discover_config(Path.cwd())`，配置**存在但非法**时静默返回 `cost: null` | 记账：当前把「没配置」与「配置坏了」合并成同一个结果，代价是排错时看不出区别；触发条件：出现按成本做门控的需求时改成显式失败码 |
| C3 | `_finalize_content` 里两个 `from ... import` 是函数内导入 | 接受：沿用 bash 分支的既有写法，避免 dispatch 顶层引入工具模块造成环 |
| C4 | `pruned.digest` 只覆盖全文、不覆盖工具名与路径 | 接受：digest 的用途是核对 spill 文件，路径已在 `pruned.spill` 里单列 |

## Spec

| # | 对照点 | 结论 |
|---|---|---|
| S1 | 剪枝阈值/头尾/标记/幂等 | 判据齐全；边界（8192 恰好在阈值上）已单独钉住 |
| S2 | `read` 与 `bash` 不走通用剪枝 | `read` 由既有 `test_file_read` 两条判据 + `test_read_is_not_pruned` 守；bash 由 `test_bash_keeps_its_own_tail_policy` 守 |
| S3 | spill 失败保留内联 | `test_a_spill_failure_keeps_the_inline_result` |
| S4 | 四桶、reasoning、缺 usage、同回合后者胜、成本 null、usage JSON | 各自有判据；真实端点另核过一次 |
| S5 | E1 报告列 | deferred：E1 只有 README、无 runner；本 change 交 `minihns usage` 的 JSON 作数据源 |

## 结论

无阻塞项：一处记账（C1）、三处接受（C2–C4）；Spec 侧除 E1 列外全部兑现。
