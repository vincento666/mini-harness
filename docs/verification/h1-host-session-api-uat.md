# H1 宿主会话 API — UAT 场次与观察表

**状态**：**agent 代跑（用户 2026-10-27 明确要求）**。ADR-0025 的「人坐在终端/浏览器前」签字仍待用户确认；本表记录的是同一套 U1–U5 在真实 deepseek 端点上的实际结果，不是 mock 判据。

**怎么算「办一件真事」**：不是跑判据，是用宿主 API 真的完成一次「开一个会话 → 让它改一个文件 → 看着它跑完 → 中途取消一次 → 断开再连上」。下面五场按顺序跑；每场把观察写进表里，最后写「别扭在哪」。

## 跑法与证据

- 客户端不是 `curl`，是两份一次性脚本（不入库）：`.tmp/h1_uat.py` 跑 U1、U2 拒绝、U3–U5；`.tmp/h1_u2_write.py` 强制 `write` 补跑 U2 的批准半边。
- 真实端点：`provider=deepseek`、`model=deepseek-chat`；`DEEPSEEK_API_KEY` 只从用户环境变量注入子进程，未写进仓库/日志。
- 会话：`ce364ee3794643ba9c3da9038e2026e6`（U1/U3/U4/U5 与 U2 拒绝）；`7a799f91041c47e5bfc631c30c2be010`（U2 严格 `write`）。工作区 `<tmp>/workspace`，先放 `notes.md`（`alpha\nbeta\n`）与 `a.md` / `b.md` / `c.md`。
- 日志：`.tmp/h1-uat-1793069816/sessions/ce364ee3794643ba9c3da9038e2026e6.jsonl`；`.tmp/h1-u2-write-1793071030/sessions/7a799f91041c47e5bfc631c30c2be010.jsonl`。
- 机器结果：`.tmp/h1-uat-1793069816/uat-results.json`（9 条 check，全部 `pass: true`）；U2 严格 `write` 的输出里 `CALLS=['read','write','read']`、`APPROVALS=[APPROVED]`、`NOTES='TODO\nbeta\n'`、`RESULT PASS`。
- 服务退出码：`0`；日志最后一条是 `session/end`。

## 观察表

| 场次 | 动作 | 预期 | 实际观察（命令 / 日志 / 截图） | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| U1 | 建会话 + 两句话 | 202 / 排队 / 两段顺序 | `POST /sessions` 201；msg1 202 `s1` `queued=false`；第一段进行中 msg2 202 `segment_id=null` `cursor=5` `queued=true`；`segment_starts=["s1","s2"]`；两条 `user/message` 顺序与请求一致；最后 `idle` | **通过** | 无。第二句确实在 s1 进行中入队，s1 收尾后自动开 s2 |
| U2 | 批准一次 / 拒绝一次 | OK / FENCE_DENIED / 会话继续 | **严格 write 补跑**（`7a799f91041c47e5bfc631c30c2be010`）：模型调用序列 `read → write → read`；批准 `call_00_BD9hxY6WAhfSAlWs2qFX1932` 200 → `approval/response=APPROVED`、该调用 `tool/result=OK`，`notes.md` 实得 `TODO\nbeta\n`；拒绝（原 U1 会话 `call_00_dNRMM0yFshZutuV7ab2U6340`）200 → `DENIED`、`DENIED_BY_APPROVAL`、段 `s3` `FENCE_DENIED`、`b.md` 未变、会话 `idle` | **通过** | 第一次 U1 会话里模型用 `edit` 改第一行；`edit` 与 `write` 都走同一审批门，但语义不同（见下）。本行改用强制 `write` 的独立补跑作为验收证据 |
| U3 | 段中取消再继续 | ABORTED / 新段正常 | 长任务 202；1 s 后 `POST /cancel` 202 `{"cancelled": true}`；段 `s4` `ABORTED`；随后「刚才做到哪了？」202，段 `s5` `MODEL_COMPLETED`；日志有 `error/abort`；会话未结束 | **通过** | 模型在取消前已发起四个 `read`，取消落在派发前，四个调用都得到「取消在派发之前置位，这个调用没有开始：read」；取消只停 s4，s5 正常 |
| U4 | 断线 + snapshot 重连 | snapshot 后只送新帧 | 断线前读到 durable 帧 `id=0 session/start`、`id=1 segment/start`；断开后 `?snapshot=1` 第一帧是 `event: snapshot`，`last_seq=95`（重连前日志 93、重连后 95），`status=running`，`messages` 是折叠后的 20 条列表；会话未因断开改变 | **通过（快照部分）** | `93→95` 的两条在途记录被 snapshot 吸收，这是快照的**追赶**，不是丢帧；snapshot 之后的 durable 帧应从 `last_seq+1` 起。本场只读 snapshot 帧，**after-snapshot 连续帧由 10.1 完成判据验证**（`test_the_host_completion_script` 断言新帧 `id == last_seq + 1`） |
| U5 | 无 token / 穿越 / 第二会话 / DELETE / 重启 | 401 / 400 / 200 / 409 / 列表空 | 无 token `GET /sessions` → 401；带 token `GET /sessions/%2E%2E/secret/events` → 400；创建第二个会话后 `GET /sessions` 列出 2 条；第二会话段进行中 `DELETE` → 409；重启服务（旧进程退出码 0）后 `GET /sessions` 200 `{"sessions": []}` | **通过** | H1 不承诺跨进程会话列表（M11 的 session index 再补）；重启后列表为空是成文边界，不是缺陷 |

**至少一条「用起来别扭」**：`edit` 与 `write` 不是同义词——`write` 覆盖整文件，`edit` 按读到的内容做 CAS（内容变了是 `STALE_EDIT`）。U2 第一次用 `edit` 只是碰巧与 `write` 结果相同；严格验收必须点名工具。另 U4 的 snapshot 会把 `last_seq` 之前的在途记录折叠进 `messages`，客户端要用游标续读，不能把「快照后不补历史帧」误判成丢帧。

**结论**：**通过（agent 代跑；U2 已按 `write` 严格补跑）**。U1、U2、U3、U5 通过；U4 的快照与断线不影响会话通过，after-snapshot 的连续帧由 10.1 判据覆盖。日志：U1/U3/U4/U5 在 `ce364ee3794643ba9c3da9038e2026e6`；U2 严格 write 在 `7a799f91041c47e5bfc631c30c2be010`。ADR-0025 要求的人跑签字仍待用户确认。
