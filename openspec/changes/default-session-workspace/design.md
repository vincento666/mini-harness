# 设计：默认工作区改为会话专属目录

> **人裁（2026-11-26，AskUserQuestion）**：发现根锚启动目录（确认符合主流 harness 设计、且
> 任何目录都能启动）；resume 恢复工作区、显式优先、缺目录报 `WORKSPACE_MISSING`。
> **只立案、暂不实现**（人裁 2026-11-26：先解决 goal 场景问题），实现顺序排在这之后。

## D1 默认值与创建时机

`--workspace` 未给时工作区解析为 `$MINIHNS_HOME/workspaces/<session_id>/`
（`MINIHNS_HOME` 未设时 `~/.mini-harness`），装配期 `mkdir -p`。两个先行事实：

- **session_id 必须先于 workspace 生成**：现在 id 在 `EventLog.create`（`writer.py:52`）里
  才出现。把 id 生成提到装配期（`uuid.uuid4().hex`），`EventLog.create` 接受显式 id，
  不够用时保持 `cls.create(session_dir, session_id=None)` 的旧签名。
- **创建失败当场失败**：`mkdir` 抛 `OSError` → `INVALID_ARGUMENT`（退出码 2），不发任何
  请求、不建日志——与 config 非法的失败时机对齐。

显式 `--workspace` 的路径走旧逻辑（`abspath`，不自动创建）——今天它对不存在的目录是什么
行为就保持什么行为，本 change 不碰。

## D2 发现根与围栏根分离（本 change 的核心分叉）

「workspace」一个词今天同时承担两件事。默认值一变，必须拆开：

- **围栏根**：file/bash/subagent/present/retention 的一切改动边界 = 会话工作区。
  规格（`fences`、`bash-tool`、`file-tools`）里「工作区」「工作区根」的措辞不动。
- **发现根**：`mini.config.toml`（D7）、skills 项目两级根、`AGENTS.md` 项目契约锚
  **启动目录**——显式 `--workspace` 时为它，否则为当前目录。

理由：人从项目根启动 chat，期望模型带着这个项目的技能、契约与配置干活；但产物理应落在
会话目录。发现根若跟着新默认走会话目录，默认模式下这三样全部静默失效——那不是隔离，
是阉割。显式 `--workspace` 时两者重合，老用户逐点无感。

实现上 `assembly.py` 已有现成锚点：`discovery_workspace`（`:148-149`）就是「`--workspace`
或 cwd」，`skills` 与契约的注入都发生在 workspace 定下来之前/同级——把这两处改传
`discovery_workspace` 即可，不需要新增贯穿参数。主规格措辞：发现处改用「发现根」。

## D3 resume 恢复工作区

`session/start` payload 已记录 `workspace`（`cli/spec.md:36`），resume 读回它作为工作区；
显式 `--workspace` 优先于日志值。恢复的目录不存在时**报错退出**（`WORKSPACE_MISSING`，
退出码 1）——目录被人为删掉时静默重建会让人以为产物还在。日志没有 `workspace` 字段的
旧记录：本 change 不做 schema 迁移，resume 遇到缺字段按「显式 `--workspace` 也没给」处理，
报 `INVALID_ARGUMENT`。

## D4 观感与日志

- 启动时 stderr 报一行 `工作区 <path>`（chat 已有「会话 <id>」横幅，紧随其后；run/host 同）。
- stdout 契约不变：run 成功只打 session id；chat stdout 只有正文与提示符。
- `session/start.workspace` 语义变化：默认模式下记会话目录（不再是启动目录）。
  `GET /sessions` 的 `workspace` 字段随 payload，host-api 规格不用改。
- 日志目录默认不动（cwd/sessions），见提案「不做什么」。

## D5 测试策略

黑盒判据全部可自动化，**不需要 tty 手感 UAT**：

- 默认（不传 `--workspace`，cwd 指向临时目录）：模型 `write snake/core.py` 落在
  `$MINIHNS_HOME/workspaces/<sid>/snake/core.py`，cwd 与仓库根无新文件。
- 显式 `--workspace <dir>`：落在 `<dir>`，逐点同旧。
- 发现根：`mini.config.toml`、`AGENTS.md`、`.minihns/skills/` 放 cwd，默认模式下仍生效。
- 围栏：默认模式下越界写（`../`）仍 `SANDBOX_DENIES_WRITE`。
- resume：断点后 resume 不传 `--workspace`，工作区恢复为日志里的；传了则以显式为准。
- `MINIHNS_HOME` 指向临时目录，测试不写真实家目录。

## D6 风险

- **黑盒测试大面积依赖「默认 workspace = cwd」**：`cli_blackbox._cli` 用 `cwd=tmp` 且不传
  `--workspace`。给 harness 的 `_command` 统一补 `--workspace <tmp>`（显式路径逐点同旧），
  逐测试不需要改。
- **真端点 UAT 的旧手册写「产物在项目里」**：`restore-chat-streaming` 的场次 3 判据不受影响
  （判据看 stdout 分行，不看文件位置），但场后清点产物的说明要提一句新位置——在那个 change
  归档时顺手改，不提前动。
