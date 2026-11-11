# skill-catalog-live UAT

**状态**：等人跑（ADR-0025）。四场；核心是「目录是消息、会变」。

## 准备

```bash
cd /Users/vincento/work/develop/mini-harness
export UV_CACHE_DIR="$PWD/.tmp/uv-cache"
export DEEPSEEK_API_KEY="$(awk '/^[[:space:]]*DEEPSEEK_API_KEY:/{print $2}' ~/.dsh/.credentials.yaml | tr -d '"')"
rm -rf /tmp/catalog-uat && mkdir -p /tmp/catalog-uat/.minihns/skills/tdd
cat > /tmp/catalog-uat/.minihns/skills/tdd/SKILL.md <<'SKILL'
---
name: tdd
description: 先写会红的判据
---
先写红判据，再写实现。
SKILL
```

## 场次

### S1 · 首个 turn 注入目录

```bash
uv run minihns chat --provider deepseek --workspace /tmp/catalog-uat --session-dir /tmp/catalog-uat/s1 --yes
> 用一句话说明你手上有哪些技能
```

看：`sessions/*.jsonl` 里第一个 turn 前有一条 `user/message`，payload `source=skill-catalog`、内容含 `<available_skills>` 与 `tdd`；受保护头部里**没有**「可用技能」块。

### S2 · 会话中途加技能

保持 S1 的会话开着，另开一个终端：

```bash
mkdir -p /tmp/catalog-uat/.minihns/skills/review
printf -- '---\nname: review\ndescription: 评审先指出风险\n---\n先指出风险。\n' > /tmp/catalog-uat/.minihns/skills/review/SKILL.md
```

回到会话再输入一句「现在你手上有哪些技能」。看：第二个 turn 之前**追加**了一条目录消息，含 `review`；再输入一句不变的内容，**不再**追加。

### S3 · 清空退休

删掉两个技能目录后再输入一句。看：追加一条空目录消息，明确说不要使用旧名字。

### S4 · 不完整与恢复

把一个根目录改成不可读（或临时换成网络盘模拟失败）再输入一句。看：目录带警告与 `incomplete: true`；恢复权限后的下一句追加无警告的替换。

## 观察表

| 场次 | 预期 | 实际观察 | 结论 | 别扭在哪 |
|---|---|---|---|---|
| S1 | 首 turn 前有目录消息；头部无技能块 | | | |
| S2 | 加技能后追加替换；不变不追加 | | | |
| S3 | 空目录退休 | | | |
| S4 | 不完整警告、恢复后清除 | | | |

**至少一条「用起来别扭」**：_

**结论**：通过 / 不通过：
