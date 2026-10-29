# tool-pipeline Specification

## Purpose

工具执行的可观察契约：六段派发、平台命令 runner、并发类别与 barrier、read 窗口、bash/搜索预算与 spill、批内日志前缀复用。

## Requirements

### Requirement: 工具派发走六段管线

系统 SHALL 按 `pre-execute → guard → execute → post-execute → finalizeContent → tools/result` 六段执行一次工具调用；每一段 SHALL 只产出「继续 / 结果」两种出口，失败也是结果，MUST NOT 抛出未捕获异常打断回合。`guard` SHALL 复用现有围栏与 approval 语义；`finalizeContent` 是 `bash` 的 16 KiB/尾部/spill 收尾点，`read`/`grep`/`glob` 的窗口与条数上限在各自工具内生效。

#### Scenario: 六段顺序可观察

- **WHEN** 一次成功的 `read` 调用经过派发
- **THEN** 派发按 `pre-execute → guard → execute → post-execute → finalizeContent` 的顺序执行，最终只写一条 `tool/result`

#### Scenario: execute 失败不进 post-execute

- **WHEN** 工具执行段返回 `TOOL_IO_FAILED`
- **THEN** 结果带上该 outcome，后续段不执行，回合继续

### Requirement: CommandRunner 是 injectable 的缝

系统 SHALL 通过一个 `CommandRunner` 缝执行外部命令；至少提供 win32 与 posix 两个 adapter。命令执行器不可用时 SHALL 产出 `FenceCode.SANDBOX_UNAVAILABLE`，CLI 以退出码 3 结束，且 MUST NOT 回退到未受限的 runner。

#### Scenario: runner 不可用

- **WHEN** 注入一个构造即失败的 `CommandRunner` 并执行一次 `bash`
- **THEN** `error/fence` 的 `code` 为 `SANDBOX_UNAVAILABLE`，退出码为 3，命令没有真正执行

#### Scenario: 平台 adapter 选择

- **WHEN** 在 win32 上运行一次 `bash`
- **THEN** 使用的是 win32 adapter；在 posix 上使用 posix adapter

### Requirement: 工具并发类别与 barrier

`ToolDefinition` SHALL 声明 `ConcurrencyClass`：`parallel`（只读/无副作用）或 `exclusive`（会改动/需独占）。同一时刻在跑的 `parallel` SHALL ≤ 8；`exclusive` SHALL ≤ 1，并且是 barrier：它之前声明的调用先完成，之后声明的调用等它完成。`tool/call` SHALL 按声明顺序落盘，`tool/result` SHALL 按完成顺序落盘。

#### Scenario: 并行只读批次真并发

- **WHEN** 同一批声明 4 个 `parallel` 调用，每个阻塞 0.1 s
- **THEN** 批次 wall-clock 明显小于串行 0.4 s，且同时最多 8 个在跑

#### Scenario: 改动调用是 barrier

- **WHEN** 同一批是 `read → write → read`
- **THEN** 第一个 `read` 在 `write` 开始前完成，第三个 `read` 在 `write` 完成后开始

#### Scenario: 结果按完成顺序

- **WHEN** 两个 `parallel` 调用完成顺序与声明顺序相反
- **THEN** 两条 `tool/result` 按完成顺序落盘，`tool/call` 仍按声明顺序

### Requirement: read 是 capped window，不落 spill

`read` SHALL 同时受 `readLimit`（默认 2000 行）、`readMaxBytes`（默认 51200 字节）与 `readMaxLineLength`（默认 2000 字符/行）约束，先到者生效。超出时 SHALL 返回截断窗口、固定 capped footer 与 `offset=<next>` 续读提示；单行超长 SHALL 带 `... (line truncated to <max> chars)` mark。`read` MUST NOT 写 spill 文件；完整内容通过继续 `read` 同一路径获得，但被 `readMaxLineLength` 截断的单行剩余部分不可恢复。

#### Scenario: 超长单行只截该行

- **WHEN** `read` 一个包含超长单行的文件
- **THEN** 该行截到 2000 字符并带 mark，窗口仍可按 `offset` 继续读

#### Scenario: 字节上限结束窗口

- **WHEN** 所选行合计超过 51200 字节
- **THEN** 结果以 capped footer 结束并给出下一个 `offset`；没有 spill 路径

#### Scenario: 行数上限照旧

- **WHEN** `read` 不带 `limit` 读取超过 2000 行
- **THEN** 只返回前 2000 行与 `offset=2001` 的续读提示

### Requirement: bash 与搜索工具超限落 spill

`bash` 的输出上限 SHALL 保持 16 KiB，超限时 SHALL 保留可见尾部并写完整输出到工作区内 spill，结果带 `[output truncated; full output: <path>]`。`grep` SHALL 受 `grepMaxMatches=250`、`grepMaxLineBytes=2000` 与 `rawOutputMaxBytes=20000000` 约束；`glob` SHALL 受 `globMaxResults=100` 约束。超出 inline 上限时 SHALL 留 marker，完整结果 MAY 落 spill。spill 路径解析后 MUST 仍在工作区根内；M10 不做 GC。

#### Scenario: bash 保留尾部并 spill

- **WHEN** `bash` 输出超过 16 KiB
- **THEN** 结果保留尾部、带 `[output truncated; full output: <path>]`，完整输出可从 spill 读回

#### Scenario: grep 超限

- **WHEN** `grep` 命中超过 250 条
- **THEN** inline 只保留上限内的匹配并带 marker；超过 `grepMaxLineBytes` 的单行被截断

#### Scenario: glob 超限

- **WHEN** `glob` 命中超过 100 条
- **THEN** inline 只保留上限内的路径并带 marker

#### Scenario: spill 不越界

- **WHEN** 一次工具结果需要 spill
- **THEN** spill 路径解析后仍在工作区根内

### Requirement: read 与 edit 共用截断窗口

`read` 的行/字节/单行上限生效后，`edit` 的「写前必读」与 CAS 判定 SHALL 使用与 `read` 相同的截断窗口；否则合法编辑 MUST NOT 被误报 `STALE_EDIT`。

#### Scenario: 截断窗口内编辑不误报

- **WHEN** 模型先 `read` 一个超长文件（被行/字节/单行上限截断），再在窗口内做 `edit`
- **THEN** 编辑被接受，不出现 `STALE_EDIT`

### Requirement: 一批调用共享一次日志前缀

同一批工具调用 SHALL 只读取一次日志前缀，并把同一份「已读过」判定传给批内每个调用；MUST NOT 让每个工具各自 `read_events`。

#### Scenario: 批内只读一次前缀

- **WHEN** 同一批有 4 个工具调用
- **THEN** 日志前缀只读取一次，四个调用都使用同一份前缀
