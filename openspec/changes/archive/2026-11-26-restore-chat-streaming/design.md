# 设计：restore-chat-streaming

## D1 复用 `SessionEnv.on_delta`，不新增 provider 路径

`provider` 规格已经有唯一方法 `generate(messages, tools, signal, on_delta=None)`；host 的 SSE 已经在用它。本 change 只把 CLI 的 env 也接上同一个 sink。

否决「新增 `generate_stream`」：mock 与真实适配器要各维护两套调用形状，而 `turn_loop` 已经用 `_forward_delta` 把 `(step_id, text)` 包成 provider 认的 `text`。否决「在 provider 里直接打印」：壳的显示职责不能下沉到模型适配器。

## D2 渲染器住在 CLI，不进内核

`sink` 的形状是 `(step_id, text)`；stdout / stderr 的分流、`[answer]` 标记、换行时机都是**终端适配**。内核只把 `step_id` 交出去，不知道有人在看。

渲染器只做三件事：写正文、打一次 `[answer] `、轮末收行。它不读日志——缺正文的步由钩子把内容送进来（D3.1）。

## D3 收尾按「轮」，不按「输入」

m13 之后一条输入可以连开多轮（目标续跑）。渲染器的 `finish()` 挂在每次 `run_turn` 返回之后：写换行、清空「本轮已打 `[answer]`」标记。

若按输入收尾（旧实现是 `finish_segment()`），目标连续三轮会把三段正文挤成一行；若完全不收尾，`[answer]` 只出现一次，人也分不清轮边界。目标轮之间的 `[轮] n/cap` 仍由入口写在 stderr，顺序保持在正文之前。

## D3.1 回退在「步末」，不在轮末

`_print_new_replies` 是轮末统一投影。如果同一轮里第一步没有 delta、第二步流了 delta，轮末才回退第一步，屏幕顺序会变成 2→1——这是复核指出的 blocker。

解决办法是给 `SessionEnv` 加一个可选钩子 `on_step_end(step_id, content)`：`turn_loop` 在该步的 `step/end` 落盘之后、下一步 `step/start` 之前调用它，`content` 是该 `step_id` 下 `purpose` 不在 payload 里的那条 `model/response.content`。CLI 的渲染器在钩子里判断：这一流没有非空 delta、且 `content.strip()` 非空，就当场打印，并把这个 `step_id` 记进「已输出」集合；轮末的 `_print_new_replies` 跳过整个集合（流式的、回退的都算），保证同一步恰输出一次。

钩子只由 CLI 的 `--stream` 路径安装：`--no-stream` 不装（由轮末投影打印），`host` 不装（由 SSE 的 durable 帧承载）。钩子不得抛异常——实现里捕获并转成 `error/*`，否则会留下 `model/response` 而无 `step/end` 的半截边界。最后一步没有「下一步」，仍要在 `break` 之前调用一次。

否决「在 `turn_loop` 里对所有 sink 补发一次完整正文」：host 也用同一个 `on_delta`，补发会让 SSE 客户端收到「增量 + 整段」两份。钩子只由 CLI 传，host 与 `--no-stream` 都不受影响。

## D4 去重按「步」

`model/response` 的键是 `step_id`（一个轮多步，每步一条）。渲染器维护「已输出」集合：流过非空正文 delta 的步加进去，步末回退打印过的步也加进去。`_print_new_replies` 读到集合里的步就跳过。

`printed` 游标仍按**非 `purpose`** 的 `model/response` 条数推进：跳过打印不等于不计数，否则下一轮会把旧回复重打一遍；`purpose`（请求级压缩摘要）本来就不打，两个口径必须一致，否则 `compaction` 之后的 `--resume` 会把首条新回复算漏（复核指出的 major）。

## D5 思考流已实现、未合入（不是 deferred）

`on_reasoning` 在当前 **main** 的 `SessionEnv` 不存在，`openai_compat` 也不解析 `reasoning_content`。但这件事**不是没做**：`origin/change/reasoning-mode-and-budget` 领先 main 50 个提交（28 项 tasks 已勾 27 项，只剩 7.2 UAT 人跑），已经把 assistant message 升级成有序 content blocks、接了 reasoning sink 与 SSE；`origin/change/chat-streaming-shell` 领先 47 个提交，其 `cli/main.py` 里已有 `[thinking]` 开始标志、`on_reasoning` 与 thinking 结束行（`6857ce4` 是分支内的合并，不是 main）。两条分支都**没合进 main**，所以当前 main 看不到思考帧。本 change 只做正文流式，不复刻、也不合并这两条分支；后续把已实现的能力合入/迁移到当前主线（并处理 v2 改词、词表与命名冲突）是独立工作，不是新开 change 重做。

## D6 取消在「写 response 之前」按是否流过正文分叉

`turn_loop` 现在的判据只看「有没有 sink」：

```
if cancel.is_set() and env.on_delta is not None:
    return _abort_turn(log, step_id, steps)
```

但「装了 sink」不等于「这一步真的流过正文」：provider 可能不流式、fixture 可能没 delta、也可能只发空串。这时模型已经完整返回，取消却会走 `_abort_turn`，把整段回复吞掉——复核指出的 major。

判断点在 `provider.generate` 返回之后、写 `model/response` 之前。在这一刻：

- `streamed_any` 为真（本步发过非空正文 delta）→ `_abort_turn`，不写半条；
- `streamed_any` 为假 → 写完整 `model/response`，再由步末回退把正文显示出来。

`streamed_any` 只统计**非空** text；每次可能产生最终回复的 `generate` 调用前重置（包括上下文溢出的压缩重试，否则上一次尝试的 delta 会污染判断）。

取消落在**工具派发**阶段时，`model/response` 早已落盘，不会走到这个判据；它由既有工具取消逻辑收尾，日志本来就是完整的。三条路径的共同不变量是：**`model/response` 要么不存在、要么完整，永不写半条**。

## D7 默认 `--stream`

沿用 2026-11-03 的人裁：shell 体验优先。`--no-stream` 保留两个用途：逐点兼容（脚本、管道断言）与问题分诊（怀疑流式时才关掉对照）。

代价是「默认输出时序改变」。内容、顺序、退出码都不变，且 `--no-stream` 能回到旧行为，所以不构成破坏性变更。

## 风险与边界

- **不 flush 就没有流式**：stdout/stderr 是管道时自带缓冲；每个 delta 后必须 flush。`[answer]` 与 `[轮]` 也 flush，否则终端里两行会跑到正文后面。
- **`[answer]` 在无思考流时信息量有限**：保留它是为了将来 `[thinking]` 回来时协议不用改；每轮一次，不重复。
- **渲染器不进 host**：若将来 host 的 chat 也要复用，再把它从 `main.py` 提到独立模块；本 change 不做这层抽象。
- **空 delta 不算流式**：`text == ""` 直接返回，既不打标记也不记入 `streamed_steps`，否则「provider 发了空 delta」会被误判成「已流式」，导致该步正文被吞。
