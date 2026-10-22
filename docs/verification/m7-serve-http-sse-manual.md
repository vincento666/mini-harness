# M7 人手验收（`m7-serve-http-sse`）

**状态：agent 这一半跑完（2026-10-22 16:06–16:07，真 PowerShell 终端、真 `minihns serve` 子进程、真 HTTP 客户端，三场）；Ctrl-C 那一半与真模型那一半待人跑（见最后一节）。**

task 9.1 列的三件事里，「一次真事（带工具调用的会话，客户端读到底 + 中途断开再带游标重连续读）」与「一次溢出（小窗口）」跑到了；「一次取消（Ctrl-C）」在 Windows 上判不了——沿用 M3 立下的边界，seam ⑥ 那条 `test_sigint_in_a_serve_subprocess_exits_with_five` 在本机是 skip 状态，Linux runner 上才会跑。这一半补的是判据没覆盖的那一面：真客户端在真会话中途连上时到底看到什么、挂断与重连在流上留下什么痕迹、溢出那一场进程侧的收尾长什么样。

跑法：工作区是 `.tmp/m7-manual/workspace/s1` / `s2` / `s3`（gitignored），日志落在各自的 `sessions/`。provider 是 mock——agent 的子进程里没有密钥，真模型那一半待人跑（最后一节）。客户端是 `httpx.AsyncClient(trust_env=False)`：本机环境里有 `HTTP_PROXY` 与带 `[::1]` 的 `NO_PROXY`，httpx 解析后者会当场抛 `InvalidURL: Invalid port: ':1]'`，与判据里同一处坑。脚本是 `.tmp/m7_serve_demo.py` 与 `.tmp/m7_probe3.py`（gitignored，不进判据）。端口是现场绑 0 拿的（10922 / 10926 / 10932）。三场都是 `--provider mock --yes`，`--yes` 是因为子进程的 stdin 不是 tty。

## 场景 A：一次真事，客户端从会话中途连上、读到底（session `89a14aaeeff549bf9da7330fbee9c0e8`）

真事是「把 `greet.py` 跑一遍并把它的输出读回来」：fixture 三回合——`bash python greet.py`（脚本打两行、睡 2 秒）→ `read greet.py` → 停。客户端在 serve 起来之后连上 `GET /events`，一路读到流自己关掉。退出码 0，日志 23 条记录，流上 23 帧。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 会话中途连上的客户端看到什么 | 不是「从连接那一刻起」，是从第一条起 | ✓ 首帧 `id: 0` 就是 `session/start`——tail 从偏移 0 读起，晚连的客户端补得齐全 |
| 一帧对一条记录 | 23 帧对 23 条 | ✓ 帧数 == 记录数 |
| `id` 就是日志的 `seq` | 逐一对应 | ✓ `['0' … '22']` == `[0 … 22]` |
| `event` 就是日志的 `type` | 逐一对应 | ✓ 23 个类型一字不差，含 `context/assembled`、`tool/call`、`tool/result` |
| `data` 是整行记录的 JSON | 反序列化之后 `seq` 与 `id` 相等 | ✓ 23 帧全等；`data` 里 `schema_version` / `session_id` / `ts` / `payload` 都在，不是只有 payload |
| 工具结果在流上 | `tool/result` 两帧 | ✓ 一帧 `outcome=OK` 是 `bash` 的输出，一帧 `outcome=OK` 是 `read` 的带行号内容 |
| 会话收尾即进程退出 | 流关掉、进程退出码 0 | ✓ 流自己关，`process.wait()` 立刻返回 0 |
| stdout 只打 session id 一行 | 一行、没有别的 | ✓ stdout 是 `89a14aaeeff549bf9da7330fbee9c0e8`，一个字符都不多 |
| 监听地址在 stderr | 不在 stdout、不在日志 | ✓ stderr 只有 `serve 监听 http://127.0.0.1:10922`；日志里没有这条，stdout 里也没有 |
| `entry` 是 `serve` | `session/start` 的 payload 里 | ✓ `"entry": "serve"`，同一份 payload 还带着 `sandbox: workspace-write`、`approval: auto`、`window: 128000`、`tools` 六件 |

## 场景 B：读满四帧就挂断，再带游标重连续读（session `a434ebf08e0547779cc18ab8322782ae`）

真事是「跑一条会睡五秒的命令」：fixture 两回合——`bash python slowly.py`（睡 5 秒）→ 停。客户端连上、读满 4 个**完整**帧就主动挂断，歇 0.3 秒，带着 `Last-Event-ID: 3` 重连，读到流关掉。退出码 0，日志 16 条记录。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 挂断不影响会话 | 会话照跑完、退出码 0 | ✓ 退出码 0，日志 16 条齐全，最后四条 `model/response` / `turn/end` / `segment/end` / `session/end` |
| 挂断不往日志里写任何东西 | 没有「客户端走了」这类记录 | ✓ 16 条里没有一条与连接有关 |
| 游标就是 `seq` | 带 `Last-Event-ID: 3` 重连 | ✓ 重连后第一条是 `id: 4` |
| 不重不漏 | 两段合起来覆盖全部 `seq` | ✓ `['0' … '15']`，重复 False、漏集合空 |
| 游标也可以走查询参数 | `?from=` 与 `Last-Event-ID` 同一条判据 | 本场走的是 header；`?from=` 由 seam ⑥ 的判据钉着 |
| 挂断发生在帧中间是常态 | —— | ✓ 见「别扭」第 2 条：第一版客户端数帧时把没收尾的半帧也算一帧，于是它在 `id: 3` 之后挂断，游标记成 3，重连从 4 起——**记录 3 它永远没拿到** |

## 场景 C：小窗口溢出（session `8dd7b88352eb48a999325a89a0f696b2`）

`--window 66000 --reserve 100`（触发线 364）加 `-p "任务"×1000`（预算读数 524）。客户端这一场**没挤进去**（见「别扭」第 1 条），观察到的是进程侧的收尾。

| 观察点 | 期望 | 实际 |
|---|---|---|
| 溢出塌成进程退出 | 退出码 4 | ✓ 退出码 4 |
| 收尾四条齐全 | `error/context` + `turn/end` + `segment/end` + `session/end` | ✓ seq 3 / 4 / 5 / 6，日志共 7 条 |
| 码是 `CONTEXT_WINDOW_EXCEEDED` | `error/context` 的 payload 里 | ✓ 是它；`session/end` 的 `stop_reason` 也是它 |
| stdout 只打 session id 一行 | 一行 | ✓ `8dd7b88352eb48a999325a89a0f696b2` |
| stderr 说人话 | 码加 detail | ✓ `CONTEXT_WINDOW_EXCEEDED: 无可遮蔽的内容，预算读数 524 已超过触发线 364`，上面一行是 `serve 监听 http://127.0.0.1:10932` |
| 没有 Traceback | 崩溃不算收尾 | ✓ stderr 只有那两行 |
| 监听先于装配 | stderr 上「监听」那行在溢出那行之前 | ✓ 顺序就是监听、溢出 |

## 别扭在哪（六条）

1. **溢出那一场的事件流窗口只有几十毫秒，客户端挤不进去。** 溢出发生在第一次装配，装配之前没有可遮蔽的内容，于是会话从第一条记录到最后一条只用了 9 毫秒（`08:07:02.897` → `08:07:02.906`）。`.tmp/m7_probe3.py` 试了三种客户端：从服务器起来之前就开始敲端口的（每 5 毫秒一次、每 20 毫秒一次）、把 fixture 写成 40 MB 好让装配慢一点的（装配在绑定之后，确实把窗口拉长了）——都没连上。这台机器上**抢在监听之前发出的 SYN 会被黑洞到超时**而不是当场被拒：一次尝试耗掉 0.5 秒到 10 秒，等它超时回来服务器早退出了（最后一次延迟 2.6 秒再连，拿到的是快拒绝 `WinError 10061`，说明监听确实已经关了）。后果是**「溢出在事件流上长什么样」这条没有任何判据**：seam ⑥ 的溢出判据看的是退出码、日志与 stdout，不看流。记进 ADR-0002 第 55 条。
2. **游标是「最后一条完整帧」的凭据，半帧也算读到过。** 第一版客户端把「没收尾的半帧」也数进帧数，于是在只收到 `id: 3` 一行（没有 `event:`、没有 `data:`）时就挂断，游标记成 3，重连从 4 起——记录 3 它永远没拿到，而它自己不知道。改成只数完整帧之后才是场景 B 那样。SSE 的游标语义在这里露了一次面：**客户端凭什么说自己读到了哪儿，只有它收到过的那一帧的 `id`**；服务端不记账，日志也不记。
3. **命令的中文输出在流里是 U+FFFD。** 场景 A 的 `bash python greet.py` 打的是中文，而那个孙进程的输出编码是控制台代码页（GBK），mini 按 UTF-8 lossy 解码，于是 `tool/result` 的 content 是 `'退出码 0\n???\r\n'`——两行中文塌成替换字符。同一场里 `read greet.py` 读回来的中文是好的（文件读是 strict 那一头）。这正是 ADR-0002 第 30 条结案时写下的那条边界在真 run 里的样子：DSH 的子进程输出也是 `Buffer.toString("utf8")`，一样 lossy。设 `PYTHONIOENCODING=utf-8` 再跑，中文就正常。
4. **晚连的客户端拿到的是全部记录，不是「从连接那一刻起」。** tail 从偏移 0 读起，所以场景 A 里那个在会话跑起来之后才连上的客户端补得齐全。这方便，但也意味着**同一个会话里先后连上的客户端看到的不是同一个起点**：先连的看到增量，后连的看到全量。将来加 snapshot 帧（ADR-0021 的 Consequences）就是给这件事一个明确的说法。
5. **`serve 监听 http://127.0.0.1:10922` 这行只在 stderr 上。** 它不在日志里（日志不写 HTTP 事实，规格钉着），也不在 stdout 上（stdout 只有一行 session id）。人要知道在哪个端口，得看 stderr；而脚本要拿端口，只能读 stderr 或者自己指定 `--port`。
6. **现场绑 0 拿到的端口落在 10000 段，而 Windows 的 excluded port range 覆盖 1048–1623 与 50000–50059。** 默认 `--port 19400` 不在被排除的段里；`netsh int ipv4 show excludedportrange protocol=tcp` 可复现。这台机器上「连一个没监听的端口」之所以慢，与这个表有没有关系没查——只确认了默认端口不在里面。

## 待人跑的那一半

**Ctrl-C（task 9.1 的第三场）**：Windows 上给真实子进程送 Ctrl-C 这条路从 M3 起就没通过（seam ⑥ 的四条 SIGINT 子进程判据在本机全是 skip：`run` 一条、`chat` 两条、`serve` 一条）。Linux runner 上跑法：

```bash
# 会话里放一条会睡 30 秒的 bash 命令，等日志里出现 "tool/call" 之后按 Ctrl-C
uv run minihns serve --http -p "跑一条会睡三十秒的命令" --port 19400 \
  --provider mock --fixture slow.json --yes
# 另一个终端：curl -N http://127.0.0.1:19400/events
# 期望：退出码 5；stderr 上有 ABORTED 那行、没有 Traceback；
# 日志最后四条 error/abort / turn/end / segment/end / session/end，
# session/end 的 stop_reason 是 ABORTED；事件流跟着会话一起关。
```

**模型层（task 9.2）**：真 provider 真模型下的事件流。本机可用的端点是 Strata（`S:\Develop\AIGC\Strata\Strata`，`--port 8300`）：

```bash
# 终端 1
uv run minihns serve --http -p "读一下 docs/CURRENT.md，告诉我门禁四道是什么" \
  --port 19400 --provider openai --base-url http://127.0.0.1:8300/v1 \
  --model qwen3.8-flash-next-iq3_xxs --api-key-env MINIHNS_STRATA_KEY
# 终端 2
curl -N http://127.0.0.1:19400/events
# 期望：流上的帧与 sessions/<session id>.jsonl 逐行一致；`read` 真的读了仓库里的文件；
# 会话收尾即进程退出、stdout 只打 session id 一行。
# 中途 Ctrl-C 一次，看流是否跟着会话一起关、退出码是不是 5。
```

密钥只在环境变量里（`MINIHNS_STRATA_KEY`），agent 的子进程里没有它，所以这一半只能人跑。跑完把观察补在本节下面。
