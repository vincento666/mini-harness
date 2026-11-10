# subagent-preset 变异测试

**日期**：2026-11-10。每个变异改源码、跑指定判据、记录红，再 `git checkout` 还原并复查基线。

| # | 变异 | 改法 | 杀死的判据 | 结果 |
|---|---|---|---|---|
| M1 | preset 不生效 | `preset` 解析后仍把 `child_registry` 覆盖成父表 | `test_a_preset_decides_the_child_tools` | 红：子工具表等于父表，preset 没起作用 |
| M2 | 未知 preset 静默回落 | `registry is None` 时改用父表，不返回 `TOOL_ARGS_INVALID` | `test_an_unknown_preset_is_a_result` | 红：未知 id 照样建出了子会话 |
| M3 | 删掉 `extra="forbid"` | 模型传 `tools` 时被静默忽略 | `test_the_tools_argument_is_gone` | 红：删除的旧参数又“成功”了 |

**基线**：还原后 `tests/test_subagent.py` + `tests/test_subagent_presets.py` 26 passed。

**关于 M3 的取舍**：`extra="forbid"` 不是安全边界，是「删除一个参数」这件事实的判据——没有它，旧参数会被 pydantic 静默丢掉，模型和读者都看不出它已经被删了。

## Learning Gate

可复用的判断已经固化在两处，本轮 **NO-PROMOTION**（`docs/lessons.md` 的收件箱已超过 15 条，按纪律先消化再收）：

- **「形状相同 ≠ 来源相同」**：`subagent.tools` 与 DSH 的 `scope.tools` 形状一样（都是创建时的工具面），但作者不同（模型 vs 部署）。判断一个参数该不该存在，先问「谁写这份内容」——写进 ADR-0037。
- **删参数要留证据**：`extra="forbid"` + schema 判据让删除可观察；否则旧参数会被静默吞掉。写进本文件的 M3。
