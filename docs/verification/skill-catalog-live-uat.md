# skill-catalog-live UAT

**状态**：**agent 代跑**（用户指示「继续」，2026-11-12）；观察由 agent 记录，合并前由用户确认。

| 场次 | 动作 | 预期 | 实际观察 | 结论 |
|---|---|---|---|---|
| S1 | 第一个 turn 前看日志 | 一条 `user/message`，`source=skill-catalog`，含 tdd | seq 3，含 `tdd` | 通过 |
| S2 | 让模型用 bash 新建 `review` 技能后再问 | 追加替换，含 review | seq 11，含 `tdd`+`review` | 通过 |
| S3 | 让模型用 bash 删光技能后再问 | 空目录退休 | seq 11，退休文本 | 通过 |
| S4 | 让模型把技能根改成 000 后再问 | 警告 + `incomplete=true` | seq 13，`incomplete=true` | 通过 |

**通过判据**：目录消息的存在/条数、`source` 与 `incomplete` 字段、内容里的技能名集合；不比对模型措辞。

**别扭**：目录替换是整套重发，技能多时每条替换都重复全部描述；`/skills` 仍是装配期快照，可能与模型目录短暂不一致（已记 simplified）。

**结论**：通过（agent 代跑）。
