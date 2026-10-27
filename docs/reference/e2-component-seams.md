# E2 组件接缝（Component Seams）——规划口径

**状态**：规划口径，**不是 spec**。E2 的 OpenSpec change 等 M 轨核心完成、E1 有基线之后再 propose；本文只回答「E2 是什么、为什么、到哪里为止」。

**一句话**：把核心能力抽成**可寻址、可版本化、可在会话之间替换**的组件；**不做 HMR、不做插件市场、不做多租户**。

---

## 1. 位置

```
M 轨核心（H1 → H2 → M10 → M11 → M12 → M13 → M14 → MEM1 → M15a）
        │
        ├── E1 评测与观测（并行，先有基线）
        │
        └── E2 组件接缝（M 核心之后、R3/G 之前）
                │
                ├── R1 经验记忆 / R2 技能库（可先用现有接口试，正式落地走 E2）
                ├── R3 模块级 harness 进化（E2 的直接消费者）
                └── G 轨 多用户/客服（E2 的 registry 可复用，但还要 plugin host/隔离/多租户）
```

E2 **不是**接 UI 壳的前置；它是**模块级 RSI 与服务化分支的前置**。壳要的是 H1/H2/M11/M14/MEM1/M15a。

---

## 2. 目标

1. **架构优化**：把 `turn_loop.py` / `cli/main.py` 里的策略从过程代码变成有接口的组件，降低单体耦合，让「改哪一块」可回答。
2. **生产迭代**：同一份内核，按会话选择不同组件版本；支持 A/B、灰度、回滚，不需要改核心代码。
3. **RSI 准备**：组件有 manifest、版本、editable surface、评估入口；R3 可以一次只变异一个组件，在 held-out 上比较，保留/回滚。
4. **可复现**：`session/start` 记录本次会话的组件清单（id/version/config hash）；同版本 replay 逐点相等，跨版本不静默通过。

---

## 3. 边界（明确不做）

- **不做 HMR**：不在运行中的会话里替换组件，不 watch 文件、不热更新代码。
- **不做插件市场**：不下载远程组件，不做依赖求解器，不做 semver range，不做签名/供应链。
- **不做多租户/多 worker**：单进程、单用户、可信本地组件；G 轨才做隔离、配额、鉴权、worker 池。
- **不做通用 DI 容器/事件总线**：组件之间只通过显式接口与 `SessionEnv` 组合；不加 `ctx.emit/waterfall` 那套。
- **不改内核语义**：日志格式、事件词表、停止理由、失败即结果、两轴围栏、CAS 都不变；唯一新增是 `session/start.payload.components`。
- **不重写 `turn_loop.py`**：保持显式回合循环；只把策略抽成对象，不把循环变成插件引擎。
- **不在 E2 做 RSI 实验**：E2 只提供「可替换 + 可评估 + 可回滚」的条件；R1–R4 是消费者。
- **E2 不是 M 的完成判据**：M 轨可以不带 E2 发布 personal-baseline；E2 是之后的架构/研究准备。

---

## 3.5 与 DSH 的关系

E2 **借的是 DSH 的组件/组合根语言**：manifest、registry、session-scoped composition、editable surface、版本与可复现。  
E2 **不借** Cordis 的服务图、fiber 生命周期、`isolate/intercept`、patch 层叠、HMR、plugin manager，也不追求 91 个服务键 / 81 个事件。  
另外：DSH 的 91 个服务键里**没有 `memory`**；它的记忆是 session/resume + `AGENTS.md` 类约定文件 + `compaction`。`MemoryStore` 是 mini/OpenClaw 方向的扩展，不是 DSH 模块的复刻。  
结论：E2 会让 mini 的架构语言更接近 DSH 的「组合」那一面，但仍然是 **component composition**，不是 **everything is a plugin**；这是 ADR-0035 的有意窄化。

## 4. 首批组件（只抽这些，不抽全部函数）

| 组件 | 现在住在哪 | 抽什么 | 消费者 |
|---|---|---|---|
| `Provider` | `provider/contract.py` | 已经是 Protocol；补 manifest/版本 | 所有入口 |
| `ApprovalGate` | `tools/fences.py` | 已经是 Protocol；补 manifest | H1/M12 |
| `ToolPolicy` | `tools/registry.py`、`dispatch.py`、M10 六段管线 | 工具定义、管线阶段、并发类别/barrier | M10/M12 |
| `ContextPolicy` | `events/fold.py` 的头部 + `context/budget.py` + `turn_loop` 的装配点 | 装配、预算、触发判定 | M11/R1 |
| `CompactionPolicy` | `turn_loop.py::_compact_if_over_line` | 摘要请求、遮蔽范围、`tokens_after` | M5/M11/R1 |
| `FailurePolicy` | `turn_loop.py` 的 provider/overflow/fence 分支 | 失败→结果词/停止理由 | M10/R3 |
| `MemoryStore` | MEM1 新增 | 读/写/加载/预算/边界 | MEM1/R1 |
| `SkillCatalog` + `CommandRegistry` | M14 新增 | 发现、清单、正文、`/skill` 命令 | M14/R2 |
| `SubagentPolicy` | M12 新增 | spawn、深度、并发上限、父子日志 | M12/R3 |
| `Verifier` | E1 新增 | held-in/held-out、隐藏测试、泄漏筛查、成本 | E1/R3/R4 |
| `CommandRunner` | M10 新增 | win32/posix/OS sandbox adapter | M10/M15a/b |

**不抽**：`EventLog.append`（单写者，已经是边界）、`fold`（纯函数，保持纯）、`SessionSettings`（配置对象，不是行为组件）、CLI 参数解析。

**`MemoryStore` 是 greenfield component，不是二次抽取**：MEM1 从第一天就按 `load / write / search(optional)` 的接口生出来，`turn_loop` 只通过 `SessionComponents.memory` 使用它，不直接碰文件路径。这样 R1（经验记忆）、R2（技能库）可以在不改内核的情况下换记忆策略；E2 的验收里包含「换一个 in-memory fake store，会话行为跟着变」。

---

## 5. 架构形状

### 5.1 manifest

```json
{
  "id": "context/default",
  "kind": "context",
  "api_version": 1,
  "version": "1.0.0",
  "entrypoint": "mini_harness.components.context_default:ContextDefault",
  "config_schema": {...},
  "dependencies": ["memory/default"],
  "editable_surfaces": ["header", "budget", "assembly"],
  "setup": "session",
  "teardown": "session"
}
```

### 5.2 registry 与组合

```text
ComponentRegistry.compose(settings, overrides, component_dirs)
    -> SessionComponents { provider, approval, tool, context, compaction,
                           failure, memory, skill, subagent, verifier, runner }
```

- 默认组件 = 当前行为；`overrides` 只覆盖指定 id；
- 组合发生在**会话开始**；运行中的会话不受后续替换影响；
- 组件目录只允许本地、可信：内置 < 用户 `$MINIHNS_HOME/components` < 工作区 `.minihns/components`；
- 依赖只做**显式声明 + 拓扑排序 + 缺失即启动失败**，不做版本求解。

### 5.3 记录与 replay

- `session/start.payload.components`: `[{id, version, config_hash}]`，不写路径、不写密钥。
- **同组件版本 + 同一日志前缀**：`replay` 逐点相等。
- **跨版本 replay**：不静默通过；要么走兼容模式，要么输出明确的 `COMPONENT_VERSION_MISMATCH`（spec 阶段定）。
- 组件版本/配置 hash 是 RSI 归因的一部分：没有它，无法知道「这次提升是哪个版本带来的」。

### 5.4 失败与隔离

- 组件在边界内抛异常：塌成 `COMPONENT_FAILED` 结果/错误，host 不崩；具体码在 spec 定。
- 组件只能访问 `SessionEnv` 给它的依赖；不允许 import 另一个组件的内部模块。
- 这是**进程内信任边界**，不是安全沙箱；安全隔离归 G/R4。

### 5.5 离线热插拔（不是 HMR）

- **会话级**：新会话选新组件，进程可以继续，运行中的会话不变；
- **进程级**：换组件目录/版本后重启 host 也可以；
- **不做**：运行中会话内替换、文件 watch、热更新代码。

---

## 6. 进入 / 退出条件

**进入**：

- H1/H2/M10/M11/M14/**M14a**/MEM1 完成；E1 有 held-out 基线；
- M12/M13/M14b/M14c 可选（`SubagentPolicy` 可后加；M14b/c 不阻塞 E2）；
- 不在 M10/M11/M14/MEM1 之前做：那些组件还不存在，提前抽只会抽空。

**退出（验收）**：

1. 默认组合与现行为一致；四道门禁全绿；日志只多 `session/start.payload.components`。
2. 测试里换一个 fake `ContextPolicy` / `CompactionPolicy`，**不改 `turn_loop.py`** 就能改变行为；默认判据不红。
3. `session/start` 记录组件清单；同版本 replay 逐点相等；跨版本有明确结果。
4. 同一进程可以先后用两套组件开会话；运行中的会话不受影响。
5. 组件抛异常不崩 host，塌成结果/错误。
6. E1 能对两套组件做 A/B，并给出归因报告（success/token/成本/失败类型）。
7. 没有 HMR、没有远程加载、没有多租户代码。

---

## 7. 与其它轨的关系

- **M 轨**：E2 不改变 M 的语义与发布判据；M 可以不带 E2 发 `personal-baseline-v1`。
- **E1**：E1 先有基线；E2 的 `Verifier` 是 E1 的组件化。
- **R1/R2**：可以先用现有接口做原型；正式落地走 E2 的 `MemoryStore` / `SkillCatalog`。
- **R3**：E2 是硬前置；没有组件清单与归因，模块级 RSI 无法判断收益来自哪。
- **R4**：E2 只提供 editable surface；沙箱、权限、账本、回滚是 R4 的事。
- **G 轨**：E2 的 registry 可复用；G 还要加多租户、worker 池、connector registry、隔离与运维，不在 E2。

---

## 8. 风险

- **过度抽象**：只抽 M10/M11/M14/MEM1 已经稳定下来的行为；不要为「将来可能」抽。
- **replay 漂移**：组件版本必须进 payload；跨版本必须显式，不许静默。
- **配置爆炸**：默认组件不暴露旋钮；先只有 `overrides`，等 E1 量到再加。
- **性能**：直接调用，不做事件总线；setup 只在会话开始。
- **安全**：本地可信组件，不是沙箱；远程/不可信组件留给 G/R4。
- **范围蔓延**：E2 不做 RSI 实验、不做插件市场、不做 HMR、不做多用户。

---

## 9. 后续

1. M 轨核心完成、E1 有基线后，propose `e2-component-seams`（proposal / specs / design / tasks）。
2. 新 ADR（编号从 0036 起）：**组件组合是会话级的，不是 HMR**。
3. 先落 `ContextPolicy` / `CompactionPolicy` / `FailurePolicy` 三个最痛的单体；`ToolPolicy` 跟 M10、`MemoryStore` 跟 MEM1（**greenfield，直接按组件接口生出来，不做二次抽取**）、`SkillCatalog` 跟 M14、`Verifier` 跟 E1。
4. 开放问题：组件目录布局、跨版本 replay 的兼容策略、组件失败的具体结果词、`SessionEnv` 是否改名 `SessionComponents`——都在 spec 阶段定。
