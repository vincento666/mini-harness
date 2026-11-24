# align-turn-step-naming UAT 场次手册

**立骨架**：2026-11-24（删除兼容层之后补立；按 ADR-0025，这张表没填完不得归档、不得合入 `main`）。

**为什么要人跑**：这次改名把用户每天看到的词全部换掉（`段 → 轮`、`回合 → 步`、`--max-turns → --max-steps`），mock 测试只能证明形状，证不了「一个新用户读这些提示会不会误事」。三场都不长，合计约十分钟。

**环境**：本机 macOS；真实端点（`DEEPSEEK_API_KEY`）；工作区用临时目录。

## 准备（每场开始前）

```bash
cd /Users/vincento/work/develop/mini-harness
export DEEPSEEK_API_KEY=$(python3 -c 'import pathlib,re;t=(pathlib.Path.home()/".dsh/.credentials.yaml").read_text();print(re.search(r"^\s*DEEPSEEK_API_KEY:\s*(\S+)\s*$",t,re.M).group(1))')
rm -rf .tmp/uat/naming && mkdir -p .tmp/uat/naming
```

## 场次 1：一次性 run 的词与日志形状

- 步骤：

```bash
uv run minihns run -p "读 README.md 的前 20 行，用一句话总结这个项目是做什么的" \
  --provider deepseek --model deepseek-chat --max-steps 3 \
  --workspace .tmp/uat/naming --session-dir .tmp/uat/naming/sessions --yes
```

- 期望：退出码 0；stdout 是一句中文总结；日志（`sessions/*.jsonl`）里的事件类型只有 `session/*`、`turn/*`、`step/*`、`context/assembled`、`model/*`、`user/message`、`tool/*`；`session/start` 的载荷键是 `max_steps`（不是 `max_turns`）。
- 观察：屏幕上有没有出现「段 / 回合」这类旧词；`--max-steps` 的 help 文案是否说得清「一步 = 一次模型往返」。
- 结果：**待填**

## 场次 2：一轮撞上限时的收尾提示

- 步骤：用同一个工作区、换 `chat`，把步数上限压到 1，让它写一个需要两步才能完成的任务：

```bash
uv run minihns chat --provider deepseek --model deepseek-chat --max-steps 1 \
  --workspace .tmp/uat/naming --session-dir .tmp/uat/naming/sessions --yes
```

在提示符里粘贴：

```text
先读 README.md，然后在 notes.md 里写三行摘要，写完告诉我。
```

- 期望：模型读完文件就用完了这一步的额度，stderr 出现一行 `[轮] 收尾 MAX_STEPS`（不是 `[段]`）；这一行不出现在 stdout，也不写进日志；提示符回到你手里，可以继续输入。
- 观察：`[轮] 收尾` 与目标轮次的 `[轮] n/cap` 会不会混；`MAX_STEPS` 这个词是否能看懂（必要时查 `GLOSSARY.md`）。
- 结果：**待填**

## 场次 3：host 视图的 `turns` 是轮数，重启后不变

- 步骤：起 host，投一条消息，看列表，再重启看一次：

```bash
uv run minihns host --http --port 8791 --session-dir .tmp/uat/naming/sessions &
```

另一只终端：

```bash
curl -s -X POST localhost:8791/sessions -H "Content-Type: application/json" \
  -d '{"workspace":".tmp/uat/naming","provider":"deepseek","model":"deepseek-chat","max_steps":2}' | head -c 400
```

拿返回的 `session_id`，发一条消息，等它回到 idle，再查列表：

```bash
curl -s localhost:8791/sessions | python3 -m json.tool | head -40
```

停掉 host（`Ctrl-C`），用同一条 `--session-dir` 重新起，再查一次列表。

- 期望：`turns` 是**轮数**（一轮里有几步不影响它）；重启前后同一个会话的 `turns` 相同。
- 观察：`turns` 与日志里 `turn/start` 的条数是否一致；重启后列表里有没有会话消失。
- 结果：**待填**
