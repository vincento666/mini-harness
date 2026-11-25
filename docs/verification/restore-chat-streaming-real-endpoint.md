# 真实端点验收：restore-chat-streaming

**日期**：2026-11-25
**端点**：OpenRouter `qwen/qwen3.8-27b`，经 `--proxy http://127.0.0.1:7897`（本机直连推理请求会被中转拒掉，见 `verification-endpoint.md` §5）
**口径**（ADR-0024）：不进 CI、不替代门禁，只回答「这套流式接上真端点跑不跑得动」。

## 场次

| # | 命令 | 要观察的值 | 结果 |
|---|---|---|---|
| 1 | `printf '用两句话说明什么是流式输出\n' \| minihns chat --provider openrouter --proxy ... --max-steps 3` | 退出码；stdout 是否有正文；stderr 是否有 `[answer] `；增量拼接是否等于日志里的完整 `content` 且只出现一次 | **通过**：退出码 0；会话 `2eb3ff10712142b8acaa152e1fe26cff`；stdout 是 `> ` + 正文 + `> `；stderr 是会话 id 与 `[answer] `；`content` 119 字符，在 stdout 里出现 1 次 |

## 关键读数

- **拼接一致**：stdout 里的正文与日志 `model/response.content` 逐字相等（`content in stdout` 为真，且 `count == 1`）。
- **日志形状不变**：11 条记录，类型序列是 `session/start → turn/start → user/message → step/start → user/message → context/assembled → model/request → model/response → step/end → turn/end → session/end`；没有 `model/delta`。
- **正文前那两个换行来自模型**：`content` 本身以 `\n\n` 开头，不是渲染器多打的。

## 不承担什么

- **首帧实时性**不在本场判：管道一次性读到底，看不见「首帧何时到」。那条由 `test_the_first_delta_is_visible_before_the_turn_ends`（子进程 + 真管道，能杀死「攒批」变异）与 UAT 场次 1 的肉眼观察覆盖。
- **取消时的半句**不在本场判：需要人按 Ctrl-C，见 UAT 场次 2。
