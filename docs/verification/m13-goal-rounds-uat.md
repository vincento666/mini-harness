# M13 关键 UAT 场次手册

**立骨架**：2026-11-17（propose 时立，归档前必须填完）。

**为什么要人跑**：本 change 改变「谁在什么时候开下一个段」，属于不可逆的自动续跑，且成本面（无人值守连续调模型）显著上升，按 `devops-loop` §0.4 属关键场次。

**环境**：本机 macOS；`minihns chat`；真实端点（OpenRouter `qwen/qwen3.8-27b`，`--provider openrouter`）；工作区用临时目录。

**跑法**：2026-11-24 **agent 代跑**（用户明确指示）。场次 1/3/4 用 pty 驱动器（`.tmp/uat/drive_chat.py`）喂输入；场次 2 的 Ctrl-C 判据**未复现**，见该场结果。

> **2026-11-19 修正**：原场次 1 写的是 `/goal 修好……轮次上限 2`，但 `/goal` 只有查看 / `pause` / `resume` / `clear` 四个动作（task 5.2），**没有创建**——建目标是模型的 `create_goal` 工具。手册已按实现改口，每场都给出可直接粘贴的命令与提示词。

## 准备（每场开始前）

```bash
cd /Users/vincento/work/develop/mini-harness
export DEEPSEEK_API_KEY=$(python3 -c 'import pathlib,re;t=(pathlib.Path.home()/".dsh/.credentials.yaml").read_text();print(re.search(r"^\s*DEEPSEEK_API_KEY:\s*(\S+)\s*$",t,re.M).group(1))')
rm -rf .tmp/uat/m13 && mkdir -p .tmp/uat/m13
uv run minihns chat --provider deepseek --workspace .tmp/uat/m13 --session-dir .tmp/uat/m13/sessions --yes
```

启动后 stderr 会打一行 `会话 <session-id>`，**记下来**，场次 4 要用。

## 场次 1：两轮续跑后自己停

- 启动：用上面的准备命令。
- 步骤：在 `> ` 提示符粘贴这一段（建目标后停手，之后**不要再输入**）：

```text
请调用 create_goal 建一个目标，objective 写「把 notes.md 逐节写成三节：每轮只写一节，写完不要标完成，由我验收」，max_rounds 给 2。建完目标就结束这一轮，现在不要读文件、不要写文件。
```

- 期望：这一段结束后**不出现 `> ` 提示符**，stderr 先打 `[轮] 1/2`、再打 `[轮] 2/2`；第 2 轮之后写 `goal/updated {phase: "blocked", blocked_reason.code: "round-limit"}` 并打一行 `已用尽 2/2`，回到提示符；`notes.md` 里有两节（第 3 节没写）。
- 另一种合法收尾（2026-11-20 起，D15）：模型在轮次里调 `ask_user` 但没人能答时，**不再续跑**——stderr 出现 `[轮] n/2` 后跟 `目标保持 active`；提示符回到你手里，**目标不暂停**。你直接输入答案：那是一条人类段（不是 goal 轮），它收尾后自动接下一轮，不需要 `/goal resume`。看到这个不算失败。
- 空转**默认连续两轮才停**（D14，2026-11-20 三裁）：第一轮只说不动会照常开下一轮；连续第二轮仍零工具调用时，stderr 出现「已停止自动推进」，提示符回到你手里，目标仍是 `active`。用 `/goal resume` 再给两轮，或 `/goal complete` 收尾。配 `[goal] stall_rounds = 0` 可完全关闭，一路跑到上限。
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
（应是 `相位 paused`、`未武装`、轮次 1/4）

```text
/goal resume
```
（应是「已恢复目标：继续自动推进」）。**不用再输入**：紧接着应出现 `[轮] 2/4`，自动跑下去。

- 期望：`Ctrl-C` 之后不再自动起新段；`/goal resume` 之后武装位变 true（`get_goal` 的工具结果里 `armed: true`）；「继续」这一段结束后自动续跑，轮次从 2 起。
- 观察：取消的反馈是否明确；续跑是否要人确认；有没有「取消后自己又跑了」。
- 结果：**未通过（agent 代跑未复现）**。两次尝试都没取消当前轮：①往 pty 写 `^C`——目标一路跑到 4/4，`/goal` 显示 `相位 blocked · 轮次 4/4`，`/goal resume` 回「轮次已用尽（4/4）：先调大 max_rounds 再 resume」；②直接给 chat 进程 `SIGINT`——日志停在 `rounds_started=3`、第 4 轮的 `step/start`（seq 96），无 `turn/end`、无 `session/end`，是驱动器超时把进程截断，不是取消生效。两次都没有出现 `paused` 相位，判据「Ctrl-C 取消当前轮 → `/goal` 显示 paused → `resume` 续跑」一条也没达成。**未定位**是 chat 的 Ctrl-C 在同步模型调用期间没生效，还是 pty 驱动器的局限。按 ADR-0025，这条 tty 判据需人在真终端复核。

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

- 期望：第一次 `/todo` 显示三条（t1、t2 为 `in_progress`，t3 为 `pending`）；第二次为空——表在 `segment/start` 清空，是「本段的常备计划」，不是跨段状态（D8，对齐 DSH 的 `turn/start`）。
- 观察：`/todo` 的输出是否够人读懂；段边界前后的变化是否让人意外（第二次为空是**预期**，不是丢数据——表还在日志里）。
- 结果：**通过**。会话 `a12e059d6a2e453e88e847c14ab97d4c`：第一个 turn 的 `/todo` 出三条（`t1`/`t2` `in_progress`、`t3` `pending`）；第二个 turn 的 `/todo` 出「（没有待办）」——日志里两条 `command/done` 的 `text` 与屏幕一致，清空发生在 `turn/start` 之后。

## 场次 4：恢复会话不自己动

- 启动：场次 1 结束之后按 `Ctrl-D`（或提示符上 `Ctrl-C`）退出，然后：

```bash
cd /Users/vincento/work/develop/mini-harness
export DEEPSEEK_API_KEY=$(python3 -c 'import pathlib,re;t=(pathlib.Path.home()/".dsh/.credentials.yaml").read_text();print(re.search(r"^\s*DEEPSEEK_API_KEY:\s*(\S+)\s*$",t,re.M).group(1))')
uv run minihns chat --provider deepseek --workspace .tmp/uat/m13 --session-dir .tmp/uat/m13/sessions --yes --resume <场次 1 的 session-id>
```

- 步骤：启动后输入：

```text
/goal
```

- 期望：不自动起新段（启动即停在提示符）；`/goal` 显示 `相位 blocked`（场次 1 撞了上限）与 `未武装`；输入一句话才继续，且不会自动开新段（目标是 blocked）。
- 观察：恢复的默认行为是否符合「不擅自花钱」。
- 结果：**通过**。`--resume 83ad04206755451cadf4186b0b1115b7` 启动后停在提示符、没有自动起轮；`/goal` 显示 `相位 blocked · 轮次 2/2 · 未武装`。

## 证据

- 会话日志路径：`.tmp/uat/m13/sessions`（场次 1、4）、`.tmp/uat/m13s2`、`.tmp/uat/m13s2b`（场次 2 两次尝试）、`.tmp/uat/m13s3/sessions`（场次 3）
- 关键事件序列：场次 1/4 见 `83ad0420…jsonl` 的 `goal/updated` 与 `turn/end`；场次 3 见 `a12e059d…jsonl` 的两条 `command/done`
- 终端录屏或粘贴：驱动器把 pty 全文打在 stdout（见本轮会话记录）；未落盘为文件

## 残余风险

- **场次 2 的 Ctrl-C 判据仍待人在真终端复核**；复核前 m13 不得归档
