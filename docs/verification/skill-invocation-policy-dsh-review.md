# skill-invocation-policy 对齐复核

**日期**：2026-11-11。时点：code-review 之后、归档之前。对齐对象：提案 / 设计 / 规格 / 验收 + DSH 十项。

## 提案与验收

| 类别 | 对照点 | 提案说什么 | 实现是什么 | 结论 |
|---|---|---|---|---|
| 提案 | 两个策略位、缺省都允许 | 加 `model_invocable` / `user_invocable` | `skills.py::Skill` 两字段；`_policy` 缺省 False/True | aligned |
| 提案 | 模型面只认模型可调 | payload / 头部 / 工具过滤 | `turn_loop` 只写模型可调；`tools/skill.py` 拒绝非模型可调 | aligned |
| 提案 | 人机面只认用户可调 | `/skills`、`/<名>`、`/skill`、host 同源 | `commands.py` 三处过滤；host 走同一 `command_catalog` | aligned |
| 提案 | 完整性 | `complete` + `skills_incomplete` + 头部警告 | `SkillDiscovery`；payload 标志；`fold` 警告行 | aligned |
| 提案 | preset 层 | `skill_dirs`，层同名胜出 | `merge_skill_layer`；spawn 时合并；父不变 | aligned |
| 验收 | 1.1–2c.4 共 16 条 | 见 tasks.md | 全部有判据，全量 635 passed | aligned |

## 设计决策

| 决策 | 实现 | 结论 |
|---|---|---|
| D1 发现期解析、出口过滤 | `Skill` 带策略；四处出口各自过滤 | aligned |
| D2 payload 即模型面过滤点 | `turn_loop` 过滤 | aligned |
| D3 工具加载前校验 | `tools/skill.py` | aligned |
| D4 人机面过滤 | `commands.py` | aligned |
| D5 宽松布尔、非法丢弃 | `_policy` + `_skill_at` | aligned |
| D6 description 必填 | `_skill_at` | aligned |
| D7 完整性 | 根 `iterdir` 失败 → false | aligned |
| D8 preset 目录层 | `merge_skill_layer` | aligned |
| D9 `skill_dirs` 校验 | `config/assembly.py` | aligned |

## DSH 十项

| # | 项 | 结论 | 记账 |
|---|---|---|---|
| 1 | 形状 | aligned | `SkillInvocationPolicy` 对应两布尔 |
| 2 | 机制 | aligned | 发现期解析、消费者过滤 |
| 3 | 语义 | aligned | 缺省、布尔语法、非法丢弃、description 必填 |
| 4 | 不变量 | aligned | 策略是事实、目录是投影；正文落 `tool/result` |
| 5 | 面 | aligned | 模型 / 人机 / 日志 / host 同源 |
| 6 | 失败与降级 | **simplified** | 没有「last-good 目录」，会话内不恢复；快照下重试=下一次装配。触发：远程/慢 provider 或需要会话内恢复 |
| 7 | 组合与扩展 | **simplified** | 层用目录根而不是挂载 provider（无插件容器，ADR-0035/0039）。触发：preset 需要挂载真正的 provider |
| 8 | 资源与约束 | aligned | 描述 500、正文 32 KiB |
| 9 | 信任与授权 | aligned | 策略只管可见性；围栏/审批不动 |
| 10 | 回放与确定性 | aligned | 清单进 payload、正文进工具结果 |
| — | `/name` 消息手势 | **deferred** | 触发：M14c 之后的 `skill-inline-mention` |

## 结论

提案、设计、规格、验收逐条兑现；DSH 十项里 8 项 aligned、2 项 simplified（触发条件已写）、1 项 deferred（已排期）。两条 simplified 与 deferred 待人裁决后记账。
