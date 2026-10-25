# 平台事实进受保护头部，并且带上本平台的命令建议

`session/start` 的 payload 记 `platform`（`os` 与 `shell`），受保护头部据此折出一块「运行环境」，除了事实还带一句建议——**先**点原生工具（列文件用 `glob`、搜内容用 `grep`、读文件用 `read`），**再**点这个平台的 shell 命令（Windows 上 `dir` / `findstr` / `Get-Content`，POSIX 上 `ls -R` / `tail`；`grep` 已在前一句点过，不重复）。理由：2026-10-24 的人手验收里模型在 `cmd.exe` 上连跑 `ls`、`wc`，靠试错才在屏幕上写出「这是一台 Windows shell」；ADR-0009 接受的那条代价（两端 shell 语义不同、命令失败是内容不是异常）在模型不知道平台时表现为**纯浪费**。主流 harness 是同一族做法：Claude Code 的 Environment 块给 `Platform` 与 `Shell`（2.1.268 把这块从系统提示挪进追加上下文），Codex 的 `environment_context` 给 OS、shell 与 sandbox，Gemini CLI 直接按 `process.platform` **生成平台专用措辞**——win32 上把 `grep` / `tail` / `head` 换成 `type` / `findstr` / `Get-Content` / `Select-String`，子 agent 的例子用 `dir /s` 而不是 `ls -R`（[google-gemini/gemini-cli#18351](https://github.com/google-gemini/gemini-cli/pull/18351)）。事实写进日志再折回、而不是每轮注入，是为了守住逐点重放的判据（M5）。

Considered options：只给事实不给建议（Claude Code 的形状）——否，UAT 里失败的正是「知道自己是 Windows」之后的下一步；每轮注入（主流形状）——否，那样折叠结果就不再只依赖日志前缀；改 `SYSTEM_PROMPT` 常量——否，所有旧日志会 `REPLAY_MISMATCH`；把平台事实写进工具描述——否，描述不进折叠结果、日志里也看不见，而描述只放与平台无关的那一半指引（ADR-0030）。

Consequences：头部多一块，新会话的 `header_fingerprint` 与 `context/assembled` 跟着变；`session/start` 没有 `platform` 的旧日志头部逐字节不变、重放照旧。ADR-0009 那条代价仍在（`bash` 的语义差异没消失），只是不再由试错发现。
