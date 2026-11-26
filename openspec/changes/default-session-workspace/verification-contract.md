# 验收契约：默认工作区改为会话专属目录

## 自动化判据（全部可黑盒自动化，无 tty 手感 UAT）

1. **默认隔离**：`MINIHNS_HOME` 指临时目录，不传 `--workspace`，cwd 指另一临时目录；mock fixture 让模型 `write snake/core.py`。
   - 判据：文件在 `<MINIHNS_HOME>/workspaces/<sid>/snake/core.py`；cwd 与仓库根无新文件；stderr 含工作区绝对路径；stdout 无路径。
2. **显式不变**：`--workspace <dir>` 下同一 fixture。
   - 判据：文件在 `<dir>`；`session/start.workspace == <dir>` 绝对路径；行为与变更前逐点一致。
3. **发现根锚启动目录**：启动目录放 `mini.config.toml`（如 `max_steps=2`）、`AGENTS.md`、`.minihns/skills/demo/SKILL.md`，不传 `--workspace`。
   - 判据：`session/start.max_steps == 2`；`context/assembled` 前有 `workspace-instructions` 注入；技能清单含 `demo`；会话工作区下的同名文件不被读取。
4. **围栏不变**：默认模式下 `write ../escape.txt` 与 `bash "touch ../x"`。
   - 判据：`SANDBOX_DENIES_WRITE` 的 `tool/result` + `error/fence`，无文件产生。
5. **resume 四条**：恢复日志工作区；显式优先；`WORKSPACE_MISSING`（退出码 1）；旧日志缺字段 `INVALID_ARGUMENT`（退出码 2）。
6. **创建失败**：`MINIHNS_HOME` 指只读路径。
   - 判据：退出码 2、`INVALID_ARGUMENT`、无日志文件。
7. **session_id 先于工作区**：`session/start.workspace` 路径里的目录名 == `session/start.session_id`（日志里的会话 id）。

## 变异

- M1 默认目录拼接漏 `session_id`（所有会话共享一个 `workspaces/`）→ 判据 1/7 杀。
- M2 发现根误锚会话工作区 → 判据 3 杀（config/skills/AGENTS.md 全失效）。
- M3 resume 静默落到 cwd 或新建默认工作区 → 判据 5 杀。
- M4 显式 `--workspace` 被默认逻辑覆盖 → 判据 2 杀。
- M5 创建失败被吞（降级成 cwd）→ 判据 6 杀。
- M6 工作区路径写上 stdout → 判据 1 杀。

## 门禁与真端点

- `scripts/gates.sh` 全绿（pytest、ruff、`mypy --strict`、`openspec validate --all --strict`）。
- 真端点一场（openrouter + proxy，管道喂提示词，明确要求直接写正文与小文件）：产物落会话目录、stderr 报路径、启动目录干净。管道读数不替代任何 tty 验收——本 change 没有手感判据，管道验证即够。

## 不验什么

- 不验会话工作区的清理/保留策略（提案明确不做自动清理）。
- 不验 `--session-dir` 默认（本 change 不动日志目录）。
- 不验 subagent 的工作区继承细节（继承逻辑锚 `parent.workspace`，本 change 不改其代码；黑盒一条子代理判据随门禁回归即可）。
