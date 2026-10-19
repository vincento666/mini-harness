# M3 人手验收与本机验证边界

change `m3-bash-concurrency-timeout`。这份记录分两半：**本机（Windows）跑不到的判据**（人裁决 2026-10-19：Windows 的 Ctrl-C 黑盒不在 M3 做，缺口记账而不是假造）与**人手验收**（拿它办一件真事，不进 CI，也不替代门禁那四道）。

## 本机跑不到的判据（2026-10-19 记录）

| 判据 | 在哪儿 | Windows 侧现状 | Linux 侧现状 |
|---|---|---|---|
| 真实 SIGINT → 退出码 5 + `tool/cancelled` + `error/abort` + `session/end(ABORTED)` | `tests/test_cli_run.py::test_sigint_in_a_real_subprocess_exits_with_five`（seam ⑥） | `skipif sys.platform == "win32"`：Windows 的 CTRL_C_EVENT 黑盒需要真实控制台进程组，本机 M2 的 tty smoke 已经证明这条路走不通（ConPTY 路线 `UpdateProcThreadAttribute` 恒返回 87） | 只在 CI 的 `ubuntu-latest` 上跑（tasks 7.1–7.2）；本机没有可用的 Linux（Docker Desktop 未启动，WSL 只有 `docker-desktop` 发行版） |
| 取消打断正在执行的 `bash`：进程树收掉 | `tests/test_turn_cancel.py::test_a_cancel_interrupts_the_call_that_is_running`（seam ①，判据是「命令跑满 1 秒后自己落一个 `leaked.txt`」） | 跑绿：Windows 走 `taskkill /T /F /PID` | 走 `os.killpg` + `SIGKILL`，同样只在 CI 上跑 |
| 超时收进程树 | `tests/test_bash_tool.py`（seam ③） | 跑绿（Windows 分支） | 同上，Linux 分支在 CI 上跑；本机这一半未覆盖（D9：两端分别报告） |
| 符号链接 / junction 的键规范化 | `tests/test_fences.py::test_a_symlink_key_resolves_to_its_target`（seam ②） | 本机不允许创建符号链接，skip | CI 的 `ubuntu-latest` 上不再 skip |

**这条边界是裁决的结果，不是遗漏**：Windows 的 Ctrl-C 黑盒需要「真实控制台 + CTRL_C_EVENT + 进程组」，本机 M2 已经实测走不通；M3 用 seam ① 注入 cancel 的判据覆盖取消语义本身，用 seam ⑥ 的 Linux 判据覆盖真实信号路径，Windows 侧只保留 `sigint_handler` 的安装与恢复判据（`tests/test_cli_run.py::test_the_cli_installs_and_restores_the_sigint_handler`）。

## 人手验收（tasks 8.1–8.2）

**状态：待跑，清单已备好（2026-10-19）。** 形状沿用 `docs/verification/m1-m2-manual-smoke.md`：场景表 + 可粘贴命令 + 观察点；实际列留空，跑完贴回来由我按 `docs/verification/m4-real-provider-manual.md` 的写法记进本节。不进 CI，也不替代门禁那四道。

**前提**：真终端（Windows PowerShell，仓库根 `S:\Develop\mini-harness`）。端点 `http://127.0.0.1:8300/v1`、模型 `qwen3.8-flash-next-iq3_xxs`，密钥走 `--api-key-env MINIHNS_STRATA_KEY`（值不落进任何记录）。8300 是单流 FIFO 且与 DSH 共用，prompt 短、`--max-turns 6`、一次只跑一个 session。

**工作区**：`.tmp/m3-manual/`（gitignored，已备好）——`notes/a.md` 与 `notes/b.md` 各 3 行、`count_lines.py`（真实检查命令，产出 `counts.txt`）、`slow.py`（睡 45 秒并拉一个同样睡 45 秒的子进程）、`README.md`。跑之前 `counts.txt` 不存在。

### 场景 A（8.1）：真事 + 并发派发 + 落盘顺序

不带 `--yes`：`bash` 算会改动的工具，真 tty 下它会停在人跟前。

```
uv run python -m mini_harness.cli.main run `
  -p "用 bash 跑 python count_lines.py，然后读 counts.txt；再同时读 notes/a.md 与 notes/b.md，核对 counts.txt 里的行数与两个文件各自的行数是否一致，不一致就说出来。" `
  --provider openai --base-url http://127.0.0.1:8300/v1 `
  --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_STRATA_KEY `
  --workspace .tmp/m3-manual --session-dir .tmp/m3-manual/sessions `
  --max-turns 6
```

| 观察点 | 期望 | 实际 |
|---|---|---|
| 提问 | 跑到 `bash` 前停在终端前，一行「允许 bash 跑 python count_lines.py，输入 y 或 n：」；答 `y` 之后进程才起 | |
| 退出码 / 墙钟 / session id | 0 | |
| `bash` 的结果 | `tool/result` 的 `outcome=OK`，content 第一行「退出码 0」，后面是 `wrote counts.txt` 与两行计数 | |
| cwd 固定在工作区根 | `.tmp/m3-manual/counts.txt` 出现（命令里的相对路径落在工作区根，不是仓库根） | |
| 并发派发 | 同一回合两个 `read`：两条 `tool/call` 按声明顺序、两条 `tool/result` 按声明顺序 | |
| 成组 | 每个 `tool_call_id` 自己的 `tool/call` →（`approval/request` → `approval/response` →）`tool/result` 相对顺序成立；不同调用的组可以交错，不要求连续 | |
| 截断标记 | 不出现 `[输出已截断]`（输出远小于 16384 字节） | |
| 收尾 | 末回合 `turn/end` 与 `session/end` 都是 `MODEL_COMPLETED` | |

取证用这个脚本（一次给出 session id、记录数、由日志时间戳算出的墙钟、事件序列、尾部 6 条原文、还活着的 `python` 进程）：

```
powershell -NoProfile -ExecutionPolicy Bypass -File docs/verification/m3-bash-manual-inspect.ps1
```

两条使用注意，都是实测踩到的：

1. **先 `echo "exit=$LASTEXITCODE"` 再跑脚本**——脚本里的外部命令会覆盖退出码，而退出码正是场景 C 的判据。
2. 脚本里的字符串一律 ASCII：Windows PowerShell 5.1 把没有 BOM 的 `.ps1` 当 ANSI 读，中文标题会碎成 `浜嬩欢搴忓垪` 这种样子。

不想用脚本就用这一条（同样不能省 `-Encoding UTF8`：默认按 ANSI 读时日志里的中文碎成无效 JSON，`ConvertFrom-Json` 报错之后 `$e` 还是上一条，输出看着正常其实少了几行）：

```
$log = Get-ChildItem .tmp/m3-manual/sessions/*.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content $log -Encoding UTF8 | ForEach-Object { $e = $_ | ConvertFrom-Json; '{0,18}  {1}  {2}' -f $e.type, $e.payload.tool_call_id, $e.payload.outcome }
```

另一条路是 `uv run python -m mini_harness.cli.main replay <session_id> --session-dir .tmp/m3-manual/sessions`：它打 `verified seq=…: OK` 与每回合的 `stop_reason`，不打工具顺序。

### 场景 B（8.2 之一）：一条故意超时的命令

```
uv run python -m mini_harness.cli.main run `
  -p "用 bash 跑 python slow.py，然后告诉我它发生了什么。" `
  --provider openai --base-url http://127.0.0.1:8300/v1 `
  --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_STRATA_KEY `
  --workspace .tmp/m3-manual --session-dir .tmp/m3-manual/sessions `
  --max-turns 6 --yes
```

| 观察点 | 期望 | 实际 |
|---|---|---|
| 墙钟 | 约 30 秒就出结果，不是 45 秒 | |
| 日志 | `tool/cancelled`（payload 只有 `turn_id` 与 `tool_call_id`，没有命令输出）紧跟一条 `tool/result`，`outcome=TOOL_TIMEOUT` | |
| 回合继续 | 超时之后模型还有回合，`session/end` 不是 `ABORTED`，退出码 0 | |
| 进程树收干净 | 跑完立刻 `Get-CimInstance Win32_Process -Filter "Name like 'python%'" \| Select-Object ProcessId, CommandLine`：只剩 harness 自己那一条（`-m mini_harness.cli.main`），没有 `slow.py`、也没有它打印出来的那个 child pid 对应的 `-c "import time…"` | |
| 默认值与开关 | 不给 `timeout_seconds` 时是 30 秒；`minihns run --help` 里没有改变它的开关 | |

### 场景 C（8.2 之二）：一次 Ctrl-C

同一条命令，在 `bash` 正在跑的时候按 Ctrl-C。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 退出码 | `$LASTEXITCODE` 是 5 | |
| 日志尾部 | `tool/cancelled` → `tool/result`（`TOOL_CANCELLED`）→ `error/abort` → `turn/end`（`ABORTED`）→ `session/end`（`ABORTED`）；被打断的那条 `tool/call` 有配对的结果 | |
| 没开始的调用 | 同一回合里还没派发的调用也各有一条结果（`TOOL_CANCELLED`），日志里没有只有 `tool/call` 没有 `tool/result` 的调用 | |
| 进程树收干净 | 同场景 B | |
| 文件没被改 | `slow.py` 没跑完；`counts.txt` 不因这条变化 | |

这条只有真终端能做：本机 ConPTY 路线走不通（`UpdateProcThreadAttribute` 恒返回 87），所以 seam ⑥ 的 Windows Ctrl-C 黑盒不在 M3（见上一节「本机跑不到的判据」）。

### 参考样本（mock 干跑，不是人的运行）

备清单时用 mock fixture 把场景 A 与场景 B 的命令形状干跑过一遍（`--provider mock --fixture`，超时那条给 `timeout_seconds: 1`）。场景 B 的日志形状：

```
session/start
   turn/start      t1
context/assembled  t1
   model/request   t1
  model/response   t1
       tool/call   t1  c1
     tool/result   t1  c1  TOOL_TIMEOUT
  tool/cancelled   t1  c1            ← 结果在前、取消记录在后
        turn/end   t1       TOOL_CALLS   ← 回合继续
   turn/start      t2
        ...
       session/end          MODEL_COMPLETED
```

`tool/result` 的 content 是「命令超过 1 秒没有结束：python slow.py」；`tool/cancelled` 的 payload 只有 `turn_id` 与 `tool_call_id`。墙钟 1.11 s。场景 A 的干跑里三条 `tool/call` 后跟三条 `tool/result` 按声明顺序、`bash` 的 content 第一行是「退出码 0」、`counts.txt` 落在工作区根。

样本的作用是**认形状**，不是判据：判据在 `tests/` 里，这一份是人眼对着真终端的输出比形状。

### 要贴回来的东西

场景 A / B / C 各一份：session id、退出码、墙钟、上面各表「实际」列的内容，外加「哪儿别扭」一两句真实观察（不是期望）。
