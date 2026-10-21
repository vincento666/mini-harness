# file-tools Specification

## Purpose
定义五个文件工具（`read` / `write` / `edit` / `glob` / `grep`）的输入契约、执行结果词表，以及「写前必读」与 `edit` 的比较交换（CAS）语义：工具失败一律是结果，不是异常。

## Requirements

### Requirement: 五个文件工具注册进工具表
系统 SHALL 内置 `read`、`write`、`edit`、`glob`、`grep` 五个文件工具定义，并把进入本次工具表的那些工具的名字与描述送进每次模型调用。它们是否进入本次工具表由装配决定（见 `config-layering`）；未注册的工具名 SHALL 仍产出 `outcome: UNKNOWN_TOOL` 的 `tool/result`。

#### Scenario: 注册表非空
- **WHEN** 一次没有配置文件的 run 写出 `session/start`
- **THEN** 其 payload 的 `tools` 含上述五个名字（同一份工具表里还有 `bash`，它由 `bash-tool` 规定）

#### Scenario: 未注册的名字仍是 UNKNOWN_TOOL
- **WHEN** 模型调用一个不在本次工具表里的工具名
- **THEN** 该调用产出 `outcome: UNKNOWN_TOOL` 的 `tool/result`，且回合继续

#### Scenario: 被白名单筛掉的文件工具不在工具表里
- **WHEN** 配置文件写 `tools = ["read"]`，模型调用 `grep`
- **THEN** 该调用产出 `outcome: UNKNOWN_TOOL` 的 `tool/result`，且回合继续

### Requirement: 工具入参路径相对工作区根解析
系统 SHALL 把文件工具的 `file_path` 与 `path` 参数相对工作区根解析；给出绝对路径时 SHALL 按绝对路径解析。解析 MUST NOT 跟随符号链接或目录 junction 逃出工作区根（判定结果由 `fences` 规定）。

#### Scenario: 相对路径落在工作区内
- **WHEN** 工作区为 `<dir>` 且 `read` 的 `file_path` 为 `notes/a.md`
- **THEN** 读取的是 `<dir>/notes/a.md`

#### Scenario: 绝对路径在工作区外仍可被读
- **WHEN** `read` 的 `file_path` 是工作区之外的一个绝对路径
- **THEN** 结果是 `OK`（读类工具不受工作区边界约束，见 `fences`）

### Requirement: 工具参数不合法是 TOOL_ARGS_INVALID 结果
系统 SHALL 在执行前校验工具入参（必填、类型、取值范围）；不合法 SHALL 产出 `outcome: TOOL_ARGS_INVALID` 的 `tool/result`，内容里写明缺哪个参数或哪个取值不合法，MUST NOT 抛出异常，也 MUST NOT 触碰任何文件。

#### Scenario: read 缺 file_path
- **WHEN** 模型调用 `read` 且 arguments 里没有 `file_path`
- **THEN** 结果是 `TOOL_ARGS_INVALID`，工作区里没有任何文件被创建或修改

#### Scenario: grep 的正则不合法
- **WHEN** 模型调用 `grep` 且 `pattern` 是非法正则
- **THEN** 结果是 `TOOL_ARGS_INVALID`，内容里含该正则的解析错误

### Requirement: 执行段的文件 I/O 失败是 TOOL_IO_FAILED 结果
系统 SHALL 把执行段的文件系统错误塌成 `outcome: TOOL_IO_FAILED` 的 `tool/result`：内容里写明是哪个工具、哪个路径、什么错误，MUST NOT 让异常逃出派发管线打断回合。这类结果 MUST NOT 被写成围栏拒绝——它没有对应的 `error/fence`。

#### Scenario: 父路径是已存在的文件
- **WHEN** `write` 的 `file_path` 为 `a.md/b.md` 而 `a.md` 是一个文件
- **THEN** 结果是 `TOOL_IO_FAILED`，没有任何文件被创建或改写，回合继续走到 `turn/end`

#### Scenario: I/O 失败不写 error/fence
- **WHEN** 任一文件工具因 I/O 失败产出 `TOOL_IO_FAILED`
- **THEN** 该调用不伴随 `error/fence`，`session/end` 的停止原因不是 `FENCE_DENIED`

### Requirement: read 返回带行号的文本窗口
系统 SHALL 让 `read` 按 `file_path` 读取 UTF-8 文本，返回带行号前缀（`<行号>: <内容>`）的窗口；`offset` 默认 1、`limit` 默认 2000，两者 MUST 是 ≥ 1 的整数。

#### Scenario: 整读带行号
- **WHEN** 对一个 3 行的文件调用 `read` 且不带 `offset` 与 `limit`
- **THEN** 结果是 `OK`，内容三行分别以 `1: `、`2: `、`3: ` 开头

#### Scenario: offset 与 limit 取窗口
- **WHEN** 对同一文件调用 `read` 且 `offset` 为 2、`limit` 为 1
- **THEN** 结果只含第 2 行且其行号为 2

#### Scenario: 路径不存在是结果
- **WHEN** `read` 的 `file_path` 指向不存在的文件
- **THEN** 结果是 `PATH_NOT_FOUND`，内容里含所查找的路径

#### Scenario: 目录与非文本是结果
- **WHEN** `read` 的目标是目录，或不是合法 UTF-8 文本
- **THEN** 结果分别是 `IS_A_DIRECTORY` 与 `NOT_UTF8_TEXT`，文件内容不变

### Requirement: write 覆盖已存在文件前必须先读过
系统 SHALL 让 `write` 按 `file_path` 写入给定 `content`（UTF-8、覆盖式、必要时创建父目录）。目标文件已存在时，该派发点之前 MUST 已有对该路径且 `outcome` 为 `OK` 的 `read`，否则 SHALL 产出 `outcome: WRITE_WITHOUT_READ` 的 `tool/result` 且该文件字节不变。目标不存在时 SHALL 直接创建。

#### Scenario: 读过之后覆盖成功
- **WHEN** 同一 session 里先 `read` 某文件再 `write` 它
- **THEN** 结果是 `OK`，且文件内容等于给定的 `content`

#### Scenario: 没读过就覆盖被拒
- **WHEN** 本 session 没有 `read` 过某已存在文件就直接 `write` 它
- **THEN** 结果是 `WRITE_WITHOUT_READ`，该文件字节不变

#### Scenario: 新文件不需要先读
- **WHEN** `write` 的目标在派发点之前不存在
- **THEN** 结果是 `OK` 且文件被创建

#### Scenario: 目标是目录是 IS_A_DIRECTORY
- **WHEN** `write` 的 `file_path` 指向一个目录
- **THEN** 结果是 `IS_A_DIRECTORY`，该目录的内容不变

### Requirement: edit 是字面替换且受 CAS 约束
系统 SHALL 让 `edit` 在已 `read` 过的文件里做字面替换：`old_string` MUST 恰好出现一次，除非 `replace_all` 为真。`edit` MUST 要求该派发点之前有对该路径 `outcome` 为 `OK` 的 `read`，且替换时的文件内容 MUST 与该次 `read` 返回的内容一致。

#### Scenario: 唯一匹配替换成功
- **WHEN** 读过某文件后 `edit` 它，`old_string` 在文件里恰出现一次
- **THEN** 结果是 `OK`，该字面串被 `new_string` 替换且只替换这一处

#### Scenario: 目标不存在与多处匹配是两个不同的结果
- **WHEN** `old_string` 在文件里出现 0 次，或出现多次而 `replace_all` 为假
- **THEN** 结果分别是 `EDIT_TARGET_NOT_FOUND` 与 `EDIT_TARGET_AMBIGUOUS`，文件内容不变

#### Scenario: 原文与读到时不一致是 STALE_EDIT
- **WHEN** 读过某文件后该文件在 session 之外被改动，再对它 `edit`
- **THEN** 结果是 `STALE_EDIT`，文件不被改写

#### Scenario: 没读过就 edit 被拒
- **WHEN** 本 session 没有 `read` 过某文件就直接 `edit` 它
- **THEN** 结果是 `WRITE_WITHOUT_READ`

### Requirement: glob 按模式返回工作区内的相对路径
系统 SHALL 让 `glob` 按 glob 模式匹配文件（MUST NOT 返回目录），返回相对工作区根的路径列表，按修改时间从新到旧排序，最多 100 条；无匹配 SHALL 是 `outcome: OK` 且内容说明没有匹配。`path` 给出的搜索根 MUST 是目录：不存在 SHALL 是 `PATH_NOT_FOUND`，是文件 SHALL 是 `NOT_A_DIRECTORY`。

#### Scenario: 匹配与排序
- **WHEN** 对含 5 个 `.md` 的 fixture 仓库调用 `glob` 且 `pattern` 为 `**/*.md`
- **THEN** 结果是 `OK` 且内容含这 5 个相对路径

#### Scenario: 无匹配不是失败
- **WHEN** `pattern` 没有任何文件匹配
- **THEN** 结果是 `OK`，内容说明没有匹配

#### Scenario: 搜索根不存在与不是目录是两个结果
- **WHEN** `path` 指向不存在的路径，或指向一个文件
- **THEN** 结果分别是 `PATH_NOT_FOUND` 与 `NOT_A_DIRECTORY`

### Requirement: grep 返回带文件与行号的匹配行
系统 SHALL 让 `grep` 按正则搜索文本文件内容，返回 `文件:行号: 行内容` 形式的匹配行，最多 250 条；无匹配 SHALL 是 `outcome: OK` 且内容说明没有匹配。`path` 给出的搜索根 MUST 是目录：不存在 SHALL 是 `PATH_NOT_FOUND`，是文件 SHALL 是 `NOT_A_DIRECTORY`。

#### Scenario: 命中带文件与行号
- **WHEN** fixture 仓库里恰有 3 行含 `TODO` 且调用 `grep` 搜 `TODO`
- **THEN** 结果是 `OK` 且内容含这 3 条 `文件:行号: 行内容`

#### Scenario: 无命中不是失败
- **WHEN** 搜索一个不存在于任何文件里的词
- **THEN** 结果是 `OK`，内容说明没有匹配

#### Scenario: 搜索根是文件不是目录
- **WHEN** `grep` 的 `path` 指向一个文件
- **THEN** 结果是 `NOT_A_DIRECTORY`，没有任何文件被读取或改写

### Requirement: 文件层工具结果词表在 M2 定稿且每个值可达
`tool/result.outcome` 的文件层取值 SHALL 是 `OK`、`UNKNOWN_TOOL`、`TOOL_ARGS_INVALID`、`PATH_NOT_FOUND`、`IS_A_DIRECTORY`、`NOT_A_DIRECTORY`、`NOT_UTF8_TEXT`、`WRITE_WITHOUT_READ`、`STALE_EDIT`、`EDIT_TARGET_NOT_FOUND`、`EDIT_TARGET_AMBIGUOUS`、`TOOL_IO_FAILED`；围栏与 approval 的拒绝取值由 `fences` 规定。词表外的值 MUST NOT 被写出；M1 的 `NOT_IMPLEMENTED` 被移除。

#### Scenario: 每个值都有可达判据
- **WHEN** 跑完 M2 的 seam ③ 与 seam ② 测试
- **THEN** 上述每个取值都至少被一条测试断言到

#### Scenario: NOT_IMPLEMENTED 不再出现
- **WHEN** 跑完 M2 的全部场景
- **THEN** 没有任何 `tool/result` 的 `outcome` 为 `NOT_IMPLEMENTED`

### Requirement: 「已读过」判定只由日志前缀派生
系统 SHALL 把「某路径算不算读过」判定为日志事实的派生：当且仅当该派发点之前存在一条针对该路径且 `outcome` 为 `OK` 的 `read`。系统 MUST NOT 维护与该判定并列的进程内真源；新的 session MUST NOT 继承上一个 session 的已读状态。

#### Scenario: 跨 session 不继承
- **WHEN** session A 读过某文件，随后新起 session B 直接 `write` 它
- **THEN** B 里该调用的结果是 `WRITE_WITHOUT_READ`

#### Scenario: 同一前缀重算判定相同
- **WHEN** 对同一份日志的同一前缀重算该判定两次
- **THEN** 两次判定结果相同
