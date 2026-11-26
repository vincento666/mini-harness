# 任务：merge-reasoning-stream

前置：工作区必须干净（先提交本轮改动）。**未完成 1.1 不得动合并。**

- [x] 1.1 提交当前工作区（三个归档 + 政策 v3），并 `uv run pytest -q` 确认基线绿
- [x] 1.2 建 `merge/reasoning` 分支，`git merge --no-ff origin/change/reasoning-mode-and-budget`，按 design D2 表逐文件解冲突（8 文件 17 处）
- [x] 1.3 词表迁移：`segment/*→turn/*`、旧 `turn/*→step/*`、`segment_id→turn_id`、中文「回合/段→轮」；逐处判量词，禁止机械替换
- [x] 1.4 政策与版本对齐：丢弃分支旧政策文本，用 main 的 `GOAL_POLICY_VERSIONS`（v3）；`session/start.goal_policy` 仍写 v3
- [x] 1.5 `specs/reasoning/spec.md` 逐句核对 v2 词表后落主规格；`chat-repl` 补 `[thinking]` 行、`provider` 补 reasoning 字段、`event-log` 补 `model/attempt`
- [x] 1.6 测试：分支自带 reasoning/golden 测试按新词表改名并跑绿；补思考帧判据（`[thinking]` 恰一次、思考不进 stdout、取消半句保留不回归）
- [x] 1.7 门禁：全量 **963 passed / 6 skipped**、ruff、mypy --strict、`openspec validate --all --strict` 31 项、覆盖率 **98.50%**（`scripts/gates.sh` + `scripts/coverage-report.sh`）；契约要求的变异 M1/M2 均被杀死，记在 `docs/verification/merge-reasoning-stream-mutation.md`
- [x] 1.8 真实端点一场（reasoner）：`model/response.blocks` 保序、SSE `reasoning/delta` 与 `model/delta` 分离、usage 不重复计；记录到 `docs/verification/merge-reasoning-stream-real-endpoint.md`（顺带修掉流式只认 `reasoning_content`、不认 OpenRouter 归一 `reasoning` 的缺陷，见该文第 0 节）
- [ ] 1.9 tty 人跑一场：`[thinking]` 恰一次、思考实时、正文不进 stderr 混流、`[answer]` 位置正确（ADR-0025）；手册 `docs/verification/merge-reasoning-stream-uat.md`
- [ ] 1.10 归档本 change；`docs/CURRENT.md` 把「思考帧未合入」从开放缺口移除
