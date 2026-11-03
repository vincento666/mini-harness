# Spec Delta

## ADDED Requirements

### Requirement: chat 的 `--stream` 是可选 shell 模式

`minihns chat` SHALL 接受互斥的 `--stream` 与 `--no-stream`；默认 MUST 是 `--stream`（shell 体验）。`--no-stream` 的 stdout、stderr、日志、退出码 MUST 与今天的阻塞输出逐点相同。`--stream` SHALL 复用 `run_turn_segment` 的 `on_delta` / `on_reasoning`，MUST NOT 新造 provider 或内核流式路径。

#### Scenario: 默认不流式

- **WHEN** 执行 `minihns chat` 不传流式 flag，stdin 是管道
- **THEN** stdout 仍是完整 `model/response` 的正文投影，与今天一致

#### Scenario: 显式流式

- **WHEN** 执行 `minihns chat --stream`，fixture 声明 `deltas: ["你", "好"]`
- **THEN** stdout 在最终 response 前依次出现 `你`、`好`，且最终 response 后不再重复整段正文

### Requirement: 正文与思考在 shell 里分流

`--stream` 时，正文 delta SHALL 写 stdout；reasoning delta SHALL 写 stderr，并带固定 `[thinking]` 前缀。reasoning MUST NOT 写 stdout，正文 MUST NOT 写 stderr 的思考行。MUST NOT 把 reasoning 当最终回答。

#### Scenario: 思考走 stderr

- **WHEN** `--stream` 且 provider 先发 reasoning delta
- **THEN** stderr 出现 `[thinking]` 行，stdout 没有该思考文本

#### Scenario: 正文走 stdout

- **WHEN** `--stream` 且 provider 发正文 delta
- **THEN** stdout 出现正文片段，stderr 没有该正文片段

### Requirement: 流式去重与无 delta 回退

`--stream` 时，如果某段已经流过正文 delta，段结束时 MUST NOT 再打印该段最终 `content` 的整段副本；如果没有流过任何正文 delta（provider 不流式或只发空 delta），段结束时 SHALL 回退到现有日志投影打印最终正文。提示符仍只打印一次，不得因流式重复。

#### Scenario: 有 delta 不重复

- **WHEN** 一个段流过 `你`、`好`，最终 content 是 `你好`
- **THEN** stdout 只出现 `你好` 一次

#### Scenario: 无 delta 回退

- **WHEN** `--stream` 但 provider 不发正文 delta，最终 content 是 `答案`
- **THEN** stdout 在该段结束打印 `答案`，不留下空输出

### Requirement: 流式下的取消不撤回已输出内容

`--stream` 时段内 Ctrl-C SHALL 按既有段级取消收尾；已经写出的 stdout 片段 MUST NOT 被撤回，也 MUST NOT 再补一整段最终 content。日志仍按 interrupted/ABORTED 规则落账；stderr 的状态行照旧。

#### Scenario: 取消保留已显示前缀

- **WHEN** `--stream` 已显示正文 `半` 后收到 SIGINT
- **THEN** stdout 保留 `半`，不追加最终整段；日志按取消规则收尾，进程回到提示符

### Requirement: 流式不改变日志与 provider 契约

`--stream` MUST NOT 写 `model/delta` / `reasoning/delta` 到日志；事件类型、`model/response.blocks`、取消/失败形状与 `--no-stream` 相同。Provider 仍只经 `generate` 调用。

#### Scenario: 日志无 delta

- **WHEN** `--stream` 跑完一段
- **THEN** 日志里没有 `model/delta` 或 `reasoning/delta`，只有正常的 durable 记录
