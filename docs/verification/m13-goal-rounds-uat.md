# M13 关键 UAT 场次手册

**立骨架**：2026-11-17（propose 时立，归档前必须填完）。

**为什么要人跑**：本 change 改变「谁在什么时候开下一个段」，属于不可逆的自动续跑，且成本面（无人值守连续调模型）显著上升，按 `devops-loop` §0.4 属关键场次。

**环境**：本机 macOS；`minihns chat`；真实端点（`DEEPSEEK_API_KEY`）；工作区用临时目录。

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
- 空转**默认不会停**（D14，2026-11-20 改口对齐 DSH）：模型某一轮只说话、没调用工具，驱动仍会开下一轮，跑到 `max_rounds` 才停。看到「明明没事可做还在跑」不算失败——这是 DSH 的形状。只有配置了 `[goal] stall_rounds = N` 才会在连续 N 轮零工具调用后出现「已停止自动推进」。
- 观察：无人输入时是否自己推进；轮次提示是否清楚（`Round: n/2`）；阻塞后是否停下不动。
- 结果：**待填**

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
- 结果：**待填**

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
- 结果：**待填**

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
- 结果：**待填**

## 证据

- 会话日志路径：待填
- 关键事件序列：待填
- 终端录屏或粘贴：待填

## 残余风险

- 待填（归档前补齐）
