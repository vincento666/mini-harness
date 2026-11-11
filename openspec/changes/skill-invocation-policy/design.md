# Design

## Decisions

**D1 策略在发现期解析，在所有出口过滤。** `Skill` 增加 `model_invocable` 与 `user_invocable` 两个布尔；`settings.skills` 保留**全部**发现结果（含两面都禁用的），由各出口自己过滤：`session/start.payload.skills` 只写模型可调、命令面只取用户可调、`skill` 工具只认模型可调。这样「策略」是一份事实，出口各自引用，不在发现期丢信息。

**D2 模型面：payload 即过滤点。** `session/start.payload.skills` 只列 `model_invocable` 的技能；头部与回放都从 payload 折叠，所以不需要在 fold 里再判一次。payload 的每一项带 `model_invocable` / `user_invocable`（审计用，不进头部文本）。

**D3 工具面：加载前校验。** `skill` 工具只接受 `model_invocable` 的名字；非模型可调返回 `TOOL_ARGS_INVALID`（文本与「未知技能」区分开），不读正文。

**D4 人机面：只认 `user_invocable`。** `/skills` 只列用户可调的技能；`/<技能名>` 只对用户可调生效；`/skill <名字>` 也按用户可调过滤（它是人机入口，不是调试通道）；host 的 `GET /commands?session_id=` 同源。两面都禁用的技能不出现在任何出口。

**D5 布尔语法照 DSH。** 接受 `true/false`、`yes/no`、`on/off`、`1/0`（大小写不敏感）；其它值视为 malformed，**丢弃整个技能**（与「名字不合法」同一条处置），不静默放行。

**D6 `description` 改为必填。** 与 DSH 的 filesystem provider 一致：`name` 与 `description` 必填，缺失/空即 malformed；无 frontmatter 的扁平文件不再是技能。这条会改变现有「无 frontmatter 的 flat.md 也能被发现」的行为，测试跟着改。

## Risks

- **策略位写反**（`disable-model-invocation: false` 被当成禁用）会让技能从模型目录消失；判据要覆盖默认值与四种组合。
- **两面都禁用**的技能如果还出现在 `/skills`，会暴露一个「能看见但什么都干不了」的条目；D4 的判据要覆盖。
- **payload 过滤**意味着 `session/start.payload.skills` 与 `settings.skills` 不再是同一份；host 的命令面必须从 settings 取、不能从 payload 取。
