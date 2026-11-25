# M13 关键 UAT 场次手册

**立骨架**：2026-11-17（propose 时立，归档前必须填完）。

**为什么要人跑**：本 change 改变「谁在什么时候开下一个段」，属于不可逆的自动续跑，且成本面（无人值守连续调模型）显著上升，按 `devops-loop` §0.4 属关键场次。

**环境**：本机 macOS；`minihns chat`；真实端点（OpenRouter `qwen/qwen3.8-27b`，`--provider openrouter`）；工作区用临时目录。

**跑法**：2026-11-24 **agent 代跑**（用户明确指示）。四场都用 pty 驱动器喂输入；场次 2 第一轮的驱动器送不出真 SIGINT，改用 `pty.fork()` + 控制终端（已归档为 `scripts/uat/drive_chat_pty.py`，用法见其 docstring）后**通过**，根因与三次尝试的读数见 `docs/lessons.md` L-101。

> **2026-11-19 修正**：原场次 1 写的是 `/goal 修好……轮次上限 2`，但 `/goal` 只有查看 / `pause` / `resume` / `clear` 四个动作（task 5.2），**没有创建**——建目标是模型的 `create_goal` 工具。手册已按实现改口，每场都给出可直接粘贴的命令与提示词。

## 准备（每场开始前）

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a   # OPENROUTER_API_KEY
rm -rf .tmp/uat/m13 && mkdir -p .tmp/uat/m13
uv run minihns chat --provider openrouter --workspace .tmp/uat/m13 --session-dir .tmp/uat/m13/sessions --yes
```

启动后 stderr 会打一行 `会话 <session-id>`，**记下来**，场次 4 要用。

## 人工复核：真终端按一次 Ctrl-C（约 2 分钟，可选）

agent 已经用 `pty.fork()`（真控制终端）代跑通过。若你想用自己的手指确认一次，三步：

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a
rm -rf .tmp/uat/m13-manual && mkdir -p .tmp/uat/m13-manual
uv run minihns chat --provider openrouter --workspace .tmp/uat/m13-manual --session-dir .tmp/uat/m13-manual/sessions --yes
```

1. 在 `> ` 后粘贴场次 2 的建目标提示词（`max_rounds` 给 4），回车。
2. 等 stderr 打出 `[轮] 2/4` 之后再按 **一次** Ctrl-C（别连按）。应看到 `[轮] 收尾 ABORTED`，提示符 `> ` 回来。
3. 输入 `/goal`：应为 `相位 paused · 轮次 2/4 · 未武装`（按得极早可能是 `1/4`）；再输入 `/goal resume`：应为「已恢复目标：继续自动推进」，**紧跟 `[轮] 3/4`**。
4. Ctrl-D 退出后核对日志：

```bash
python3 - <<'PY'
import json, pathlib
p = sorted(pathlib.Path(".tmp/uat/m13-manual/sessions").glob("*.jsonl"))[-1]
for line in p.read_text().splitlines():
    r = json.loads(line)
    if r["type"] == "turn/end":
        print("turn/end", r["payload"]["stop_reason"])
    if r["type"] == "goal/updated":
        g = r["payload"]["goal"]
        print("goal/updated", g["phase"], f'{g["rounds_started"]}/{g["max_rounds"]}')
PY
```

应当依次出现：`turn/end ABORTED` → `goal/updated paused 2/4` → `goal/updated active 2/4` → `turn/end MODEL_COMPLETED` → `goal/updated active 4/4`。

**没出现 `paused` 时的三步分诊**（照顺序看，别先怀疑代码）：

1. 日志里有没有 `error/abort` 或 `turn/end ABORTED`？**没有** → 信号没送到（`bash` 包了一层、`tmux` 里按错了前缀键、或你对 `uv` 而不是 python 发的），不是功能问题。
2. 有 `ABORTED` 但 `phase` 还是 `active` → 真 bug，看 `close_failed_round` 的 `ABORTED` 分支与 `abort_goal`。
3. `paused` 有了但 `/goal resume` 不起轮 → 看 `_resume_round`（`cli/main.py`）与 `next_goal_round`（`loop/turn_loop.py`）。

## 场次 1：两轮续跑后自己停

- 启动：用上面的准备命令。
- 步骤：在 `> ` 提示符粘贴这一段（建目标后停手，之后**不要再输入**）：

```text
请调用 create_goal 建一个目标，objective 写「把 notes.md 逐节写成三节：每轮只写一节，写完不要标完成，由我验收」，max_rounds 给 2。建完目标就结束这一轮，现在不要读文件、不要写文件。
```

- 期望：这一段结束后**不出现 `> ` 提示符**，stderr 先打 `[轮] 1/2`、再打 `[轮] 2/2`；第 2 轮之后写 `goal/updated {phase: "blocked", blocked_reason.code: "round-limit"}` 并打一行 `已用尽 2/2`，回到提示符；`notes.md` 里有两节（第 3 节没写）。
- 另一种合法收尾（2026-11-20 起，D15）：模型在轮次里调 `ask_user` 但没人能答时，**不再续跑**——stderr 出现 `[轮] n/2` 后跟 `目标保持 active`；提示符回到你手里，**目标不暂停**。你直接输入答案：那是一条人类段（不是 goal 轮），它收尾后自动接下一轮，不需要 `/goal resume`。看到这个不算失败。
- 空转**默认连续两轮才停**（D14，2026-11-20 三裁）：第一轮只说不动会照常开下一轮；连续第二轮仍零工具调用时，stderr 出现「已停止自动推进」，提示符回到你手里，目标仍是 `active`。用 `/goal resume` 再给两轮，或 `/goal complete` 收尾。配 `[goal] stall_rounds = 0` 可完全关闭，一路跑到上限。
- **「连 `[轮] n/cap` 都没出现」的常见原因（2026-11-25 实测）**：你在第一句里让模型「分三个篇章，每篇章一轮」，模型却把三章全写在**人类轮**里（`create_goal` → `todo` → `write` → 校验 → `edit` → `read` …），八个步一次用完，`stop_reason=MAX_STEPS`。`MAX_STEPS` 在 `NO_CONTINUE_REASONS` 里，所以驱动不开目标轮——你看不到 `[轮] 1/4`，只看到步级那行 `[轮] 收尾 MAX_STEPS`（注意：**步级收尾**也是这个前缀，圆括号里是理由）。这不是 bug，是「一轮的步数上限撞了就不自动烧钱」。
  要真的看到轮次，提示词里必须写死「**本轮只写一篇，写完就停，不要标完成，由我验收**」，并把 `--max-steps` 调大（默认 8，这个模型一轮里会读文件、写文件、再校验，很费步数）。
- 观察：无人输入时是否自己推进；轮次提示是否清楚（`Round: n/2`）；阻塞后是否停下不动。
- 结果：**通过**。会话 `83ad04206755451cadf4186b0b1115b7`：`create_goal max_rounds=2` → `[轮] 1/2` 写第一节 → `[轮] 2/2` 先试 `update_goal blocked` 被 `GOAL_BLOCK_TOO_EARLY`（至少 3 轮）拒，改 `edit` 写第二节 → `[轮] 已用尽 2/2：目标置为 blocked（round-limit）` → `/goal` 显示 `相位 blocked · 轮次 2/2 · 未武装` 与 `阻塞 round-limit`。`notes.md` 只有两节，第三节未写。全程无人工输入。

## 场次 2：中途叫停与人工续跑

- 启动：重新跑一次准备命令（新会话）。提示词把 `max_rounds` 改成 4：

```text
请调用 create_goal 建一个目标，objective 写「把 notes.md 逐节写成三节：每轮只写一节，写完不要标完成，由我验收」，max_rounds 给 4。建完目标就结束这一轮，现在不要读文件、不要写文件。
```

- 步骤：自动轮次开始前 stderr 会打 `[轮] n/cap`。看到 `[轮] 2/4` 之后按一次 `Ctrl-C`；回到提示符后输入：

```text
/goal
```
（应是 `相位 paused`、`未武装`；轮次是取消时那一轮**已入账**的序号——在看到 `[轮] 2/4` 之后几秒才按，通常是 `2/4`，若按得极早可停在 `1/4`）

```text
/goal resume
```
（应是「已恢复目标：继续自动推进」）。**不用再输入**：紧接着应出现 `[轮] 3/4`（接着已入账的那一轮往下，不重跑被取消的那一轮），自动跑下去。

- 期望：`Ctrl-C` 之后不再自动起新段；`/goal resume` 之后武装位变 true（`get_goal` 的工具结果里 `armed: true`）；「继续」这一段结束后自动续跑，轮次从 2 起。
- 观察：取消的反馈是否明确；续跑是否要人确认；有没有「取消后自己又跑了」。
- 结果：**通过**（2026-11-24 第三次尝试，真控制终端）。会话 `b624450a49554d2f9fd004a96fc04ec1`：
  - 建目标（`max_rounds=4`）→ 第 1 轮写第一节 → `[轮] 2/4` 后 3 秒按 Ctrl-C；日志随即 `error/abort {step_id: t9, code: ABORTED}`、
    `turn/end s3 {stop_reason: ABORTED, steps: 2, tool_calls: 1}`、`goal/updated revision 2 phase=paused rounds_started=2`——
    取消真的落到了「本轮以 ABORTED 收尾」那条路上，`close_failed_round` 把 `active` 改成了 `paused` 并解除武装。
  - `/goal` → `相位 paused · 轮次 2/4 · 未武装`；`/goal resume` → 「已恢复目标：继续自动推进」，`goal/updated revision 3 phase=active`，
    紧接着 `[轮] 3/4`（不重跑被取消的第 2 轮），该轮 `turn/end s4 {MODEL_COMPLETED, steps: 3, tool_calls: 2}`。
  - 再按一次 Ctrl-C（此时 4/4）→ `turn/end s5 ABORTED`、`goal/updated revision 4 phase=paused rounds_started=4`；
    此时 `/goal resume` 回「轮次已用尽（4/4）：先调大 max_rounds 再 resume」——**paused 与额度是两件事**，这一条也顺带验到了。
  - 前两次为什么没反应（根因已定位，不是功能问题）：第一次起的是 `uv run minihns`，`SIGINT` 落在 `uv` 上；
    第二次虽然直接对进程发 `SIGINT`，但 pty 没有成为子进程的控制终端——`os.tcgetpgrp(master)` 返回 `0`，
    没有前台进程组，写进去的 `^C` 只是字节。改用 `pty.fork()`（`setsid` + 控制终端 + exec）后 `tcgetpgrp` 等于子进程 pid，一次就通。
    三次尝试的读数记在 `docs/lessons.md` L-101。

## 场次 3：任务表的两面（段内并行 / 段首清空）

- 启动：重新跑一次准备命令（新会话，无目标）。
- 步骤：粘贴：

```text
请调用 todo 提交三条待办：t1 与 t2 同时标为 in_progress，t3 标 pending。提交完就回一句话结束这一段，不要做别的。
```

等回到 `> ` 后：

```text
/todo
```

再输入：

```text
只回一句话，不要用 todo。
```

回到 `> ` 后再：

```text
/todo
```

- 期望：第一次 `/todo` 显示三条（t1、t2 为 `in_progress`，t3 为 `pending`）；第二次为空——表在 `turn/start` 清空，是「本段的常备计划」，不是跨段状态（D8，对齐 DSH 的 `turn/start`）。
- 观察：`/todo` 的输出是否够人读懂；段边界前后的变化是否让人意外（第二次为空是**预期**，不是丢数据——表还在日志里）。
- 结果：**通过**。会话 `a12e059d6a2e453e88e847c14ab97d4c`：第一个 turn 的 `/todo` 出三条（`t1`/`t2` `in_progress`、`t3` `pending`）；第二个 turn 的 `/todo` 出「（没有待办）」——日志里两条 `command/done` 的 `text` 与屏幕一致，清空发生在 `turn/start` 之后。

## 场次 4：恢复会话不自己动

- 启动：场次 1 结束之后按 `Ctrl-D`（或提示符上 `Ctrl-C`）退出，然后：

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a
uv run minihns chat --provider openrouter --workspace .tmp/uat/m13 --session-dir .tmp/uat/m13/sessions --yes --resume <场次 1 的 session-id>
```

- 步骤：启动后输入：

```text
/goal
```

- 期望：不自动起新段（启动即停在提示符）；`/goal` 显示 `相位 blocked`（场次 1 撞了上限）与 `未武装`；输入一句话才继续，且不会自动开新段（目标是 blocked）。
- 观察：恢复的默认行为是否符合「不擅自花钱」。
- 结果：**通过**。`--resume 83ad04206755451cadf4186b0b1115b7` 启动后停在提示符、没有自动起轮；`/goal` 显示 `相位 blocked · 轮次 2/2 · 未武装`。

## 证据

- 会话日志路径：`.tmp/uat/m13/sessions`（场次 1、4）、`.tmp/uat/m13d/sessions`（场次 2 通过的那次，`b624450a…`）、`.tmp/uat/m13s2`／`.tmp/uat/m13s2b`（场次 2 前两次失败的尝试，留作根因证据）、`.tmp/uat/m13s3/sessions`（场次 3）
- 关键事件序列：场次 1/4 见 `83ad0420…jsonl` 的 `goal/updated` 与 `turn/end`；场次 3 见 `a12e059d…jsonl` 的两条 `command/done`
- 终端录屏或粘贴：驱动器把 pty 全文打在 stdout（见本轮会话记录）；未落盘为文件

## 残余风险

- 场次 2 的 Ctrl-C 判据由 agent 用 `pty.fork()` 代跑通过；与真终端的唯一差别是「人按键的时机」，而判据不依赖时机（`paused` 与续跑轮次都由日志证明）。若人复核，按上面三步即可，读数会与 `b624450a…` 同形。
- 场次 2 的 `/goal` 轮次号取决于取消落在装配完成之前还是之后（记 `1/4` 或 `2/4`），本手册已按「已入账」写，不再是固定值。
