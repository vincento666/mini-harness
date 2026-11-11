# skill-invocation-policy UAT

**状态**：等人跑（ADR-0025）。五个场次都是 non-tty 的 CLI 运行。

## 跑前准备

```bash
cd /Users/vincento/work/develop/mini-harness
export UV_CACHE_DIR="$PWD/.tmp/uv-cache"
export DEEPSEEK_API_KEY="$(awk '/^[[:space:]]*DEEPSEEK_API_KEY:/{print $2}' ~/.dsh/.credentials.yaml | tr -d '"')"
rm -rf /tmp/policy-uat && mkdir -p /tmp/policy-uat/.minihns/skills/{both,model-only,user-only,neither,bad}
cat > /tmp/policy-uat/.minihns/skills/both/SKILL.md <<'SKILL'
---
name: both
description: 两面都可调
---
BOTH 正文。
SKILL
cat > /tmp/policy-uat/.minihns/skills/model-only/SKILL.md <<'SKILL'
---
name: model-only
description: 只给模型用
user-invocable: false
---
MODEL-ONLY 正文。
SKILL
cat > /tmp/policy-uat/.minihns/skills/user-only/SKILL.md <<'SKILL'
---
name: user-only
description: 只给人用
disable-model-invocation: true
---
USER-ONLY 正文。
SKILL
cat > /tmp/policy-uat/.minihns/skills/neither/SKILL.md <<'SKILL'
---
name: neither
description: 两面都禁用
disable-model-invocation: on
user-invocable: "no"
---
NEITHER 正文。
SKILL
cat > /tmp/policy-uat/.minihns/skills/bad/SKILL.md <<'SKILL'
---
name: bad
description: 非法策略值
disable-model-invocation: maybe
---
BAD 正文。
SKILL
```

## 场次

| 场次 | 动作 | 预期 |
|---|---|---|
| S1 | `chat` 里 `/skills` | 列出 `both` 与 `user-only`；不列 `model-only`、`neither`、`bad` |
| S2 | `/skill model-only` | `ok=false`（非用户可调），不打印正文 |
| S3 | `/user-only` | 打印 `USER-ONLY 正文` |
| S4 | 模型侧：让模型「用 skill 工具加载 user-only」 | 模型拿到 `TOOL_ARGS_INVALID`（不可由模型调用）；`session/start.payload.skills` 里没有 `user-only`、有 `model-only` 与 `both` |
| S5 | 让模型「用 skill 工具加载 bad / neither」 | 都是未知技能（`bad` 被丢弃；`neither` 两面禁用） |

核对：

```bash
python3 - <<'PY'
import json, glob
start = next(json.loads(l) for l in open(sorted(glob.glob('/tmp/policy-uat/sessions/*.jsonl'))[-1])
             if json.loads(l)['type'] == 'session/start')
print([s['name'] for s in start['payload'].get('skills', [])])
PY
```

预期模型清单：`["both", "model-only"]`。

## 观察表

| 场次 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|
| S1 | | | |
| S2 | | | |
| S3 | | | |
| S4 | | | |
| S5 | | | |

**至少一条「用起来别扭」**：_

**结论**：通过 / 不通过：
