# Tasks

## 1. stream/end 实现（唯一代码缺口）

- [ ] 1.1 seam ⑥：Host 读日志失败时先发 `stream/end`（reason=error, code=LOG_UNREADABLE）再关流；帧无 `id`、日志里没有该记录——`host.py` 与 `serve.py` 两端各一条黑盒判据
- [ ] 1.2 seam ⑥：会话删除时事件流先收 `stream/end`（reason=session_ended）再断开

## 2. 规格追认（无代码）

- [ ] 2.1 seam ⑥：snapshot 帧判据补「messages 是模型上下文、不含 tool/approval 历史」断言（实现已满足，判据钉住追认条款）
- [ ] 2.2 seam ⑥：`/log?path=` 等价路径不是合法路由（404）判据

## 3. 收尾四项

- [ ] 3.1 真实端点验收：起 Host 跑一场真实会话，SSE 客户端收帧序列正常、`stream/end` 不出现在 durable 重放里
- [ ] 3.2 UAT 验收（人跑）：场次手册 propose 时立骨架
- [ ] 3.3 变异测试一轮
- [ ] 3.4 Learning Gate
