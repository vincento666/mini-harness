# Tasks

## 1. 解析与形状（seam ②）

- [x] 1.1 `Skill` 增加 `model_invocable` / `user_invocable`；缺省都为 true
- [x] 1.2 布尔语法：true/false、yes/no、on/off、1/0（大小写不敏感）；其它值丢弃整个技能
- [x] 1.3 `description` 必填；无 frontmatter 或空描述跳过
- [x] 1.4 四种组合（both / model-only / user-only / neither）各有一条发现判据

## 2. 出口过滤（seam ②④⑥）

- [x] 2.1 seam ④：`session/start.payload.skills` 只列模型可调的技能
- [x] 2.2 seam ②：`skill` 工具对非模型可调返回 `TOOL_ARGS_INVALID`（不读正文）
- [x] 2.3 seam ⑥：`/skills` 与 `/<技能名>` 只认用户可调；`/skill <名字>` 同
- [x] 2.4 seam ⑥：host `GET /commands?session_id=` 与 `POST` 同源过滤
- [x] 2.5 两面都禁用的技能不出现在任何出口

## 2b. 发现完整性（seam ②④）

- [x] 2b.1 seam ②：根 `iterdir` 失败 → `complete=false`；单文件坏 → 跳过且不影响 complete
- [x] 2b.2 seam ④：`payload.skills_incomplete` 与头部警告行（清单为空也出现）
- [x] 2b.3 下一次装配重新发现（不沿用上次结果）

## 2c. preset 作用域层（seam ②⑦）

- [x] 2c.1 seam ②：`skill_dirs` 配置校验（字符串数组；目录不存在不是错）
- [x] 2c.2 seam ⑦：子会话 = 全局 + preset 层，preset 层同名直接胜出；父会话不变
- [x] 2c.3 seam ⑦：preset 层独有的技能只在子会话出现
- [x] 2c.4 preset 层目录扫不动 → 子会话 `skills_incomplete`

## 3. 收尾四项

- [x] 3.1 真实端点：一个 `disable-model-invocation` 技能只能经 `/技能名` 注入，模型工具调不到
- [x] 3.2 UAT（人跑）：三类技能各办一件小事
- [x] 3.3 变异测试一轮
- [x] 3.4 Learning Gate
