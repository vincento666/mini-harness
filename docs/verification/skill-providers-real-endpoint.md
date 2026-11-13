# skill-providers 真实端点

**日期**：2026-11-12。`--provider deepseek`（`deepseek-chat`），两个独立工作区。会话日志在仓库根 `sessions/` 下，id 见各场。

## S1 · preset provider 覆盖同名技能（`61d90706…` 父 / `bc1e8234…` 子）

工作区 `.tmp/real/sp1`：全局 `.minihns/skills/tdd`（描述「全局的 tdd」），preset 目录 `.minihns/preset-skills` 里另有同名的 `tdd`（描述「preset 的 tdd」）与独有的 `extra`。配置：

```toml
[subagent]
preset = "reader"
allowed_presets = ["reader"]

[subagent.presets.reader]
tools = ["read", "glob", "skill"]

[subagent.presets.reader.skills]
kind = "filesystem"
dirs = [".minihns/preset-skills"]
```

任务：让父会话调 `subagent`（`agent_preset = reader`），子会话列技能并读 `tdd` 正文。

| 面 | 观察 |
|---|---|
| 父 `session/start.skills` | 只有 `tdd` =「全局的 tdd：项目根的测试驱动技能」 |
| 父目录消息（seq 4） | 同上，只有一条 |
| `tool/call subagent` | `agent_preset: "reader"` |
| 子 `session/start` | `entry = subagent`、`preset = reader`、`parent_session_id` 指父；`skills` = `extra`（只有 preset 层才有）+ `tdd`（「preset 的 tdd：reader 档的测试驱动技能」） |
| 子目录消息 | `extra` + preset 的 `tdd`，与 `session/start` 一致 |
| 子 `skill` 工具结果 | 正文是「preset 正文：先写红判据，再写最小实现。」——由拥有该名字的层提供 |
| 父末条回复 | 转述子会话的清单与正文，父自己没看到 `extra` |

## S2 · 命令面与模型目录同源（`d8b5c439…`）

工作区 `.tmp/real/sp2`：只有全局 `tdd`。`chat` 从管道喂四条输入：`/skills` → 让模型用 bash 新建 `review` → `/skills` → `/exit`。

| 时点 | 命令面输出 | 模型目录消息 |
|---|---|---|
| 会话开始 | `- tdd（rank 100）：全局的 tdd…` | seq 6：`- tdd: 全局的 tdd…` |
| 模型写完 `review` 之后 | `- review（rank 100）：评审时先指出风险` + `- tdd…` | seq 14：`- review: 评审时先指出风险` + `- tdd…` |

两边在两次观察点的集合与描述一致；`digest` 从 `0bc5ddbd…` 变为 `ceb656f1…`，目录是替换而不是追加。

## 结论

**通过**：真实端点下，preset 的 provider 层按名字覆盖全局层、层独有技能只进子会话、`skill` 工具正文来自拥有该名字的层；命令面与模型目录读同一份快照，中途新增技能在两侧同时可见。

UAT（`docs/verification/skill-providers-uat.md`）另跑，不由本场替代。
