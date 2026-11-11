# M14 skills & commands UAT

**状态**：S1 / S2 由人跑（2026-11-11 通过）；S3 / S4 由 agent 代跑（用户明确指示「剩下你帮我跑吧」），观察由 agent 记录。S3/S4 是 non-tty 的 CLI/HTTP 运行，这笔流程偏离在合并前由用户确认。

## 跑前准备（一次）

```bash
cd /Users/vincento/work/develop/mini-harness
export UV_CACHE_DIR="$PWD/.tmp/uv-cache"
export DEEPSEEK_API_KEY="$(awk '/^[[:space:]]*DEEPSEEK_API_KEY:/{print $2}' ~/.dsh/.credentials.yaml | tr -d '"')"

rm -rf /tmp/m14-uat && mkdir -p /tmp/m14-uat/.minihns/skills/tdd /tmp/m14-uat/.minihns/skills/review
cat > /tmp/m14-uat/.minihns/skills/tdd/SKILL.md <<'SKILL'
---
name: tdd
description: 先写会红的判据，再写实现
---

# TDD

1. 先写一条会失败的测试。
2. 再写最小实现让它变绿。
3. 每次只做一个切片。
回答时必须**先列出这三步**，再动代码。
SKILL
cat > /tmp/m14-uat/.minihns/skills/review/SKILL.md <<'SKILL'
---
name: review
description: 评审时先指出风险
---

# Review

先指出风险，再给建议。
SKILL
printf '目标：把这条写进 note.md\n' > /tmp/m14-uat/inbox.md
```

## S1 · `/skills` 与 `/skill`（不开段）

```bash
cd /Users/vincento/work/develop/mini-harness
uv run minihns chat --provider deepseek --workspace /tmp/m14-uat --yes
> /skills
> /skill tdd
> 按 tdd 技能的要求，说明你会怎么改一个函数
```

看：

- `/skills` 列出 `review`、`tdd`（名字 + 描述 + rank）；
- `/skill tdd` 打印正文（含「先写会红的判据」），**屏幕上没有因为这条命令多出一个模型回复段**；
- 第三句才开一个段；模型回答**先列出那三步**（说明它自己调了 `skill` 工具拿到正文）。

核对日志（换成实际的 session id）：

```bash
python3 - <<'PY'
import json, glob
for line in open(sorted(glob.glob('/tmp/m14-uat/sessions/*.jsonl'))[-1]):
    r = json.loads(line)
    if r['type'].startswith('command/') or r['type'] in ('segment/start', 'user/message'):
        print(r['type'], r['payload'].get('name'), r['payload'].get('ok'), str(r['payload'].get('content'))[:30])
PY
```

预期：两条命令各一对 `command/run` + `command/done`；`segment/start` 只有一次（第三句）。

## S2 · 同名技能：项目内胜出

```bash
mkdir -p ~/.mini-harness/skills/tdd
cat > ~/.mini-harness/skills/tdd/SKILL.md <<'SKILL'
---
name: tdd
description: 用户级的另一个 tdd
---
用户级正文：这条不应该被用到。
SKILL
cd /Users/vincento/work/develop/mini-harness
uv run minihns chat --provider deepseek --workspace /tmp/m14-uat --yes
> /skill tdd
```

看：打印的是**项目内**那份正文（含「先写会红的判据」），不是「用户级正文」。跑完删掉用户级那份：

```bash
rm -rf ~/.mini-harness/skills/tdd
```

## S3 · host 命令面与 CLI 同一份

```bash
cd /Users/vincento/work/develop/mini-harness
export MINIHNS_HOST_TOKEN="uat-$(date +%s)-xxxxxxxxxxxxxxxx"
uv run minihns host --http --port 19410 --session-dir /tmp/m14-uat/host-sessions &
HOST_PID=$!
sleep 2

TOKEN="$MINIHNS_HOST_TOKEN"
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:19410/commands | python3 -m json.tool

SID=$(curl -s -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"workspace":"/tmp/m14-uat","provider":"deepseek"}' \
  http://127.0.0.1:19410/sessions | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_id"])')
echo "session=$SID"

curl -s -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"skills"}' http://127.0.0.1:19410/sessions/$SID/commands | python3 -m json.tool
curl -s -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"skill","arguments":"tdd"}' http://127.0.0.1:19410/sessions/$SID/commands | python3 -m json.tool

kill $HOST_PID
```

看：`GET /commands` 与 `/skills` 同一份；`POST` 返回 200 与正文；日志里两条命令各一对 `command/run` + `command/done`，**没有** `segment/start`、没有 `user/message`。

## S4 · preset persona

```bash
cat > /tmp/m14-uat/mini.config.toml <<'TOML'
[subagent]
preset = "reviewer"

[subagent.presets.reviewer]
persona = "你是一位严格的代码评审者：回答的第一句必须是指出风险。"
tools = ["read", "glob"]
TOML
cd /Users/vincento/work/develop/mini-harness
uv run minihns run --provider deepseek --workspace /tmp/m14-uat \
  --session-dir /tmp/m14-uat/persona-sessions \
  -p "派一个 subagent 读 inbox.md，然后告诉我它的结论" --yes
```

看：子 `session/start.payload.preset_persona` 是那段文本；子会话的第一句回复带有「先指出风险」的味道。核对：

```bash
python3 - <<'PY'
import json, glob
for path in glob.glob('/tmp/m14-uat/persona-sessions/*.jsonl'):
    for line in open(path):
        r = json.loads(line)
        if r['type'] == 'session/start' and r['payload'].get('entry') == 'subagent':
            print('preset=', r['payload'].get('preset'), 'persona=', r['payload'].get('preset_persona'))
PY
```

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | `/skills` + `/skill` | 清单、正文、不开段；第三句的模型先列三步 | 人跑通过：清单与正文正常，命令不开段，模型回答先列三步 | 通过 | — |
| S2 | 同名技能 | 只有项目内那份 | 人跑通过：`/skill tdd` 给项目内正文 | 通过 | — |
| S3 | host 命令面 | 与 CLI 同一份、不开段 | `GET /commands` 返回 skills/skill；`POST skills` 返回清单、`POST skill tdd` 返回正文；日志两对 `command/run`+`command/done`，无 `segment/start` | 通过（agent 代跑） | token 长度下限 32 在第一次尝试时直接报 `INVALID_ARGUMENT`，消息清楚；配置时容易忽略 |
| S4 | preset persona | 子头部有人设、风格可辨 | 子 `preset=reviewer`、`preset_persona` 是那段文本、`tools=read/glob`；子第一句以「风险提示：…」开头 | 通过（agent 代跑） | 一个 preset 同时管 persona 与 tools，改之前要想清楚两件事 |

**至少一条「用起来别扭」**：S4 的 preset 把 persona 与 tools 绑在同一张表里——只想要人设时也得重列工具表（或继承默认），「只改人设」不是一次编辑。

**结论**：通过（S1–S2 人跑，S3–S4 agent 代跑，S3/S4 的偏离由用户确认）。
