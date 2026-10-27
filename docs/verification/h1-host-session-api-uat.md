# H1 宿主会话 API — UAT 场次与观察表

**状态**：**agent 代跑（用户 2026-10-27 明确要求）**。ADR-0025 的「人坐在终端/浏览器前」签字仍待用户确认；本表记录的是同一套 U1–U5 在真实 deepseek 端点上的实际结果，不是 mock 判据。

**怎么算「办一件真事」**：不是跑判据，是用宿主 API 真的完成一次「开一个会话 → 让它改一个文件 → 看着它跑完 → 中途取消一次 → 断开再连上」。下面五场按顺序跑；每场把观察写进表里，最后写「别扭在哪」。

## 跑法与证据

- 客户端不是 `curl`，是一次性脚本 `.tmp/h1_uat.py`（不入库）：起真实 `minihns host --http` 子进程，用 httpx 依次跑 U1–U5。
- 真实端点：`provider=deepseek`、`model=deepseek-chat`；`DEEPSEEK_API_KEY` 只从用户环境变量注入子进程，未写进仓库/日志。
- 会话：`ce364ee3794643ba9c3da9038e2026e6`；工作区 `<tmp>/workspace`，先放 `notes.md`（`alpha\nbeta\n`）与 `a.md` / `b.md` / `c.md`。
- 日志：`.tmp/h1-uat-1793069816/sessions/ce364ee3794643ba9c3da9038e2026e6.jsonl`
- 机器结果：`.tmp/h1-uat-1793069816/uat-results.json`（9 条 check，全部 `pass: true`）
- 服务退出码：`0`；日志最后一条是 `session/end`。

## 观察表

| 场次 | 动作 | 预期 | 实际观察（命令 / 日志 / 截图） | 结论 | 别扭在哪 |
|---|---|---|---|---|---|
| U1 | 建会话 + 两句话 | 202 / 排队 / 两段顺序 | `POST /sessions` 201；msg1 202 `s1` `queued=false`；第一段进行中 msg2 202 `segment_id=null` `cursor=5` `queued=true`；`segment_starts=["s1","s2"]`；两条 `user/message` 顺序与请求一致；最后 `idle` | **通过** | 无。第二句确实在 s1 进行中入队，s1 收尾后自动开 s2 |
| U2 | 批准一次 / 拒绝一次 | OK / FENCE_DENIED / 会话继续 | 批准 `call_00_LDcS4kxh0hPoJ5ZEL1U40474` 200；`approval/response=APPROVED`；`tool/result=OK`（模型用 `edit` 把 notes.md 的 `alpha` 换成 `TODO`，又读回核对）；`notes.md` 实得 `TODO\nbeta\n`。拒绝 `call_00_dNRMM0yFshZutuV7ab2U6340` 200；`approval/response=DENIED`；该调用 `DENIED_BY_APPROVAL`；段 `s3` 以 `FENCE_DENIED` 收尾；`b.md` 仍是 `b.md 的内容\n`；会话 `idle` | **通过** | 模型对「改第一行」选择了 `edit` 而不是 `write`；两者都会改动、都走审批，所以结果等价。若壳的 UI 按工具名展示，要接受 `edit` |
| U3 | 段中取消再继续 | ABORTED / 新段正常 | 长任务 202；1 s 后 `POST /cancel` 202 `{"cancelled": true}`；段 `s4` `ABORTED`；随后「刚才做到哪了？」202，段 `s5` `MODEL_COMPLETED`；日志有 `error/abort`；会话未结束 | **通过** | 模型在取消前已发起四个 `read`，取消落在派发前，四个调用都得到「取消在派发之前置位，这个调用没有开始：read」；取消只停 s4，s5 正常 |
| U4 | 断线 + snapshot 重连 | snapshot 后只送新帧 | 断线前读到 durable 帧 `id=0 session/start`、`id=1 segment/start`；断开后 `?snapshot=1` 第一帧是 `event: snapshot`，`last_seq=95`（重连前日志 93、重连后 95），`status=running`，`messages` 是折叠后的 20 条列表；会话未因断开改变 | **通过** | snapshot 与日志之间有 2 条在途记录，所以 `last_seq` 落在 93–95 之间；判据用闭区间核对，未把「重连瞬间仍在追加」误判成不一致 |
| U5 | 无 token / 穿越 / 第二会话 / DELETE / 重启 | 401 / 400 / 200 / 409 / 列表空 | 无 token `GET /sessions` → 401；带 token `GET /sessions/%2E%2E/secret/events` → 400；创建第二个会话后 `GET /sessions` 列出 2 条；第二会话段进行中 `DELETE` → 409；重启服务（旧进程退出码 0）后 `GET /sessions` 200 `{"sessions": []}` | **通过** | H1 不承诺跨进程会话列表（M11 的 session index 再补）；重启后列表为空是成文边界，不是缺陷 |

**至少一条「用起来别扭」**：U2 的「改第一行」被模型实现成 `edit` 而不是 `write`——审批与结果都对，但如果壳按工具名给图标/文案，需要同时接受两种会改动的工具。另 U4 的 snapshot 与日志存在 2 条在途记录，壳要用 `last_seq` 游标而不是「快照等于最终日志」来续读。

**结论**：**通过（agent 代跑）**。U1–U5 全部实际跑通；日志 session id `ce364ee3794643ba9c3da9038e2026e6`，退出码 0，最后一条 `session/end`。ADR-0025 要求的人跑签字仍待用户确认。
