# 提案：默认工作区改为会话专属目录

## 为什么

2026-11-25 的 UAT 会话（`483e4e32…`）里，人让模型「开发一个贪吃蛇」，模型把 `snake/`
直接写进了启动目录（项目仓库根）。人裁（2026-11-26）：**没给 `--workspace` 时，会话工作区
默认改为用户目录下的对应子目录**，不再默认落在当前目录。

现状语义是「工作区 = `--workspace` 或当前目录」（`assembly.py:238-239`），围栏放行工作区内的
一切写入。于是从项目仓库根启动 chat，一次性产物（`snake/`、`essay.txt`）就落进 git 仓库；
想隔离只能靠人记得加 `--workspace`，默认路径下没有任何保护。

## 要改什么

- **默认工作区 = `$MINIHNS_HOME/workspaces/<session_id>/`**（未设 `MINIHNS_HOME` 时为
  `~/.mini-harness/workspaces/<sid>/`），装配期创建；创建失败当场 `INVALID_ARGUMENT`（退出码 2），
  不建日志。`--workspace` 显式给时完全不变。
- **发现根与围栏根分离**：围栏根（file/bash/subagent/present 等一切改动的边界）= 会话工作区；
  发现根（`mini.config.toml`、skills 项目两级根、`AGENTS.md` 项目契约）= 启动目录
  （显式 `--workspace` 时为它，否则为当前目录）。显式给 `--workspace` 时两者重合，与今天逐点一致。
- **resume 恢复工作区**：`session/start` 已记录 `workspace` 绝对路径；resume 默认读回并复用
  同一目录，显式 `--workspace` 优先于日志。
- **观感**：启动时 stderr 报一行工作区路径；stdout 契约不变（run 仍只打 session id，chat 的
  stdout 仍只有正文与提示符）。

## 不做什么

- **不自动清理会话工作区**：产物留给人复查；清理属 retention，另议。
- **不搬 session 日志目录**：`--session-dir` 默认仍是当前目录下的 `sessions/`。它也占 cwd，
  但变更面独立，不混入本 change。
- **不做 `--isolate` 之类的 flag**：默认即隔离，`--workspace` 就是显式逃生门，不需要第二个开关。
- **不动围栏与工具实现**：file/bash/subagent/present 的边界判断都锚「工作区」一词，语义不变，
  变的只是默认值落在哪。retention spill 在工作区下，跟随围栏根，行为不变。

## 影响面

主规格动五份：`cli`（默认值与有效参数记录）、`config-layering`（发现锚从「workspace 解析后的
目录」改为「启动目录」）、`skills`（项目两级根锚发现根）、`workspace-contract`（项目契约锚
发现根）、`session-resume`（resume 恢复工作区）。host 的 `POST /sessions` 走同一份装配，
`workspace` 未给时随新默认，规格不加 delta（现状未写死默认值）。
