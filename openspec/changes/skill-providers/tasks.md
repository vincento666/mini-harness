# Tasks

## 1. Provider 与注册表（seam ②）

- [x] 1.1 `SkillProvider` 协议 + filesystem 实现（list/get，包装四根与正文读取）
- [x] 1.2 `SkillRegistry`：全局层 + `scoped(provider)`；`snapshot()` 近层胜出、按名字排序
- [x] 1.3 层内裁决：同一层内按 rank/注册顺序；近层低 rank 仍胜

## 2. 装配与目录（seam ①④）

- [x] 2.1 `assemble` 建全局 provider + 注册表，进 `Prepared` 与 `SessionEnv`
- [x] 2.2 目录消息改读 `registry.snapshot()`；`settings.skills` 只做 payload 快照
- [x] 2.3 会话中途加/删/不完整仍按 A 的判据走

## 3. 命令面与工具（seam ②⑥）

- [x] 3.1 `/skills`、`/<技能名>`、host 命令面改读注册表快照（关闭 A 的 D7）
- [x] 3.2 `skill` 工具执行时走注册表；无注册表回落构造元组

## 4. 配置与子会话（seam ②⑦）

- [x] 4.1 `[subagent.presets.<id>.skills]` 解析/校验（kind/filesystem、dirs）
- [x] 4.2 删除 `skill_dirs`；未知键、未知 kind、dirs 类型错误 → 退出码 2
- [x] 4.3 spawn 时 `registry.scoped(preset provider)`；子会话目录/命令面读它
- [x] 4.4 父会话不受 preset 层影响；根只有全局层

## 5. 收尾

- [x] 5.1 真实端点：preset provider 覆盖同名技能、命令面与模型目录一致
- [x] 5.2 UAT（人跑）
- [x] 5.3 变异测试一轮
- [x] 5.4 Learning Gate
- [x] 5.5 对齐复核（十项）
- [x] 5.6 ADR-0035 修订 + ADR-0040
