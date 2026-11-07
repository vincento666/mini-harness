# M12 真实端点验收

**日期**：2026-11-06（本机 macOS，`--provider deepseek`，模型 `deepseek-chat`）。密钥只从环境变量读，不进 argv、不进日志。

## 场次

### S1 · 一次委派

`minihns run --provider deepseek -p "用 subagent 让子会话读 inbox.md 并总结成一句话" --yes`

| 观察 | 事实 |
|---|---|
| 父会话 | `entry=run`，3 个回合、2 条 `tool/result`（先 `glob` 看工作区，再 `subagent`） |
| 子会话 | `entry=subagent`、`parent_session_id=05a2d1ed…`、`depth=1`，2 个回合、1 条 `read` 结果 |
| 父拿到的结果 | 父最后一条 `model/response` 是子会话的一句话总结（「inbox.md 只有一行……即一条把该内容写入 note.md 的待办目标」） |
| 父日志 | 没有子会话的 `model/*` 或 `read`；父自己的 `glob` 是它自己的回合 |

### S3 · 深度超限

`-p "派一个 subagent，让它自己再派一个 subagent 去读 inbox.md" --yes`

| 观察 | 事实 |
|---|---|
| 子会话（depth 1） | 它调 `subagent` 的那一条结果是 `DEPTH_EXCEEDED`：「子代理的深度 2 超过 maxDepth 1」 |
| 子会话收尾 | 被拒之后它自己 `read` 了 inbox.md 才收尾——结果词不打断回合 |
| 父会话 | 拿到 OK 与子会话的最终文本 |

### S4 · 子会话问人不可用

不设 `--yes`（ask 模式，非 tty）：`-p "必须派一个 subagent 完成：让子会话把 inbox.md 的内容写进 note.md"`

| 观察 | 事实 |
|---|---|
| 子会话的写 | `tool/result` 是 `DENIED_BY_APPROVAL`，配对 `error/fence(code=APPROVAL_UNAVAILABLE)` |
| 落盘 | `note.md` 没有被创建 |
| 父会话 | 自己的 `read`/`glob` 正常；三次派子代理都被拒，父照常结束（EXIT 0） |

### S5 · 取消

本轮没跑（要 tty 的 `chat` 场次，留给 UAT）。mock 侧的 `test_parent_cancel_cancels_the_child` 与 `test_a_completed_child_result_survives_parent_cancel` 已覆盖同一行为。

## 别扭的地方（记下来给 M13/UAT 用）

- **父代理不会区分「能力不可用」与「临时失败」**：S4 里它连派三次 subagent 去写，三次都是 `APPROVAL_UNAVAILABLE`，它仍继续换措辞重试。子结果只有最终文本，父看不到子会话被围栏拒绝的细节——真实模型只能从文本里猜。这提示「子会话的停止理由要不要进父结果」可能是 M13 的一个输入。
- **`sandbox` 参数在真实使用里是等宽**：模型传的是 `workspace-write`（与父相同），所以「只能收窄」的拒绝分支只有判据覆盖，真实场次里没被触发。
- 根会话的 `session/start` 不写 `depth`（只有子会话写父子三项），Host 视图按 0 兜底；两处口径一致，但读原始日志的人要知道这一点。

## 结论

**通过**：spawn、子日志独立、父只拿最终文本、深度是结果词、子会话审批不可用，四项都在真实端点上成立。
