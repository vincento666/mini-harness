## MODIFIED Requirements

### Requirement: bash 的输出有上限并标记截断
系统 SHALL 限制单次 `bash` 结果进入日志的输出字节数，被截断时 content SHALL 带一个固定的截断标记。截断 MUST NOT 改变 `outcome`，也 MUST NOT 让日志里出现无界的命令输出。输出字节 SHALL 按 UTF-8 解码，无效字节 SHALL 塌成替换字符：系统 MUST NOT 猜平台编码，也 MUST NOT 因解码失败把结果变成失败结果词。照 DSH：子进程输出是 lossy UTF-8（`dsh-subprocess-local/lib/output.js:193` 与 `:232` 的 `Buffer.concat(chunks).toString("utf8")`），只有文件读取是严格的（`dsh-fs-local/lib/index.js:333` 的 `TextDecoder("utf-8", { fatal: true })`）。

#### Scenario: 大输出被截断且可观察
- **WHEN** 一条命令的输出超过上限
- **THEN** content 含截断标记，且其长度不超过上限与标记之和

#### Scenario: 非 UTF-8 输出塌成替换字符
- **WHEN** 一条命令的输出含不构成合法 UTF-8 的字节（例如 Windows 控制台按 GBK 写出的中文）
- **THEN** content 里那些位置是替换字符，`outcome` 仍是 `OK`，日志里没有任何解码失败的记录或失败结果词
