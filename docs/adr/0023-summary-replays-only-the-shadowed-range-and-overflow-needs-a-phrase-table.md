---
status: accepted
---

# 摘要只回放被遮蔽的那一段；认溢出靠一张固定短语表

**更正一件写进过主规格的事。** M5 的 `context-projection` 规格原本写的是「摘要请求装被遮蔽那段折出来的消息」，实现送的是「受保护头部 + 当时整份表层 + 一条固定指令」；`code-review` 的 Spec 轴指出不一致后，人裁决「改措辞，保留实现」（M5 tasks 9.3，归档 design D2 写明代价是「摘要会重述保留尾部里仍在场的内容」）。DSH 不是那个形状：`dsh-compaction-basic` 的摘要调用回放「surface 节点 0 的系统消息 + **已遮蔽区域的消息** + 尾随压缩指令」（`re/verified/dsh/node_modules/@deepseek-ai/dsh-compaction-basic/README.md` 第 119 与 187 行）。按「DSH 为真」（ADR-0011 / 0012 / 0013 的纪律）更正过来：`events/fold.py` 加一个按 seq 闭区间折出对话的入口 `fold_range`，回合循环只调它。M5 的 D9 当时避开的正是「给 fold 加一个子区间参数」——这笔账现在付了，换来的是摘要请求不再比它要缩小的东西更大（真端点上那次：`prompt (222233 tokens) leaves no room to answer in the context (196608)`）。

**第二件是认溢出的代价。** DSH 的溢出是提供方确认的失败（它的 `agent/request-error` 监听器接的是 provider-confirmed `CONTEXT_WINDOW_EXCEEDED`）；mini 接的真端点回的 400 里**没有** `error.code`，只有 `type: "invalid_request_error"` 与一句 `message`。所以 provider 层认溢出只能是：`error.code` 命中，或 `message` 命中一张固定短语表（`ContextOverflowPhrase`，大小写不敏感，不做模糊匹配）。

Considered options：只认 `error.code`（否：真端点不给这个键，实测那次就是不给）；HTTP 400 一律当溢出（否：400 最常见的原因是请求本身写坏了，把它当溢出会让压缩反复重试同一份装不下的东西）；把正文交给上层去判断（否：措辞知识会散到 seam ①，而措辞是 provider 那一层的事实）。

Consequences：短语表是一份会过期的东西——端点改措辞就退化成 `PROVIDER_HTTP_STATUS`（仍然可见、仍然塌成段，只是不再走溢出那条路），要加条目而不是改判定逻辑；表里每条的可达性由 `tests/test_vocabulary_reachability.py` 钉着，实测到的真实形状留在 `tests/fixtures/real_endpoint/`（ADR-0022）。
