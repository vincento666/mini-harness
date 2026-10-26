# Proposal

## Why

M5 的真实端点重新验收（`docs/verification/m5-context-budget-compaction-reacceptance.md`）跑出三次溢出，**三次全走「无可遮蔽」**，而其中两次的上下文离真正的窗口还很远：

- session `70fa85600d484109b2f266506ee24c42`：`--window 70000 --reserve 100`，触发线 4364、保留预算 11200、压力预算 69900。装配读数 **5933**，日志 `error/context seq=24`，run 以退出码 4 结束。
- session `8de532bbf9d045d58ca3cf56cd55c7ad`：`--window 100000 --reserve 100`，一次 `read` 得到 424,641 字符（估算 106,161 token），压力预算 99900——这一次是真溢出。

根因在 `loop/turn_loop.py:821-852`：**触发线同时被当成压缩触发线和溢出判据**。`reading > trigger_line` 先决定是否压缩，压缩无可遮蔽后同一个 `reading > trigger_line` 直接产出 `CONTEXT_WINDOW_EXCEEDED`。当 `trigger_line < retain_line`（`W < (O + 65536) / 0.84`，默认保留额下约 `W < 87890`）时，读数落在 `(trigger_line, retain_line]` 这一段就是死区：压缩无从下手（`shadowed_range` 的 `_round_end` 把切点推到整组工具往返之后，落点越过最后一条候选就返回 `None`，`budget.py:200-211`），而上下文其实装得下。70000 / 100 那一跑是在 4364 token 处撞墙，窗口允许 69900。

**判据侧的连带欠账**：M5 的完成判据写着「压缩仍不够时以退出码 4 结束」，可这条字面分支在当前形状下**不可达**——压缩成功一次的表层不超过「头部 + 摘要 + `0.16 W`」，要它超过 `W − O` 需要 `O > 0.84 W`，那时触发线被 `max(0, ·)` 压成 0，压缩不会开始。这条判据从来没有以它写着的形状被跑到过。记在 `docs/adr/0002` 的「判据欠账」与 `docs/CURRENT.md`。

## What Changes

- **溢出判据换成压力预算**：新增 `pressure_budget = W − O` 这一处事实；一次装配的读数不超过它时 MUST NOT 产出 `CONTEXT_WINDOW_EXCEEDED`，即使它超过触发线、即使本次没有可遮蔽的内容。触发线只决定「这次装配要不要尝试压缩」。
- **死区窗口可跑**：`trigger_line < retain_line` 不再是运行期撞墙的配置。既有的启动校验跟着换轨（apply 时改，见 design D5）：从 `W − O − 65536 ≤ 0 → 退出码 2` 改成 **`W − O ≤ 0 → 退出码 2`**——旧那条的理由「触发线为 0 就救不动」正是本 change 要修的判据错位。
- **摘要请求装不下时不再直接溢出**：那条路今天无条件通向 `CONTEXT_WINDOW_EXCEEDED`；改成「不发请求，是否溢出由压力预算判」。
- **`detail` 给三个数**：读数、压力预算、触发线，并保留「压缩之后」与「无可遮蔽」两种措辞分支。
- **那条字面分支变可达**：修完之后「压缩发生了但仍然不够」第一次能真跑到（压缩后读数仍超过压力预算），M5 完成判据那句第一次有判据打到它。

**本 change 明确不做**：不改触发线公式 `floor(min(W × 0.8, W − O − 65536))`；不改保留预算的 `0.16`（照抄 DSH 的 `DEFAULT_RETAIN_RATIO`）；不改 `字符 ÷ 4` 的估算；不动 `shadowed_range` 的切点规则与「不拆散工具往返」；不加任何命令行开关；不解决「单条工具往返本身就超压力预算」——那是真溢出，本 change 让它继续以退出码 4 结束；不碰 `minihns serve` 的事件流。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `context-budget`：新增「溢出判据是压力预算，触发线只决定要不要压缩」；修改「越线时压缩发生在装配之内」「压缩救不了时是 CONTEXT_WINDOW_EXCEEDED 结果」「摘要请求只装本次要遮蔽的那一段」。
- `turn-loop`：修改「停止判定写在 turn/end」里 `CONTEXT_WINDOW_EXCEEDED` 的措辞（判据从触发线换成压力预算）。

## Impact

- 代码：`context/budget.py` 加 `pressure_budget(window, reserve)`；`loop/turn_loop.py:821-852` 的判定与 `detail` 措辞；`cli/main.py` 的启动校验不动。
- 判据：seam ①（死区不溢出、压缩后仍超压力预算、摘要请求装不下不再直接溢出）、seam ⑥（`--window 70000 --reserve 100` 的真实子进程退出码不是 4）、seam ④ 不动。
- 文档：立 **ADR-0026**（溢出判据与压缩触发线是两件事，以及为什么之前那条判据不可达）；关闭 `docs/adr/0002` 的「判据欠账」里小窗口死区那条；`docs/roadmap.md` 的 M5 完成判据补一句。
- 依赖：无新增依赖。
