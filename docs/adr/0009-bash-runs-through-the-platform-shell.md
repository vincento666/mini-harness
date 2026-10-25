# bash 经平台 shell 执行，超时之后按平台终止它启动的进程树

`bash` 用 `asyncio.create_subprocess_shell` 跑命令：Windows 落到 `cmd.exe /c`、POSIX 落到 `/bin/sh -c`，cwd 固定工作区根；超时或取消之后按平台收掉整棵树——POSIX 用 `start_new_session=True` 加 `os.killpg(..., SIGKILL)`，Windows 用 `taskkill /T /F /PID`。裁决：**接受两端 shell 语义不同**这条代价，因此每条 bash 判据只用平台中立命令（`python <文件>`，`-c` 的引号在两端语义不同）。

Considered options：不经 shell 的 `create_subprocess_exec` + `shlex.split`——否，模型写的命令带管道与重定向，不经 shell 就不可用，而 `shlex` 的 POSIX 语义在 Windows 上不对；只 kill 直接子进程——否，实测后代进程握着管道继续写工作区，`process.wait()` 还会被它拖到后代自然跑完；OS 级 job object / landlock——否，MVP 明确不做 OS 级沙箱。

与 fences 主规格「围栏不做 OS 级强制（MUST NOT 依赖 job object）」不冲突：那条禁止的是**用 OS 机制实施围栏**，本条终止的是**自己启动的进程**，两者不同轴。代价写清楚：模型在 Windows 上写 POSIX 语法会得到命令失败，那是内容不是 harness 失败；不变量 E 的边界轴对 bash 恒真（ADR-0008），所以「命令实际写到哪儿」没有任何机制约束它。

2026-10-25：这条代价还在，但不再由试错发现——平台事实与本平台的命令建议进受保护头部，见 ADR-0029；等价能力优先用原生工具、不用临时脚本兜底，见 ADR-0030。
