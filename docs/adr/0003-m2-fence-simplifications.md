---
status: partially superseded by ADR-0013（第 3 条作废，其余仍然有效）
---

# M2 围栏的刻意简化：不做 OS 级强制、approval 不提权、管线只有三段、两轴不预设

M2（change `m2-file-tools-and-fences`）落地五个文件工具与围栏判定，但只把围栏做成「harness 自己的判定」。后来的人看到下面的现象时，不要当成缺陷去「修」；每条都写明了代价。

1. **围栏没有 OS 级强制。** 判定靠 `path_key`（`os.path.realpath` + Windows 上 `normcase`）加档位与边界的比较，全部在进程内完成：不建 Windows ACL、不用 job object、不做 landlock。代价是围栏**不是安全边界**——进程内任何代码都能绕过它，它防的是「模型不小心」与「路径写法绕过 CAS」，不防恶意进程。DSH 有 OS 级沙箱，mini 版在「MVP 明确不做」里把它划出去了。
2. **approval 没有提权通道。** 问人只有一次问答，结论只有 `APPROVED` / `DENIED` / `UNAVAILABLE` 三种：批准只放行**这一次**这个操作，既不临时抬 `--sandbox` 档位，也不记住「以后都批准」。`--yes` 是一次性的全局免问，同样不放宽档位（`--sandbox read-only --yes` 仍然以 `SANDBOX_DENIES_WRITE` 被拒）。代价是同一个目录里的连续改动会反复问人，想少问只能整体开 `--yes`。DSH 有「拒绝后带 `sandbox_permissions` 再请求一次」的提权通道，mini 版否掉：那需要一个「提权请求长什么样」的词表，而 M2 没有能消费它的东西。
3. **派发管线塌成三段：校验 → 围栏 → 执行。** 没有第四段：没有 OS 沙箱段、没有提权段、没有 `tool/cancelled` 与 `model/retry`（这两个类型在 M2 词表之外，`tests/test_turn_loop.py::test_no_m2_scenario_writes_tool_cancelled_or_model_retry` 守住它们不出现）。代价是 M3 要插新段时改的是 `dispatch_tool_call` 的函数体，而不是注册一段新环节；`DispatchOutcome` 也会跟着长。
4. **围栏的两条轴不预设。** M2 只实现「档位三档（`read-only` / `workspace-write` / `danger-full-access`）」与「工作区边界」，且**边界只约束会改动的操作**：`read` 一个工作区之外的路径是 `OK`，`write` 同一个路径是 `DENIED_BY_FENCE`（`OUTSIDE_WORKSPACE`）。`danger-full-access` 解除边界，但不解除写前必读与 CAS。判定顺序硬编码在 `judge_fence` 里：档位 → 边界 → 要不要问人。代价是加第三条轴（例如「边界也约束读」「档位可组合」）要改这个函数的顺序，而不是加一条规则；顺序本身就是行为（先校验、再档位、再边界、再问人、最后执行）。
5. **提问走 stderr，读到 EOF 是「不可问人」而不是「人说了不」。** `StdinApprovalGate` 的问题写 stderr、回答读 stdin：stdout 归会话 id 与 `--events jsonl`，混进去就不再与日志逐行相等（13.6 的判据）。回答流读到 EOF 时结论是 `UNAVAILABLE` 而不是 `DENIED`——Windows 上 `NUL` 设备的 `isatty()` 为真，`stdin=DEVNULL` 的子进程会被当成「可以问人」，把 EOF 判成拒绝会让「没人可问」与「人拒绝了」两种情况共用 `APPROVAL_DENIED`。代价是 `isatty()` 在 Windows 上不足以判断「真有人在回答」，真正的 tty 交互只能靠 smoke 验证（见 `docs/verification/m2-file-tools-and-fences-approval-smoke.md`）。

Considered options：OS 级强制（否于 MVP：Windows ACL / job object 的实现量超过 M2 的判据需要）；approval 批准后抬档位或记住批准（否：那需要一个提权词表与一个「记住」的载体，两者都没有判据）；把 `tool/cancelled` 与 `model/retry` 一起做进管线（否：M2 没有产生它们的场景，做了只能测「它不出现」）；边界也约束读（否：读越界在 DSH 与本项目里都是合法能力，约束它会让 `read` 一个已有文件要先问人）；EOF 判成 `DENIED`（否：见第 5 条，两种失败要能区分）。

覆盖的 change：`openspec/changes/m2-file-tools-and-fences/`（proposal、design、specs、tasks）。
