# 真实端点回来的东西

这里的 fixture 不是手编的桩数据，是从真实端点实际回过的产物里裁下来的。判据读它们，为的是「形状是真的」，不是「形状像」。

## `context_overflow_400.json`

- **来源**：session `92c155ba16fb4a4aa7bcbf931d5ba098`（`minihns chat`，本机 Strata 端点 `http://127.0.0.1:8300/v1`，模型 `qwen3.8-flash-next-iq3_xxs`，窗口 128000、保留 8192）。
- **怎么拿到的**：把那份日志 `seq <= 67` 折成消息（19 条），照 `_compact_if_over_line` 当时的形状重发一次——带不带 `tools` 都是 400；只留「system 加 user 两条」的对照场是 200。探针 `.tmp/probe_compaction.py`，结论记进 `docs/adr/0022-model-features-need-a-real-endpoint-gate.md`。
- **为什么值得留**：错误对象里**没有** `error.code`，只有 `type` 与 `message`；provider 主规格与既有判据只认 `error.code == "context_length_exceeded"`，所以这个真实形状当时被判成了 `PROVIDER_HTTP_STATUS`。
- **裁掉了什么**：只留错误对象本身。同一场探针另两次回复的 token 数（222468）与端点的 `timings` 字段没有留下——判据判的是形状，不是那一次的具体数字。

## `compaction_summary.json`

- **来源**：session `d31a7790e92c49fcb47d9a5dc8b25636`（`minihns chat`，本机 Strata 端点 `http://127.0.0.1:8300/v1`，模型 `qwen3.8-flash-next-iq3_xxs`，窗口 80000、保留 100）。那次跑真发生了两次压缩，这条是第一次（seq 13，回合 `t2`）；摘要正文是真端点回的，不是桩。
- **怎么拿到的**：跑完直接读那份日志（`.tmp/realchat/sessions/`），全程记录见 `docs/verification/fix-compaction-and-context-overflow-manual.md`。
- **为什么值得留**：遮蔽反馈那一行（seam ⑥）只读 payload 里 `shadowed_range` 两端与 `tokens_before` / `tokens_after` 这四个键。键名与形状在这里钉住，实现与屏幕两边不必互相猜。
- **裁掉了什么**：`summary` 只留「任务 / 已做 / 下一步」三句的骨架，原文里那些行号与 `abcdefghij` 的细节没有留下。同一 session 的第二次压缩（seq 32，`15364 → 13239`）没有留成第二份 fixture——形状一样，数字不同，判据判的是形状。

## 规矩

fixture 只留字段形状与必要的短句，不整段照抄真实回复正文；每个 fixture 在本文件里写明来源 session id。CI 不持 API key（handoff 决策 6），真实端点那一层是完成判据、不是 CI 判据，见 ADR-0022。
