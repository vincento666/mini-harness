# M14 DSH parity review

**日期**：2026-11-11。对照 DSH 公开文档：[skills](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/skills.md)、[commands](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/commands.md)、[tools](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/tools.md)。

| 面 | DSH 的做法 | mini 的落成 | 结论 |
|---|---|---|---|
| **发现** | 六级根（100 project-dsh、200 project-agents、300 custom、400 user-dsh、500 user-agents、600 bundled）；项目根 = 最近 `.git` 祖先；kebab-case；目录式 `<name>/SKILL.md` 或扁平 `<name>.md`，不递归；watcher 热更新；host + 每 scope 一层的分层注册表 | 四级根（100 `.minihns`、200 `.agents`、400 `MINIHNS_HOME`、600 `builtin_skills`）；项目根就是 workspace；kebab-case；两种形状、不递归；装配期快照；单层 | **simplified**：根少两级、无 git 祖先探测、无 watcher、无分层。代价与触发条件见 ADR-0038 |
| **清单注入** | 第一个 `agent/pre-step` 注入 user 角色 `<system-reminder>`，只放名字 + XML 转义描述；之后每步比对 digest，变了追加完整替换；不完整快照保留上一版 | `session/start.payload.skills` 只放清单；受保护头部放名字 + 描述（2000 字符预算、截断 marker）；启动快照 | **simplified**：头部 vs user reminder、快照 vs 每步替换。触发条件：会话中途增删技能要即时可见 |
| **`skill` 工具** | `dsh-tool-skill` 插件；校验 kebab-case 与 `modelInvocable`；每次调用重读正文；返回 `<skill_content>` / `<skill_resources>` / `<skill_instructions>` | 内置工具；同样的 XML 三段；未知名字 `TOOL_ARGS_INVALID`；32 KiB 截断；正文落 `tool/result` | **aligned**（结果形状与按需读取）；**simplified**（插件注册与 invocation policy，ADR-0035/0038） |
| **命令面** | `dsh-commands` 注册表；handler 直接执行，不创建模型消息；`command/run` + `command/done`；语法/未知名字的 admission miss 不落日志；按 agent 作用域 | `commands.py` 共用实现；CLI `/skills` `/skill` 与 host `GET/POST /commands`；同样的两件套事件；admission miss 不落日志；不开段 | **aligned**（作用域与插件化按 mini 的简化处理） |
| **preset persona** | `agentPreset` 是会话级 preset，根与子都跑在某个 preset 下；persona 是 preset 的一部分 | `[subagent.presets.<id>].persona` 只作用于子会话；单个字符串 | **simplified**：child-only、字符串。触发条件：根会话也要 preset 时（ADR-0038） |

## 结论

模型可见的三面（`skill` 工具结果、命令语义、清单形状）与 DSH 同形；差异集中在**发现广度、注入机制、注册模型与 preset 作用域**，全部是已记账的简化（ADR-0038），没有未记录的 `deferred` 项。技能热更新（watcher + digest 替换）记为触发条件：需要会话中途增删技能即时可见时再做。
