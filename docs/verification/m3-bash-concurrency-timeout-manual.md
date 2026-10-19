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

待跑。形状沿用 `docs/verification/m1-m2-manual-smoke.md`：场景表 + 一键脚本 + `mismatches=0`，外加只有真终端能做的按键与 Ctrl-C 两条。
