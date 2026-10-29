# Design

## Context

`context/budget.py` 现在把 `0.8`、`65536`、`16%` 写成常量；`SessionSettings` 只有 `window` / `reserve`；`session/start` payload 也只记录这两个窗口字段。配置层已有 `window` / `reserve` 的三层机制与类型校验，但 `SETTINGS_FIELDS` 是固定表。

本切片只做压缩参数的配置化；工具管线 / 并发 / spill 仍在后续 change。

## Goals / Non-Goals

**Goals:**

- 四个参数可配置，默认值让现有行为逐点不变。
- 有效值进 `session/start`；配置错误在 session 开始之前失败。
- `trigger_line` / `retain_line` 从常量函数变成参数函数；`shadowed_range` 使用有效 retain。
- 配置层仍是「内置默认 < 配置文件」；本切片不加 CLI flag，避免一次扩三处。

**Non-Goals:**

- 不加 `--compaction-*` flag；配置文件是这一片的入口。
- 不改 `window` / `reserve` 的校验与压力预算。
- 不做单条剪枝、spill、并发、`read` 字节上限。
- 不做动态改参数；参数在 session 开始时冻结。

## Decisions

**D1 四个字段直接放 `SessionSettings`，不引入 `CompactionPolicy` 对象。** 当前设置对象就是扁平 dataclass；四个字段与 `window` / `reserve` 同级，`session/start` payload 与 replay 读取都简单。等 M11/M14b 需要多组策略时再抽对象。

**D2 默认值：0.8 / 65536 / 0.16 / 0。** `compaction_retain_tokens = 0` 是「没有绝对保留量，用 ratio」；>0 时覆盖 ratio。`retain_tokens` 用绝对值，解决「固定留多少」不随窗口缩放的需求。

**D3 `trigger_line` / `retain_line` 改成关键字参数。** 形如 `trigger_line(window, reserve, *, threshold_ratio=0.8, headroom_tokens=65536)`；`retain_line(window, *, retain_ratio=0.16, retain_tokens=0)`。默认参数让旧调用点先不改也能跑；实际调用点从 `settings` 取值。

**D4 配置校验分两层。** `config/load.py` 只校验类型与未知键（ratio 是 float，tokens 是 int，bool 不算数字）；取值域（`0 < ratio <= 1`、`tokens >= 0`）在 `session/assembly.py` 的 session 前校验里做，和 `window` / `reserve` 同处，失败不建日志。

**D5 `session/start` 记录有效值；replay 不把它们当折叠输入。** 它们用于审计与未来 replay 的压缩判断，但当前 `replay` 只重算 `context/assembled`，不需要读这四个字段；旧日志缺字段不失败。

**D6 不加 CLI flag。** 用户明确要「改配置文件」；flag 会把同一参数扩到 parser、help、layering 与 host 请求体四处。等真的需要每 run 覆盖再加。

## Risks / Trade-offs

- **保留量太小导致没有可遮蔽段**：`retain_tokens` 太小或 ratio 太小时 `shadowed_range` 可能返回 `None`；这是合法结果（压缩救不了），不是配置错误。测试要覆盖边界。
- **`retain_tokens` 与 ratio 双写**：优先级固定在「tokens > 0 覆盖」，不合并；文档与 payload 都记录两者，避免读日志的人猜。
- **旧日志兼容**：旧记录没有四个字段；replay 不读取即不受影响。若未来 replay 需要判断压缩参数，必须先迁移/默认，不能直接 `payload["..."]`。
- **配置类型陷阱**：TOML 的 `0` / `1` 是 int；ratio 接受 int 还是只接受 float？决定：ratio 接受 int/float 并转 float（`1` 是合法边界），tokens 只接受 int。`bool` 在两层都拒绝。

## Migration Plan

1. 加字段与默认值；旧调用点仍可用默认参数。
2. 改调用点从 settings 取参数；测试默认行为逐点不变。
3. 加配置键、payload、校验；补配置黑盒。
4. 门禁、真实端点、UAT、变异、Learning Gate。

## Open Questions

- 无阻塞项。`retain_tokens` 的默认 0 与「ratio 生效」已定；不加 flag 是本切片明确边界。
