# skill-providers UAT

**状态**：agent 代跑（用户指示，2026-11-12）。四场。环境 `--provider deepseek`（`deepseek-chat`），工作区 `.tmp/uat/s1`–`s4`。

## 场次

| 场次 | 动作 | 预期 |
|---|---|---|
| S1 | 配 `[subagent.presets.reader.skills] kind="filesystem"`、`dirs=["sk"]`，全局与层里各放一个 `tdd` | 子会话看到层里那份；父会话是全局那份 |
| S2 | 层里放一个全局没有的 `review` | 子会话的目录与 `/skills` 有它；父没有 |
| S3 | 会话中途新建技能后再 `/skills` | `/skills` 与模型目录都看到 |
| S4 | 把 `kind` 写成 `remote` | 退出码 2、`INVALID_ARGUMENT`、无日志 |

## 观察表

| 场次 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|
| S1 | 父 `/skills` 两次（spawn 前后）都只有 `tdd`=「全局的 tdd：项目根的测试驱动技能」；子会话 `3a05b9f3…` → `c969b241…` 的 `session/start.skills` 与目录消息都只有 `tdd`=「preset 的 tdd：reader 档的测试驱动技能」；模型自己指出「名称一致、描述不同」 | 通过 | 父会话看不到子会话的技能来自哪一层——本场跑完后按人裁决加了 `Skill.source`，现在 `session/start` 与目录消息都写层名 |
| S2 | 父 `/skills` 两次都只有 `tdd`；子会话 `96d9f1d6…` → `7d9f1a4f…` 的目录是 `review`（「评审时先指出风险」）+ `tdd`；模型指出「子会话多一个 review」 | 通过 | 同上（本场之后已加 `source`）；另外 `review` 只在子会话可调，父会话里没有它，这一点界面上没有提示 |
| S3 | 会话 `a7716fd8…`：第一次 `/skills` 只有 `tdd`；模型用 bash 写 `.minihns/skills/review/SKILL.md` 后，第二次 `/skills` 是 `review` + `tdd`；同一时刻模型目录消息从「tdd」变为「review + tdd」，`digest` 变化 | 通过 | 没有；命令面与目录同源这条读起来是直的 |
| S4 | `minihns run` 退出码 **2**；stdout 空；stderr 为 `INVALID_ARGUMENT: [subagent.presets.reader].skills.kind 只接受 filesystem`；`--session-dir` 下 0 个文件 | 通过 | 错误指向 `kind` 且给出唯一合法值，够用 |

**结论**：通过。

## 附：人跑时可留意

- 四场都是 agent 在真实端点上跑的，没覆盖「人对着屏幕时的迟疑点」。真正要人看的是 S2 的第三条：子会话独有的技能在父会话里不可见，但父会话的模型会读到子会话的转述——这条边界是否该在系统提示里说明，留给下次 UAT 判断。
