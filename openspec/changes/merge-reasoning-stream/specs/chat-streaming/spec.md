# Spec Delta

## MODIFIED Requirements

### Requirement: 正文增量写 stdout，`[answer]` 每轮一次

`--stream` 时，非空正文 delta SHALL 写 stdout，并在每个 delta 之后 flush。每一轮第一次非空正文 delta 之前，系统 SHALL 在 stderr 写一次 `[answer]` 头行——标记独占一行、自带换行——并 flush；同一轮内后续步的正文 MUST NOT 再写 `[answer]`。正文 MUST NOT 写 stderr；`[answer]` MUST NOT 写 stdout，也 MUST NOT 写进事件日志。头行自带换行后，正文从头行下一行开始，MUST NOT 依赖模型正文恰好以前导换行开头才与标记分行（2026-11-26 UAT 人裁：`[thinking]` 与 `[answer]` 同构）。

#### Scenario: 增量按序落到 stdout

- **WHEN** fixture 的 `deltas` 是 `["你", "好"]`，`content` 是 `你好`
- **THEN** stdout 里 `你` 在 `好` 之前出现，且 `你` 出现时该轮尚未结束（发生在轮末打印之前）

#### Scenario: 一轮两步只有一个标记

- **WHEN** 一轮里两步都产生非空正文 delta
- **THEN** stderr 里 `[answer]` 头行恰出现一次

#### Scenario: 正文不带前导换行也不粘连

- **WHEN** provider 的正文增量不以换行开头
- **THEN** stderr 以 `[answer]\n` 收尾，正文从头行下一行开始

#### Scenario: 空 delta 不触发标记

- **WHEN** provider 只发空字符串 delta，最终 `content` 非空
- **THEN** stderr 里没有 `[answer]`，正文在轮末按回退规则打印

### Requirement: 流式投影裁掉回复正文的首尾空白

`--stream` 下 stdout 的正文投影 SHALL 裁掉**本轮**回复正文的首尾空白：本轮第一个可见正文增量（流式或步末回退）写出前 MUST 先去掉前导空白；正文开始后的纯空白增量 MUST 先攒住，等下一个可见增量到达时写出，轮末仍未被接上的按尾随空白丢弃——段与段之间的空行因此保留，只裁首尾。日志里的 `model/response.content` 与 `blocks` MUST 保持 provider 原文：裁剪只发生在渲染投影，MUST NOT 写回日志，也 MUST NOT 改动去重、回退与「空 delta 不触发标记」的既有判据。`--no-stream` 是旧行为投影，MUST NOT 裁剪。`[thinking]` 头行下的第一段思考同理裁前导空白；思考的尾随空白不裁（思考段以收行结束）。这是 2026-11-27 UAT 后的人裁，依据主流终端/网页助手「裁显示、留原文」的通行做法（它们的输出经 Markdown 渲染层，首尾空白天然不可见）。

#### Scenario: 前导空白不出现在头行下

- **WHEN** 本轮正文增量以前导换行开头（如 provider 依次发 `"\n\n"`、`"你好"`）
- **THEN** stderr 的 `[answer]` 头行下一行直接是正文，stdout 正文不以空白开头；日志 `content` 仍是 `"\n\n你好"` 原文

#### Scenario: 尾随空白被裁、中段空行保留

- **WHEN** 正文增量在中段含 `"\n\n"`、并以纯空白增量收尾
- **THEN** stdout 里段间空行照写，轮末输出以最后一个可见字符结尾（只剩轮末换行）；日志 `content` 保留尾随空白原文

#### Scenario: 步末回退同样裁前导

- **WHEN** 本轮没有流过任何可见正文、步末回退的 `content` 带前导空白
- **THEN** stdout 从可见字符开始；日志 `content` 保持原文
