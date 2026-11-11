# skill-slash-commands UAT

**状态**：**agent 代跑**（用户明确指示，2026-11-11）。三场都是 non-tty 的 CLI/HTTP 运行，观察由 agent 记录；合并前由用户确认这笔偏离。

## 跑前准备

```bash
cd /Users/vincento/work/develop/mini-harness
export UV_CACHE_DIR="$PWD/.tmp/uv-cache"
export DEEPSEEK_API_KEY="$(awk '/^[[:space:]]*DEEPSEEK_API_KEY:/{print $2}' ~/.dsh/.credentials.yaml | tr -d '"')"
rm -rf /tmp/m14b-uat && mkdir -p /tmp/m14b-uat/.minihns/skills/tdd /tmp/m14b-uat/.minihns/skills/skills
cat > /tmp/m14b-uat/.minihns/skills/tdd/SKILL.md <<'SKILL'
---
name: tdd
description: 先写会红的判据，再写实现
---
第一条：先写红判据。
SKILL
cat > /tmp/m14b-uat/.minihns/skills/skills/SKILL.md <<'SKILL'
---
name: skills
description: 故意与内置命令同名
---
这是叫 skills 的技能正文。
SKILL
```

## S1 · 直接 `/技能名`

```bash
uv run minihns chat --provider deepseek --workspace /tmp/m14b-uat --yes
> /tdd
> /help
```

看：`/tdd` 打印「第一条：先写红判据。」；`/help` 列出 `/skills`、`/skill`、`/tdd`——**叫 `skills` 的技能不出现在清单里**（内置名优先），但它仍可用 `/skill skills` 调到。

核对：

```bash
python3 - <<'PY'
import json, glob
for line in open(sorted(glob.glob('/tmp/m14b-uat/sessions/*.jsonl'))[-1]):
    r = json.loads(line)
    if r['type'].startswith('command/'):
        print(r['type'], r['payload'].get('name'), r['payload'].get('ok'))
PY
```

预期：一条 `command/run name=tdd` + 一条 `command/done`；没有 `segment/start`。

## S2 · 内置名优先

```bash
uv run minihns chat --provider deepseek --workspace /tmp/m14b-uat --yes
> /skills
> /skill skills
```

看：`/skills` 列的是清单（不是「这是叫 skills 的技能正文」）；`/skill skills` 才打印那段技能正文。

## S3 · host 的会话级清单

```bash
export MINIHNS_HOST_TOKEN="uat-$(date +%s)-$(printf 'x%.0s' $(seq 1 24))"
uv run minihns host --http --port 19411 --session-dir /tmp/m14b-uat/host-sessions &
sleep 2
TOKEN="$MINIHNS_HOST_TOKEN"
SID=$(curl -s -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"workspace":"/tmp/m14b-uat","provider":"deepseek"}' \
  http://127.0.0.1:19411/sessions | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_id"])')
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:19411/commands?session_id=$SID" | python3 -m json.tool
curl -s -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"tdd"}' http://127.0.0.1:19411/sessions/$SID/commands | python3 -m json.tool
kill %1
```

看：带 `session_id` 的清单里有 `tdd` 与 `skills`（技能），不带时只有内置命令；`POST {name:"tdd"}` 返回正文。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | `/tdd` + `/help` | 正文、`/tdd` 在清单里、不开段 | `/tdd` 打印「第一条：先写红判据。」；`/help` 是 `命令：/skills / /skill / /tdd`（叫 `skills` 的技能不在里面）；日志 `command/run name=tdd` + `command/done`，无 `segment/start` | 通过 | |
| S2 | `/skills` 与 `/skill skills` | 内置优先 | `/skills` 列清单（含 tdd 与叫 skills 的技能）；`/skill skills` 打印「这是叫 skills 的技能正文。」；内置没被覆盖 | 通过 | `/skills` 的清单里会出现与内置同名的技能，但 `/help` 里不出现——同一会话两处清单不一致，容易困惑 |
| S3 | host 会话级清单 | 带 `session_id` 才列技能 | 带 `session_id` 是 `skills`/`skill`/`tdd`；不带只有前两个；`POST {name:"tdd"}` 返回正文；日志一对 run/done | 通过（agent 代跑） | |

**至少一条「用起来别扭」**：`/skills` 列出所有技能（含与内置同名的），`/help` 只列不冲突的技能命令——两处清单口径不同，第一眼会以为 `skills` 技能消失了。

**结论**：通过（agent 代跑，S1–S3；偏离由用户确认）。
