# 里程碑换序：M4（真实 Provider）先于 M3（bash / 并发 / 平台层与 CI）

学习目的的项目在 M1–M3 期间没有任何"像助手"的可用性：M1 与 M2 的完成判据全是 mock fixture 驱动的 CLI 断言，跑绿了就结束。人裁决把真实 Provider 提前，让内核在撞进 `bash`、超时、平台差异之前，先被真实模型跑一遍。执行顺序定为 **M1 → M2 → M4 → M3 → M5 → M6 → M7**，change id 不变（先做 `m4-real-provider-deepseek`，后做 `m3-bash-concurrency-timeout`）。

1. **为什么换。** ① 真实模型是唯一能暴露「前面所有抽象是不是白设计」的输入：`provider/contract.py::ToolSpec` 只有 `name` 与 `description`，`AssistantTurn.finish_reason` 目前只是记录、分支实际看 `tool_calls` 有没有，一轮多调用要靠 `parallel_tool_calls`——这三条只有真实模型会逼你回答。② M4 与 M3 之间没有技术依赖：`bash` 不需要真实模型，真实模型不需要 `bash`。③ 学习动机：中间插一个能对话的里程碑，比连着两个纯内核里程碑更容易持续。
2. **代价：跨平台与 CI 整体后移。** 「同一套判据在 Windows 与 Linux 各跑一遍全绿、门禁由 CI 跑」本来挂在 M3 上，现在跟着 M3 一起后移；M4 的实现与 smoke 按 Windows + 真实网络写，Linux 侧到 M3 才验证。M2 起累积的 Windows 绑定点（路径大小写与 junction、tty 检测、SIGINT）继续欠着，到 M3 一次性还。
3. **代价：CI 不能持 API key。** 门禁那道必须离线可跑，所以 CI 只跑 mock 判据；真实 Provider 的 smoke 归入人手验收，不进 CI。这条是换序之后才出现的约束。
4. **代价：`ToolSpec` 缺参数 schema 从「留给 M4」变成 M4 的阻塞项。** 现状是模型只看到工具名与描述，参数形状只在派发侧校验（`args_model`）；不补 JSON schema，真实模型只能猜参数。M4 的 tasks 里这一条排在适配器之前。

Considered options：先写一个「人当模型」的 stdin Provider 原型（否：不接真实模型就看不到 schema、重试、并行调用的真实代价，而原型不进规格）；把 M6 的 REPL 提前（否：撞会话边界——`EventLog` 每 session 一个新文件、`fold` 的头部只取自一条 `session/start`，而续会话的 `--resume` 在 MVP 不做清单里；且取消目前只在回合边界被看到、窗口预算还不存在）；保持 M3 先（否：真实对话推迟两个里程碑）。

同时裁决的第二件事：**每个里程碑的完成判据里加一条人手验收**——用真实工作区干一件真事，观察记进 `docs/verification/`。写进了 `docs/roadmap.md` 与 `AGENTS.md`。

覆盖的范围：`docs/roadmap.md` 的里程碑顺序与完成判据。
