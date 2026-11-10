# M14 skills & commands UAT

**状态**：等人跑（ADR-0025）。

## 跑前准备

```bash
cd /Users/vincento/work/develop/mini-harness
export UV_CACHE_DIR="$PWD/.tmp/uv-cache"
rm -rf /tmp/m14-uat && mkdir -p /tmp/m14-uat/.minihns/skills/tdd
cat > /tmp/m14-uat/.minihns/skills/tdd/SKILL.md <<'SKILL'
---
name: tdd
description: 先写会红的判据，再写实现
---

# TDD

1. 先写一条会失败的测试。
2. 再写最小实现让它变绿。
3. 每次只做一个切片。
SKILL
printf '目标：把这条写进 note.md\n' > /tmp/m14-uat/inbox.md
```

## 场次

### S1 · `/skills` 与 `/skill`

```bash
uv run minihns chat --provider deepseek --workspace /tmp/m14-uat --yes
> /skills
> /skill tdd
> 按 tdd 技能的步骤，说明你会怎么改一个函数
```

看：`/skills` 列出 `tdd`（名字 + 描述），不开新段；`/skill tdd` 之后屏幕上出现正文，随后是一个新段；模型回答遵循「先写红判据」的步骤。

### S2 · 同名技能高优先级

在用户级也放一个同名 `tdd`（内容不同），重开会话：

```bash
mkdir -p ~/.mini-harness/skills/tdd
cat > ~/.mini-harness/skills/tdd/SKILL.md <<'SKILL'
---
name: tdd
description: 用户级的另一个 tdd
---
用户级正文。
SKILL
uv run minihns chat --provider deepseek --workspace /tmp/m14-uat --yes
> /skills
```

看：`/skills` 里只有一个 `tdd`；`/skill tdd` 给的是**项目内**那份正文。跑完把用户级那份删掉。

### S3 · host 命令面与 CLI 同一份

```bash
MINIHNS_HOST_TOKEN=... uv run minihns host --http --port 19410 --allow-auto-approval &
# 创建会话后：
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:19410/commands
curl -H "Authorization: Bearer $TOKEN" -X POST \
  -d '{"name":"skill","arguments":"tdd"}' \
  http://127.0.0.1:19410/sessions/<id>/commands
```

看：`GET /commands` 与 `/skills` 同一份清单；`POST` 返回 202 且日志里是 `command/invoked` + 一条带正文的 `user/message`。

### S4 · preset persona

在 `/tmp/m14-uat/mini.config.toml` 里配一个带 persona 的 preset，让父会话派一个子代理：

```toml
[subagent]
preset = "reviewer"

[subagent.presets.reviewer]
persona = "你是一位严格的代码评审者，回答必须先指出风险。"
tools = ["read", "glob"]
```

看：子 `session/start.payload.preset_persona` 是这段文本；子会话的第一句回复带有「先指出风险」的风格。

## 观察表

| 场次 | 动作 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| S1 | `/skills` + `/skill` | 清单、正文、按正文回答 | | | |
| S2 | 同名技能 | 只有项目内那份 | | | |
| S3 | host 命令面 | 与 CLI 同一份 | | | |
| S4 | preset persona | 子头部有人设、风格可辨 | | | |

**至少一条「用起来别扭」**：_

**结论**：通过 / 不通过：
