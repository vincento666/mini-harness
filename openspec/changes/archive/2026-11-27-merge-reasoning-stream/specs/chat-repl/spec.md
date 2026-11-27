# Spec Delta

## ADDED Requirements

### Requirement: chat 的思考帧走 stderr，正文投影不变

`chat` 在流式模式下 SHALL 把 `reasoning/delta` 增量写到 **stderr**，并在本轮第一次思考增量前打一次 `[thinking]` 头行（标记独占一行、自带换行，思考文本从头行下一行开始流式追加）；正文增量仍只写 stdout，`[answer]` 头行仍走 stderr 且每步至多一次。`[thinking]` 与 `[answer]` MUST 同构：都是独占一行的头，内容另起——不依赖模型正文是否恰好以前导换行开头（2026-11-26 UAT 人裁，thinking 对齐 answer）。思考 MUST NOT 出现在 stdout（stdout 仍只有模型回复正文与提示符）。

只有思考流、正文走步末回退的那一轮 SHALL 在 `finish_turn` 时补一个 `[answer]` 头行，且 MUST 先封住未收行的思考流再补标记，不让正文标记插进思考流中间；纯无增量的步仍不打标记（既有「空 delta 不触发标记」不变）。

#### Scenario: 思考不进 stdout

- **WHEN** 一次流式调用先发 reasoning 增量再发正文增量
- **THEN** stdout 只有正文；stderr 有 `[thinking]` 与 `[answer]` 头行各一次，`[thinking]` 在 `[answer]` 之前，两个标记各自独占一行

#### Scenario: 正文不带前导换行也不粘连

- **WHEN** 正文增量不以换行开头（如 `content` 是 `答案`）
- **THEN** stderr 以 `[answer]\n` 收尾，正文从头行下一行开始，不与标记粘在同一行

#### Scenario: 思考帧的取消不回归既有判据

- **WHEN** 正文已滚出几个字后按 Ctrl-C
- **THEN** 已显示前缀保留、不补打整段、`[轮] 收尾 ABORTED` 可见、进程回到提示符（`restore-chat-streaming` 的四项判据不变）
