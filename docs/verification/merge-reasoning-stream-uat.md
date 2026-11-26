# merge-reasoning-stream — UAT 场次手册（tty 手感）

**状态**：**待人跑**。机器那一半已完成（1.7 门禁、1.8 真实端点，见 `merge-reasoning-stream-real-endpoint.md`），这一半是**手感**，只能人跑（ADR-0025）：tty 下思考是否真的在刷、`[thinking]` 是否只出一次、正文有没有被思考污染。**这张表没填完不得归档。**

## 跑之前的准备

```bash
cd /Users/vincento/work/develop/mini-harness
set -a && . ~/.config/minihns/openrouter.env && set +a
```

必须在**真终端**里跑（不是管道、不是 `-p`）：`chat` 的流式渲染只在 tty 上走增量分支，管道下看到的是一整段，手感判据不成立。

## 场次表

| # | 怎么跑 | 看什么 | 通过判据 | 状态 |
|---|---|---|---|---|
| 1 | 真终端跑下面命令，把提示词打进去；等它答完，再按 Ctrl-D 退出 | 思考是不是**边想边出**：`[thinking] ` 之后文字一点一点长出来，而不是停两秒一次性砸出整段 | ① `[thinking]` 前缀**恰好出现一次**，没有重复的 `[thinking]`/`Thinking…` 行；② 思考期间终端光标在动、文字逐步追加，肉眼能看出「在流」；③ 思考**全部**在 stderr 那侧（终端上显示为思考原文，但 `--no-stream` 对比时不进正文） | **待人跑** |
| 2 | 接第 1 场，等 `[answer]` 出现后观察正文 | 正文与思考的边界 | ① `[answer] ` 出现在**正文开始处**、恰好一次；② 正文**不带** `[thinking]` 前缀同款标记，也不与思考文字粘在同一行；③ 答完后没有第二段重复正文（屏幕上正文就是最终那一份） | **待人跑** |
| 3 | 再接一句：`再说话，我中途打断一下`，等它开始输出思考后**立刻按 Ctrl-C** | 半句保留 + 收尾提示 | ① 已显示的思考/正文**留在屏幕上**，不整段消失、不重复一遍；② 出现 `[轮] 收尾 ABORTED`（或该轮对应的收尾行），提示符回到 `> `、进程**不退出**；③ 会话日志里该步是 `interrupted` 的 `model/response`（有 blocks 时）或 `model/attempt`，不是空记录 | **待人跑** |

**场次 1 命令**：

```bash
uv run minihns chat --provider openrouter --model qwen/qwen3.8-27b \
  --workspace .tmp/uat-reasoning-tty --session-dir .tmp/uat-reasoning-tty/sessions \
  --max-steps 2
```

**场次 1 提示词**（挑要真思考的，别给一句话就能答的）：

```
用三句话解释为什么天空是蓝色的，先想清楚再回答。
```

## 判据取不到时的兜底

- 若模型这一场几乎不思考（`[thinking]` 只有一两个词）：换提示词再跑一次，判据要求的是「有思考且流式」，不是「思考长度达标」。换两次都没有思考，记下 session id 说明模型这一场没触发思考，判据记为**不可判**，不算通过。
- 若终端是管道/Warp 之类会缓冲的壳：`[thinking]` 一次性出现属壳的行为，不算失败；换 Terminal.app / iTerm2 重跑一次再判。

## 观察记录

- （待人跑后填写：每场实际输出片段、session id、判据逐条勾、失败处的截图或粘贴）
