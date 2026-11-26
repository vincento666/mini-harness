# 任务：默认工作区改为会话专属目录

## 1. 实现

- [ ] 1.1 `session_id` 生成提前到装配期：`EventLog.create` 接受显式 id（保留旧签名的 `session_id=None` 路径），装配期先生成 id 再解析工作区
- [ ] 1.2 默认工作区解析：未给 `--workspace` → `$MINIHNS_HOME/workspaces/<sid>/`，`mkdir -p`；`OSError` → `INVALID_ARGUMENT` 退出码 2，不建日志
- [ ] 1.3 发现根与围栏根分离：`skills` 项目两级根与 `AGENTS.md` 项目契约改锚 `discovery_workspace`（显式 `--workspace` 或 cwd）；config 发现维持现状（本来就是「workspace 或 cwd」，改措辞与判据）
- [ ] 1.4 resume 恢复工作区：读 `session/start.workspace`，显式优先；`WORKSPACE_MISSING`（退出码 1）与旧日志缺字段 `INVALID_ARGUMENT`（退出码 2）两条失败路径
- [ ] 1.5 观感：启动时 stderr 报一行工作区路径（chat 紧随「会话 <id>」横幅；run/host 同）；stdout 契约不变
- [ ] 1.6 `--help` 文案：`--workspace` 的说明改写新默认（含「发现根仍锚启动目录」一句）

## 2. 测试

- [ ] 2.1 黑盒 harness 补默认 `--workspace`（指向各测试自己的临时目录），逐点同旧；逐测试不改
- [ ] 2.2 新判据：默认模式产物落 `$MINIHNS_HOME/workspaces/<sid>/`、启动目录无新文件（`MINIHNS_HOME` 指临时目录）
- [ ] 2.3 新判据：显式 `--workspace` 逐点同旧；发现根（config/skills/AGENTS.md）在未传 `--workspace` 时仍锚启动目录
- [ ] 2.4 新判据：默认模式下越界写（`../`）仍 `SANDBOX_DENIES_WRITE`；围栏根是会话目录
- [ ] 2.5 新判据：resume 恢复日志工作区、显式优先、`WORKSPACE_MISSING`、旧日志缺字段四条
- [ ] 2.6 变异：M1 默认目录拼接漏 `session_id`（共享目录）；M2 发现根误锚会话工作区（技能/契约失效）；M3 resume 静默落到 cwd；M4 显式 `--workspace` 被默认逻辑覆盖

## 3. 验证与文档

- [ ] 3.1 门禁全绿：`scripts/gates.sh`（pytest、ruff、mypy --strict、openspec validate --all --strict）
- [ ] 3.2 真端点一场验证（管道即可，无 tty 手感场次）：不传 `--workspace` 让模型写一个小文件，产物落会话目录、stderr 报路径、启动目录干净
- [ ] 3.3 文档：`docs/CURRENT.md`、`docs/roadmap.md`；`restore-chat-streaming-uat.md` 的产物清点说明在归档时顺带改（design D6，不提前动）
