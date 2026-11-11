# Tasks

## 1. 解析与形状（seam ②）

- [ ] 1.1 `Skill` 增加 `model_invocable` / `user_invocable`；缺省都为 true
- [ ] 1.2 布尔语法：true/false、yes/no、on/off、1/0（大小写不敏感）；其它值丢弃整个技能
- [ ] 1.3 `description` 必填；无 frontmatter 或空描述跳过
- [ ] 1.4 四种组合（both / model-only / user-only / neither）各有一条发现判据

## 2. 出口过滤（seam ②④⑥）

- [ ] 2.1 seam ④：`session/start.payload.skills` 只列模型可调的技能
- [ ] 2.2 seam ②：`skill` 工具对非模型可调返回 `TOOL_ARGS_INVALID`（不读正文）
- [ ] 2.3 seam ⑥：`/skills` 与 `/<技能名>` 只认用户可调；`/skill <名字>` 同
- [ ] 2.4 seam ⑥：host `GET /commands?session_id=` 与 `POST` 同源过滤
- [ ] 2.5 两面都禁用的技能不出现在任何出口

## 3. 收尾四项

- [ ] 3.1 真实端点：一个 `disable-model-invocation` 技能只能经 `/技能名` 注入，模型工具调不到
- [ ] 3.2 UAT（人跑）：三类技能各办一件小事
- [ ] 3.3 变异测试一轮
- [ ] 3.4 Learning Gate
