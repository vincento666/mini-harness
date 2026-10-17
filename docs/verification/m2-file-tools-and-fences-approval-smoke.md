# M2 approval 真实 tty smoke（tasks 13.7）

**基线**：分支 `change/m2-file-tools-and-fences`，133 passed / 1 skipped，`uv run mypy --strict src` 干净。
**要验的东西**：approval 门在真 tty 上问一次人，`y` 与 `n` 各自的行为与退出码。

## 为什么 seam ⑥ 的黑盒测试不够

seam ⑥ 的 CLI 测试把子进程的 stdin 接到 `subprocess.DEVNULL`。Windows 上 NUL 设备的 `isatty()` 返回 **True**，读它立刻 EOF——所以那条路径证明的是「没人可问」：`APPROVAL_UNAVAILABLE` → 退出码 3（`test_a_write_with_no_human_to_ask_ends_with_code_three`）。它证明不了「人回答了 y / 人回答了 n」。

本沙箱里 pwsh 自己的 stdin 也是 NUL：子进程继承它，提问写出去了、`readline()` 立刻 EOF → 只能得到 UNAVAILABLE。要拿到「有人回答」就必须造一个真控制台。

试过的路与其结果：

| 做法 | 结果 |
|---|---|
| 子进程继承 pwsh 的 stdin | 提问可见，读立刻 EOF（NUL），`UNAVAILABLE` |
| ConPTY：`CreatePseudoConsole` + `PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE` | `CreatePseudoConsole` 成功，`UpdateProcThreadAttribute` 恒返回 87（`ERROR_INVALID_PARAMETER`），本机不通 |
| 父进程 `FreeConsole` + `AllocConsole`，把控制台句柄交给子进程 | 控制台建起来了（`GetStdHandle` 给出句柄），但 `WriteConsoleInput` 报 6（`ERROR_INVALID_HANDLE`） |
| **子进程 `CREATE_NEW_CONSOLE`，父进程 `AttachConsole(子进程 pid)` 后开 `CONIN$` 投递按键** | **走通** |

走通的那条：子进程有自己的真实控制台，stdin 是控制台句柄（`isatty()` 真、读取走 `ReadConsole`）；父进程 `AttachConsole` 到那个控制台、`CreateFileW("CONIN$")` 拿到同一个控制台的输入句柄，`WriteConsoleInput` 投递 4 条 `KEY_EVENT`（字母按下 + 松开，`\r` 按下 + 松开）。

## 命令

```
uv run python docs/verification/m2-file-tools-and-fences-approval-smoke-harness.py
```

夹具 `tests/fixtures/scenarios/read_then_write/turns.json`：t1 `read notes/plan.md` → t2 `write notes/plan.md` → t3 停止。档位默认 `workspace-write`、approval 默认 `ask`（不加 `--yes`）。脚本自己建临时工作区 `.smoke-ws` / `.smoke-sessions`，结束时清掉。

## 两次运行与退出码

| 回答 | `approval/response.decision` | `tool/result.outcome` | `error/fence` | 终止 | **退出码** | `notes/plan.md` |
|---|---|---|---|---|---|---|
| `y` | `APPROVED` | `OK`（「写了 …plan.md（7 个字符）」） | 无 | 继续跑到 t3 `MODEL_COMPLETED` | **0** | 由「# 计划…」改成「重写过的计划」 |
| `n` | `DENIED` | `DENIED_BY_APPROVAL` | `APPROVAL_DENIED` | t2 `FENCE_DENIED`，t3 没跑到 | **3** | 字节不变 |

提问文本（写到子进程 stderr，即它自己的控制台）：

```
允许 write 改动 s:\develop\mini-harness\.smoke-ws\notes\plan.md，输入 y 或 n：
```

`n` 那次 stderr 上的失败行（非 0 退出必须在 stderr 说清楚）：

```
APPROVAL_DENIED: 没有获得批准：s:\develop\mini-harness\.smoke-ws\notes\plan.md
```

`n` 那次的类型序列（尾部）：`… → tool/call → approval/request → approval/response → tool/result → error/fence → turn/end → session/end`；`y` 那次没有 `error/fence`，尾部是 `… approval/request → approval/response → tool/result → turn/end → turn/start …`。

## 人工在真终端复现

```
uv run minihns run -p "任务" --provider mock `
  --fixture tests/fixtures/scenarios/read_then_write/turns.json `
  --workspace <一个含 notes/plan.md 的目录> --session-dir .sessions
```

看到「允许 write 改动 …，输入 y 或 n：」后：

- 敲 `y` 回车 → 退出码 0（`echo $LASTEXITCODE` / `echo $?`），文件被改写，日志里没有 `error/fence`。
- 同一命令再来一次，敲 `n` 回车 → 退出码 3，stderr 打 `APPROVAL_DENIED: …`，文件不动，日志尾部是 `error/fence(APPROVAL_DENIED)` + `turn/end(FENCE_DENIED)`。

## 已知限制

- 记录里的两次退出码来自 `WriteConsoleInput` 投递的按键事件，不是人手敲的键盘。控制台是真的（子进程 stdin 是控制台句柄、走 `ReadConsole`），按键是程序投递的。
- 这条 smoke 不进测试套件：它要求能创建新控制台会话的桌面环境，CI 上跑不稳；`y` / `n` / EOF 三条分支本身由 `tests/test_approval_gate.py` 在 seam 上守住。
