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
