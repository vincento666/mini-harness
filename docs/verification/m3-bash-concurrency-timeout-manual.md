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

**状态：跑完（2026-10-19 20:08–20:11，人在真终端跑的三个 session）。** 形状沿用 `docs/verification/m1-m2-manual-smoke.md`：场景表 + 可粘贴命令 + 观察点；「实际」列由日志读出，「别扭」列在最后一节。不进 CI，也不替代门禁那四道。

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
| 提问 | 跑到 `bash` 前停在终端前，一行「允许 bash 跑 python count_lines.py，输入 y 或 n：」；答 `y` 之后进程才起 | 三次提问（t1 / t3 / t6 各一条 `bash`），措辞是「允许 bash 改动 <命令>，输入 y 或 n：」——「允许 bash 跑」是我写清单时的措辞，不是实现的措辞。三次都答 `y`，日志里三条 `approval/response` 都是 `APPROVED` |
| 退出码 / 墙钟 / session id | 0 | `c25136a7e1d942cb9b953fdd329af558`，52 条记录，墙钟 31.92 s（日志首尾 `ts` 之差），6 个回合，`MAX_TURNS` → 退出码 0（`STOP_REASONS_TO_EXIT_CODES`） |
| `bash` 的结果 | `tool/result` 的 `outcome=OK`，content 第一行「退出码 0」，后面是 `wrote counts.txt` 与两行计数 | t3 `python count_lines.py` 对上 ✓。另外两条值得记：t1 `ls -la && echo "---" && cat count_lines.py` 在 cmd.exe 里 **退出码 1**（`ls` 不是内建命令）仍是 `OK`；t6 那条多行 `python -c "…"` 退出码 0 但输出是空的 |
| cwd 固定在工作区根 | `.tmp/m3-manual/counts.txt` 出现（命令里的相对路径落在工作区根，不是仓库根） | ✓ `.tmp/m3-manual/counts.txt` 出现，内容 `a.md 5` / `b.md 4`；仓库根没有 `counts.txt` |
| 并发派发 | 同一回合两个 `read`：两条 `tool/call` 按声明顺序、两条 `tool/result` 按声明顺序 | ✓ t5 两条 `read`（`notes/a.md`、`notes/b.md`）：`call` 与 `result` 都是声明顺序，两条 `result` 的 `ts` 相同（12:08:08.990，同一毫秒） |
| 成组 | 每个 `tool_call_id` 自己的 `tool/call` →（`approval/request` → `approval/response` →）`tool/result` 相对顺序成立；不同调用的组可以交错，不要求连续 | ✓ 每个 id 的相对顺序都成立。t5 的形状正是 `call c1`、`call c2`、`result c1`、`result c2`——c2 的 `call` 与它的 `result` 被 c1 的 `result` 切开，就是 10.4 那条「可以交错」在真 run 里的样子 |
| 截断标记 | 不出现 `[输出已截断]`（输出远小于 16384 字节） | ✓ 三个 session 全查过，`[输出已截断]` 出现 0 次 |
| 收尾 | 末回合 `turn/end` 与 `session/end` 都是 `MODEL_COMPLETED` | **没对上**：两者都是 `MAX_TURNS`。模型在第 6 回合还在核对，没给出最终结论 |

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
| 墙钟 | 约 30 秒就出结果，不是 45 秒 | `tool/call` 12:09:28.469 → `tool/result` 12:09:58.543 = **30.07 s** ✓。整个 session `4a2da4bf8106482a9dbab9ab54e7ce3d`：47 条记录、45.04 s、6 个回合 |
| 日志 | `tool/cancelled`（payload 只有 `turn_id` 与 `tool_call_id`，没有命令输出）紧跟一条 `tool/result`，`outcome=TOOL_TIMEOUT` | 顺序是反的：`tool/result`（`TOOL_TIMEOUT`，content「命令超过 30 秒没有结束：python slow.py」）**在前**，`tool/cancelled` 在后，两条 `ts` 相同。与 mock 参考样本一致 |
| 回合继续 | 超时之后模型还有回合，`session/end` 不是 `ABORTED`，退出码 0 | ✓ t4 / t5 / t6 三个回合都在，`session/end` 是 `MAX_TURNS`，退出码 0 |
| 进程树收干净 | 跑完立刻 `Get-CimInstance Win32_Process -Filter "Name like 'python%'" \| Select-Object ProcessId, CommandLine`：只剩 harness 自己那一条（`-m mini_harness.cli.main`），没有 `slow.py`、也没有它打印出来的那个 child pid 对应的 `-c "import time…"` | ✓ 而且**是模型自己查的**：t4 `tasklist /FI "IMAGENAME eq python.exe"`、t5 `Get-CimInstance Win32_Process … python.exe`、t6 搜命令行里的 `slow.py\|time.sleep`。我这边的独立检查同样只剩 Strata 那两个 8300 服务进程与 harness 自己（t6 的搜索结果里那条 `uv.exe run python -m mini_harness…` 就是 harness 本身） |
| 默认值与开关 | 不给 `timeout_seconds` 时是 30 秒；`minihns run --help` 里没有改变它的开关 | ✓ 实测 30.07 s；`run --help` 的开关表里没有改变它的开关 |

### 场景 C（8.2 之二）：一次 Ctrl-C

同一条命令，在 `bash` 正在跑的时候按 Ctrl-C。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 退出码 | `$LASTEXITCODE` 是 5 | 日志 `session/end` 是 `ABORTED`，`STOP_REASONS_TO_EXIT_CODES` 把它钉成 5。**这一格是从日志 + 映射表读出来的，不是终端上读到的**——人没有贴 `echo $LASTEXITCODE`。要终端上的那一行，重跑一次场景 C 之前先记住按 Ctrl-C 后立刻 `echo "exit=$LASTEXITCODE"` |
| 日志尾部 | `tool/cancelled` → `tool/result`（`TOOL_CANCELLED`）→ `error/abort` → `turn/end`（`ABORTED`）→ `session/end`（`ABORTED`）；被打断的那条 `tool/call` 有配对的结果 | 顺序同样是结果在前：`tool/result`（`TOOL_CANCELLED`，content「工具 bash 的执行被打断」）→ `tool/cancelled` → `error/abort`（`code=ABORTED`，`detail="取消被置位"`）→ `turn/end(ABORTED)` → `session/end(ABORTED, turns=1)` ✓ 配对成立 |
| 没开始的调用 | 同一回合里还没派发的调用也各有一条结果（`TOOL_CANCELLED`），日志里没有只有 `tool/call` 没有 `tool/result` 的调用 | **这一格没被验证**：那一回合只有一条 `bash`，没有未派发的调用可看。判据在 seam ①（`tests/test_turn_cancel.py`），真终端这一侧没撞到 |
| 进程树收干净 | 同场景 B | ✓ `30eae25741a840f381e8fc1fd41221c9`：11 条记录、墙钟 7.51 s（约 7 秒时按的 Ctrl-C，没到 30 秒超时）；跑完没有 `slow.py` 与它的 child 残留 |
| 文件没被改 | `slow.py` 没跑完；`counts.txt` 不因这条变化 | ✓ `counts.txt` 仍是 `a.md 5` / `b.md 4`，与场景 A 之后一致 |

这条只有真终端能做：本机 ConPTY 路线走不通（`UpdateProcThreadAttribute` 恒返回 87），所以 seam ⑥ 的 Windows Ctrl-C 黑盒不在 M3（见上一节「本机跑不到的判据」）。

### 别扭与意外（真跑出来的，不是期望）

1. **`--max-turns 6` 不够，真事没办完。** 场景 A 的六个回合花在这条路上：`ls -la && cat count_lines.py`（退出码 1）→ `glob` → `python count_lines.py` → `read counts.txt` → 两条 `read` → 多行 `python -c "…"`。第 6 回合结束在 `MAX_TURNS`，模型始终没给出「一致 / 不一致」的结论。判据本身没坏（每回合都有结果、日志完整、退出码 0），是人给的预算太小。下次给 10。
2. **cmd.exe 的中文输出碎在日志里。** 场景 A 的 t1 那条 content 里有 **34 个 U+FFFD**：`ls` 不存在时 cmd.exe 写的是 GBK 字节，`src/mini_harness/tools/bash_tools.py` 的 `output = stdout.decode("utf-8", errors="replace") + stderr.decode(...)` 把它们换成替换字符。日志层没错，是解码选型；后果是模型看到的是 `'ls' ??????ڲ???ⲿ???` 这种样子。记进 `docs/adr/0002-deferred-refactors.md` 第 30 条，不在 M3 动。
3. **退出码 0 不等于命令做了事。** 同一条 t6 的多行 `python -c "…"` 经 cmd.exe 退出 0、输出为空。不变量 B 保证「有结果」，不保证「命令语义成立」。
4. **模型自己去查了进程树**（场景 B 的 t4 / t5 / t6）。这份记录里最有用的一条证据不是人贴的，是 harness 跑出来的。
5. **交错在真 run 里出现了**（场景 A 的 t5）：`call c1`、`call c2`、`result c1`、`result c2`。10.4 改措辞之前，这条形状会被判成违规。
6. **提问措辞**：实现说「允许 bash 改动」，清单里写的是「允许 bash 跑」。清单是预测，不是规格。

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

### 这一轮实际回来的是什么

人贴回来的是三段终端原文：场景 A 的三次提问行与 session id，场景 B 与 C 的 session id。退出码、墙钟、事件序列、截断标记、进程残留都由我从 `.tmp/m3-manual/sessions/*.jsonl` 读出（取证脚本 `docs/verification/m3-bash-manual-inspect.ps1`）。

两处因此**没有终端侧的直接证据**，上面表里已标明：场景 C 的退出码 5（从日志 `session/end(ABORTED)` 加 `STOP_REASONS_TO_EXIT_CODES` 读出），以及「同一回合里没开始的调用也各有一条结果」（那一回合只有一条 `bash`，没有未派发的调用可看）。
