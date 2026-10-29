# Proposal

## Why

M10 的第一切片是「压缩参数可配置」。当前触发线、headroom 与保留尾部都写死在 `context/budget.py`：`0.8`、`65536`、`16%`；用户只能通过改 `window` / `reserve` 间接影响它们。DSH 的 `dsh-compaction-basic` 暴露 `thresholdRatio`、`headroomTokens`、`retainRatio`、`retainTokens`，mini 只抄了默认值，没抄配置面。

先做这一片，因为它独立、判据清晰，且是后续 M10 工具管线 / 上下文经济的底座；工具并发、spill、`read` 字节上限不在本 change。

## What Changes

- 配置新增四个键（`mini.config.toml`；本切片不加 CLI flag）：
  - `compaction_threshold_ratio`：默认 `0.8`，`0 < x <= 1`
  - `compaction_headroom_tokens`：默认 `65536`，`>= 0`
  - `compaction_retain_ratio`：默认 `0.16`，`0 < x <= 1`
  - `compaction_retain_tokens`：默认 `0`（0 表示用 ratio；>0 时它优先），`>= 0`
- `context/budget.py` 的 `trigger_line` / `retain_line` 从常量改为参数；默认值逐点保持现有行为。
- `SessionSettings` 带这四个有效值；`session/start.payload` 记录它们，供审计与 replay 取回。
- 配置校验：类型（float/int，`bool` 不算 int）、范围、`window - reserve > 0` 仍单独判；非法配置在 session 开始前退出码 2，不建日志。
- **不做**：工具管线 / 并发 / spill / `read` 字节上限（M10 余下）、CLI flag、每工具可配、动态改参数。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `context-budget`：触发线从固定 `0.8`/`65536` 改为可配；保留尾部从固定 `16%` 改为可配 ratio/tokens；默认行为不变。
- `config-layering`：配置文件允许四个 `compaction_*` 键，并校验范围。
- `cli`：`session/start.payload` 记录四个有效字段。

## Impact

- 代码：`context/budget.py`、`loop/settings.py`、`config/load.py`、`session/assembly.py`、`cli/main.py`（装配参数）、`loop/turn_loop.py`（调用参数）、测试。
- 规格：三个 delta；无新依赖。
- 兼容：默认值下行为逐点不变；旧日志没有四个字段时 replay 不因缺字段失败（不读取它们做折叠）。
- 顺序：M10 第一切片；完成后另立 `m10-tool-pipeline-and-concurrency` 做余下。
