# chat-repl Delta

## MODIFIED Requirements

### Requirement: 自动轮次在 stderr 留下边界

REPL 里由目标驱动自动开的轮（带 goal 轮次），系统 SHALL 在该轮开始前向 stderr 打印一行 `[轮] <n>/<cap>`，其中 `<n>` SHALL 只对**目标驱动自动开的轮**计数——人类轮（用户输入直接开的轮）MUST NOT 消耗或推进 `<n>`，`<cap>` 仍是目标账本里的轮次上限（显示镜像账本事实，两者不得为对齐观感而改账）。收尾时：额度用尽 SHALL 打印一行含 `已用尽 <n>/<cap>` 与 `round-limit`；因未决问题交回控制权 SHALL 打印一行含 `目标保持 active` 与「回答后自动继续」；零工具调用的空转 SHALL 打印一行含「已停止自动推进」与 `/goal resume` / `/goal complete`。这些行 MUST NOT 写进事件日志、MUST NOT 出现在 stdout；人工轮、`run` 与 `serve` 上的输出 MUST NOT 因此改变。「轮不以 `MODEL_COMPLETED` 收尾时打印一行」那条既有规则不变。

#### Scenario: 两轮续跑看得见边界

- **WHEN** 一个上限为 2 的目标在 chat 里连跑两轮
- **THEN** stderr 依次出现 `[轮] 1/2`、`[轮] 2/2` 与含 `已用尽 2/2` 的一行；stdout 里没有这些行

#### Scenario: 未决问题停在哪里看得见

- **WHEN** 第 1 轮问了一个人答不了的问题
- **THEN** stderr 有 `[轮] 1/3` 与含 `目标已暂停` 的一行，没有 `[轮] 2/3`；提示符回到人手里

#### Scenario: 人类轮不消耗自动轮编号

- **WHEN** 建目标发生在人类轮（人类轮里模型写了正文、调了工具），随后目标驱动自动续跑 3 个轮、目标上限为 3
- **THEN** stderr 依次出现 `[轮] 1/3`、`[轮] 2/3`、`[轮] 3/3`，编号与目标自述的第 N 轮一致；人类轮没有 `[轮]` 行、也没有让任何一个自动轮从 2 起跳

> 本 delta 不改任何实现行为——`<n>` 只计自动轮是既定账本语义（`goal-round-pacing` 落地、场次 3 tty 人跑与会话 `8ec5e70e…` 实机复核）；把语义显式钉进规格，是为了防止后续 change 以「对齐观感」为由把人类轮计入编号。`[轮]` 编号与模型自述轮次的日常对齐靠验收跑法（UAT 场次 3 提示词要求「建目标的本轮不要写任何正文」，change `round-label-prompt-alignment` 的 proposal），不靠改机制。
