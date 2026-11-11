# skill-invocation-policy UAT

**状态**：**agent 代跑**（用户明确指示，2026-11-11），观察由 agent 记录；合并前由用户确认这笔偏离。

## 跑前准备

工作区 `/tmp/policy-uat`：`both`（默认）、`model-only`（`user-invocable: false`）、`user-only`（`disable-model-invocation: on`）、`neither`（两面禁用）、`bad`（`disable-model-invocation: maybe`）。provider `deepseek`。

## 场次与观察

| 场次 | 动作 | 实际观察 | 结论 |
|---|---|---|---|
| S1 | `/skills` | 列出 `both` 与 `user-only`；不列 `model-only`、`neither`、`bad` | 通过 |
| S2 | `/both` | 开段；`user/message` 含技能正文 + 「请按技能执行」；模型回复以「【BOTH】」开头 | 通过 |
| S3 | `/model-only` | stderr「未知命令：/model-only」；日志无 `command/*` | 通过 |
| S4 | `/neither` | stderr「未知命令：/neither」；日志无 `command/*` | 通过 |
| S5 | `/skill user-only` | 打印正文、不开段（查看路径） | 通过 |
| S6 | 让模型 `skill(user-only)` / `skill(model-only)` | 前者 `TOOL_ARGS_INVALID`「不可由模型调用」；后者 `OK` | 通过 |
| S7 | `session/start.payload.skills` | 只有 `both`、`model-only` | 通过 |

## 别扭

- `/model-only` 与 `/neither` 都报「未知命令」——人分不出「存在但不可由用户调」与「不存在」（DSH 的 `/name` 对未知与 user-disabled 都保持普通文本，不报错）。
- `/skill <名字>`（查看）与 `/<技能名>`（执行）两个入口只差一个 `skill` 前缀，第一次用容易混。

**结论**：通过（agent 代跑）。
