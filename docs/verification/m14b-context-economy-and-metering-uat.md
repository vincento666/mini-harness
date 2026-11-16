# m14b-context-economy-and-metering UAT

**状态**：agent 代跑（用户指示，2026-11-16）。四场。环境 `--provider deepseek`（`deepseek-chat`），工作区 `.tmp/uat/m14b`，价目表用测试值 `input = 1.0`、`output = 2.0`。

## 场次

| 场次 | 动作 | 预期 |
|---|---|---|
| S1 | 让模型 `grep` 一个命中上千行的文件（结果超过 8192 码点） | 日志里的结果有头、剪枝标记、尾与相对路径；`read` 那个路径能看到全文。**不用 `read` 造场景**：`read` 已豁免剪枝 |
| S2 | 让模型原样跑 `seq 1 20000`（不接管道），产生大输出 | bash 仍是尾部保留 + 原有 spill 标记，不走头尾剪枝 |
| S3 | 对 S1 的会话执行 `minihns usage <id> --config …` | JSON 里 `turns` 与 `total` 的四桶与日志里的 `usage` 对得上 |
| S4 | 去掉 `--config` 再跑一次 `usage` | `cost` 是 `null`，不出现猜测的金额 |

## 观察表

| 场次 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|
| S1 | 第一次让模型「grep 文件」，它把 `path` 指到文件，工具以 `NOT_A_DIRECTORY` 拒绝，随后改用 bash 的小结果——没触发剪枝。第二次显式给 `pattern=needle, path=.`：结果 11304 码点被剪，`pruned = {chars: 11304, digest: 976768…, spill: .mini-harness/spill/grep-976768ae06b294ac.txt}`，标记在，模型引用了 spill 路径 | 通过 | 工具只接受目录作为搜索根，模型第一次会误用；这是工具契约的既有形状，不是剪枝的问题 |
| S2 | 第一次被模型用 `tail -n 1` 规避（输出只有一行）；显式要求「不要接管道」后：结果 16463 码点，**没有**剪枝标记，带 `[output truncated; full output: .mini-harness/spill/bash-ac646a88e7f991ef.txt]`，尾部能看到 20000 | 通过 | 模型会主动规避大输出；人跑时若想复现，需要在指令里排除管道 |
| S3 | `total = {input_uncached: 1967, cache_read: 2944, cache_write: 0, output: 226}`，与日志逐项相等；`cost = 0.002419`，等于 `(1967×1 + 226×2) / 1e6` | 通过 | 无 |
| S4 | `cost` 为 `null` | 通过 | 无 |

**结论**：通过。

## 附：人跑时可留意

- S1 的 `1012 行` 是模型自己的表述：工具实际只列出前 250 条并剪枝，模型把「spill 里还有」说成了总数。剪枝本身没丢信息（spill 有全文），但模型可能把「看到的条数」当「总数」——值得在提示里要求它区分。
- S2 说明「让模型产生大输出」本身需要指令约束，否则它会自己先 `tail` 掉。
