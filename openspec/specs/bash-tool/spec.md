# bash-tool Specification

## Purpose

规定 `bash` 工具的执行契约：一次命令在哪个目录跑、跑多久算超时、输出怎么进日志、命令自己的退出码算什么结果、超时之后被它启动的进程怎么收。

## Requirements

### Requirement: bash 是会改动的工具
系统 SHALL 把 `bash` 注册为会改动的工具：`--sandbox read-only` 下 SHALL 被拒，`ask` 档位下 SHALL 先问人。围栏对 `bash` 的判定只由档位轴给出，边界轴对它恒真（ADR-0008）。

#### Scenario: read-only 下 bash 被拒
- **WHEN** 一次 `--sandbox read-only` 的 run 里模型请求 `bash`
- **THEN** 该调用是 `outcome: DENIED_BY_FENCE` 的 `tool/result` 与一条 `error/fence`（`code: SANDBOX_DENIES_WRITE`），命令没有被执行，工作区里没有任何文件被创建

### Requirement: bash 的工作目录固定为工作区根
系统 SHALL 把命令的工作目录设为工作区根，并 MUST NOT 提供改变工作目录的入参。

#### Scenario: 相对路径落在工作区内
- **WHEN** 一条命令写一个相对路径的文件
- **THEN** 该文件出现在工作区根之下，且 `read` 能用同一个相对路径读到它

### Requirement: bash 的超时默认 30 秒、上限 600 秒
系统 SHALL 用 30 秒作为 `bash` 的默认超时。`bash` 的入参 SHALL 可带 `timeout_seconds`，取值 MUST 是大于 0 且不超过 600 的整数；超出上限 SHALL 是 `TOOL_ARGS_INVALID` 结果且命令不执行。这些数值 MUST NOT 有命令行开关。

#### Scenario: 超过默认超时的命令被打断
- **WHEN** 一条命令运行超过它的超时
- **THEN** 该调用的 `tool/result` 的 `outcome` 是 `TOOL_TIMEOUT`，日志里有一条 `tool_call_id` 配对的 `tool/cancelled`

#### Scenario: 超上限的 timeout_seconds 不启动进程
- **WHEN** `bash` 的入参 `timeout_seconds` 是 601
- **THEN** 结果是 `TOOL_ARGS_INVALID`，且没有任何进程被启动

### Requirement: 命令自己的退出码是内容不是失败结果词
当命令跑完且退出码非 0 时，系统 SHALL 产出 `outcome: OK` 的 `tool/result`，其 content SHALL 含退出码与命令的输出。系统 MUST NOT 为「命令自己失败了」新造结果词。

#### Scenario: 退出码非 0 仍是 OK
- **WHEN** 一条命令以退出码 1 结束并往 stderr 写了内容
- **THEN** `outcome` 是 `OK`，content 里能看到退出码 1 与那段内容

### Requirement: bash 的输出有上限并标记截断
系统 SHALL 限制单次 `bash` 结果进入日志的输出字节数，被截断时 content SHALL 带一个固定的截断标记。截断 MUST NOT 改变 `outcome`，也 MUST NOT 让日志里出现无界的命令输出。输出字节 SHALL 按 UTF-8 解码，无效字节 SHALL 塌成替换字符：系统 MUST NOT 猜平台编码，也 MUST NOT 因解码失败把结果变成失败结果词。照 DSH：子进程输出是 lossy UTF-8（`dsh-subprocess-local/lib/output.js:193` 与 `:232` 的 `Buffer.concat(chunks).toString("utf8")`），只有文件读取是严格的（`dsh-fs-local/lib/index.js:333` 的 `TextDecoder("utf-8", { fatal: true })`）。

#### Scenario: 大输出被截断且可观察
- **WHEN** 一条命令的输出超过上限
- **THEN** content 含截断标记，且其长度不超过上限与标记之和

#### Scenario: 非 UTF-8 输出塌成替换字符
- **WHEN** 一条命令的输出含不构成合法 UTF-8 的字节（例如 Windows 控制台按 GBK 写出的中文）
- **THEN** content 里那些位置是替换字符，`outcome` 仍是 `OK`，日志里没有任何解码失败的记录或失败结果词

### Requirement: 超时或取消之后进程树不得继续运行
系统 SHALL 在 `bash` 超时或被取消之后终止它启动的进程树，MUST NOT 留下仍在运行的后代进程。终止手段是实现细节，MUST NOT 成为规格里的承诺（与「围栏不做 OS 级强制」不冲突：那条禁止的是用 OS 机制实施围栏，不是终止自己启动的进程）。

#### Scenario: 后代进程一起收
- **WHEN** 一条命令启动了一个会持续运行的后代进程，而该命令因超时被打断
- **THEN** 超时之后该后代进程不再运行，也没有在超时之后继续写工作区

### Requirement: bash 的描述点明原生工具优先
`bash` 的描述 SHALL 点明它跑的是真命令（构建、测试、版本控制、进程），列文件、搜内容、读文件这类等价能力 SHALL 引导去用 `glob` / `grep` / `read`。这份描述 MUST 与平台无关：平台相关的那半句只出现在头部的运行环境块里，否则同一份事实会有两个来源（ADR-0029 / ADR-0030）。

#### Scenario: bash 的描述把列文件指给 glob
- **WHEN** 读一次 run 发给模型的工具表里 `bash` 的描述
- **THEN** 描述把列文件与搜内容指给 `glob` 与 `grep`，并点明不要用 `ls` / `grep` / `cat` 这类等价命令

#### Scenario: bash 的描述里没有平台专用命令
- **WHEN** 读这份描述
- **THEN** 它不含 `dir`、`findstr`、`Get-Content` 这类只在某一个平台上成立的字样，也不把「临时写一段脚本」当作推荐手段
