# M11 真实端点验收

**日期**：2026-11-05。**端点**：DeepSeek `deepseek-reasoner`（真实 key，不进日志）。
**session**：`c30432c87e0d478ba0e6e24faba39acd`。

## 观察

1. 第一次 `chat`：写 `session/start`，回答 `2+2 等于 4。`。
2. `chat --resume <id>`：
   - 没有新建 `session/start`；
   - 回答 `3+3 等于 6。`；
   - 同一份日志继续追加。
3. `minihns replay <id>`：
   - 两个装配点 `seq=4`、`seq=13` 都 `OK`；
   - `t1` / `t2` 都 `MODEL_COMPLETED`；
   - final context 同时含两轮 user/assistant。
4. 日志仍是 append-only；旧记录未改写。

## 结论

真实端点下 `resume` 续写与 `replay` 逐点一致；M11 的恢复路径在真实 provider 上成立。
Host 重启后的 resume、schema 跳版拒绝、cache 加速由单测/黑盒判据覆盖。
