#!/usr/bin/env python3
"""repowiki 目录定义：mini-harness 的页面树（与 repowiki 参考仓库同构）。

结构约定（照参考仓库）：
  zh/content/<页面>.html                       根级页面
  zh/content/<目录>/<目录>.html                目录的同名枢纽页
  zh/content/<目录>/<子页面>.html              二级页面
  zh/content/<目录>/<子目录>/<子目录>.html      三级目录的枢纽页
  zh/meta/repowiki-metadata.json               生成台账与引用图

本模块只描述目录与引用关系；正文在 repowiki/src/pages/<slug>.html。
"""

from __future__ import annotations

from typing import Any

# slug, 名称, 父 slug（"" = 根）, 层级, 依赖文件, 生成提示, 图表 id, 组内顺序
CATALOG: list[dict[str, Any]] = [
    # -------------------------------------------------- 根级页面
    {
        "slug": "项目概述",
        "name": "项目概述",
        "parent": "",
        "level": 1,
        "order": 1,
        "files": ["AGENTS.md", "src/mini_harness/__init__.py", "pyproject.toml", "docs/CURRENT.md"],
        "diagrams": ["m1-01-system-context", "m1-12-use-case"],
        "prompt": "说明 mini-harness 是什么、为谁而建、M1 交付了什么能力边界，以及它与被剖析的参考 harness 的关系。列出六个测试接缝与六条运行时不变量的名称，并给出读者按什么顺序读这套文档。",
    },
    {
        "slug": "快速开始",
        "name": "快速开始",
        "parent": "",
        "level": 1,
        "order": 2,
        "files": ["AGENTS.md", "src/mini_harness/cli/main.py", "pyproject.toml", "tests/fixtures"],
        "diagrams": ["m1-05-lifecycle", "m1-21-exit-code"],
        "prompt": "给出从零跑通一次 minihns run 与 minihns replay 的完整步骤：安装、准备剧本 fixture、会话目录位置、退出码含义、常见失败与对应处置。所有命令给出可直接复制的形式。",
    },
    {
        "slug": "规格驱动流程",
        "name": "规格驱动流程",
        "parent": "",
        "level": 1,
        "order": 3,
        "files": ["openspec/config.yaml", "openspec/specs", "openspec/changes", "AGENTS.md"],
        "diagrams": ["m1-26-change-lifecycle", "m1-27-gate-pipeline"],
        "prompt": "解释一个里程碑如何作为一个 OpenSpec change 走完 propose、apply、verify、sync-specs、archive、merge 的闭环，以及收尾门禁流水线的固定顺序与每道门的判据。",
    },
    {
        "slug": "开发工具和脚本",
        "name": "开发工具和脚本",
        "parent": "",
        "level": 1,
        "order": 4,
        "files": [
            "docs/tools/inventory.py",
            "docs/tools/build_diagrams.py",
            "docs/tools/diagram_defs.py",
            "docs/tools/uml_svg.py",
            "docs/tools/diag_probe.py",
            "docs/tools/build_wiki.py",
        ],
        "diagrams": ["m1-30-repo-layout"],
        "prompt": "说明仓库内自研工具的职责与用法：代码清单生成、图表生成、图表排错探针、wiki 构建，以及它们与 repowiki 资产目录的关系。",
    },
    {
        "slug": "路线图与决策记录",
        "name": "路线图与决策记录",
        "parent": "",
        "level": 1,
        "order": 5,
        "files": [
            "docs/roadmap.md",
            "docs/adr/0001-m1-simplifications.md",
            "docs/adr/0002-deferred-refactors.md",
            "docs/lessons.md",
        ],
        "diagrams": ["m1-32-roadmap", "m1-29-timeline", "m1-31-lessons-loop"],
        "prompt": "汇总 M1 到 M7 的里程碑与完成判据、两份 ADR 记录的简化决定与待还欠账、教训索引的编号与主题，并说明里程碑推进顺序的理由。",
    },
    {
        "slug": "术语表",
        "name": "术语表",
        "parent": "",
        "level": 1,
        "order": 6,
        "files": [
            "src/mini_harness/events/vocabulary.py",
            "src/mini_harness/loop/turn_loop.py",
            "openspec/config.yaml",
        ],
        "diagrams": ["m1-16-event-vocabulary", "m1-13-turn-loop-steps", "m1-21-exit-code"],
        "prompt": "给出项目内部术语的规范定义：事件词表、停止原因、接缝、围栏两轴、受保护头部、指纹、投影、门禁、复利门，每个术语给出代码出处。",
    },
    # -------------------------------------------------- 系统架构设计
    {
        "slug": "系统架构设计",
        "name": "系统架构设计",
        "parent": "",
        "level": 1,
        "order": 7,
        "files": ["AGENTS.md", "src/mini_harness"],
        "diagrams": ["m1-02-container-view", "m1-03-layered"],
        "prompt": "作为本目录的枢纽页，给出架构总览、四个视图（系统上下文、容器、分层、包依赖）的读法，以及本目录各子页的分工。",
    },
    {
        "slug": "架构总览与决策",
        "name": "架构总览与决策",
        "parent": "系统架构设计",
        "level": 2,
        "order": 1,
        "files": ["AGENTS.md", "docs/adr/0001-m1-simplifications.md", "openspec/config.yaml"],
        "diagrams": ["m1-01-system-context", "m1-10-component-contract"],
        "prompt": "描述系统上下文：使用者、CLI、内核、日志、模型提供方、工作区之间的边界与契约，以及六条不变量如何约束这些边界。",
    },
    {
        "slug": "分层与依赖关系",
        "name": "分层与依赖关系",
        "parent": "系统架构设计",
        "level": 2,
        "order": 2,
        "files": [
            "src/mini_harness/cli/main.py",
            "src/mini_harness/loop/turn_loop.py",
            "src/mini_harness/events",
            "src/mini_harness/provider",
            "src/mini_harness/tools",
        ],
        "diagrams": ["m1-03-layered", "m1-04-package-deps"],
        "prompt": "逐层说明 CLI 层、内核层、日志层、Provider 层、工具层的职责与真实 import 方向，指出唯一的反向依赖及其记录位置。",
    },
    {
        "slug": "系统生命周期与流程",
        "name": "系统生命周期与流程",
        "parent": "系统架构设计",
        "level": 2,
        "order": 3,
        "files": [
            "src/mini_harness/cli/main.py",
            "src/mini_harness/loop/turn_loop.py",
            "docs/roadmap.md",
        ],
        "diagrams": ["m1-05-lifecycle", "m1-11-process-files"],
        "prompt": "描述从进程启动到退出的完整生命周期，以及会话、回合、事件三个层次的时间流程；区分已实现流程与计划流程。",
    },
    {
        "slug": "组件与接口装配",
        "name": "组件与接口装配",
        "parent": "系统架构设计",
        "level": 2,
        "order": 4,
        "files": [
            "src/mini_harness/provider/contract.py",
            "src/mini_harness/tools/registry.py",
            "src/mini_harness/loop/turn_loop.py",
        ],
        "diagrams": ["m1-10-component-contract", "m1-09b-class-contracts"],
        "prompt": "用提供接口与需求接口描述组件装配关系，说明为什么 CLI 只依赖协议而不依赖具体实现，以及替换实现需要满足哪些契约。",
    },
    # -------------------------------------------------- 核心运行时
    {
        "slug": "核心运行时",
        "name": "核心运行时",
        "parent": "",
        "level": 1,
        "order": 8,
        "files": ["src/mini_harness/loop/turn_loop.py", "src/mini_harness/events"],
        "diagrams": ["m1-13-turn-loop-steps", "m1-23-dataflow"],
        "prompt": "作为本目录的枢纽页，给出运行时的核心事实：日志是唯一事实、回合循环五步、装配由折叠产生，并指引到子页。",
    },
    {
        "slug": "事件日志追加与折叠",
        "name": "事件日志追加与折叠",
        "parent": "核心运行时",
        "level": 2,
        "order": 1,
        "files": [
            "src/mini_harness/events/record.py",
            "src/mini_harness/events/writer.py",
            "src/mini_harness/events/reader.py",
            "src/mini_harness/events/fold.py",
        ],
        "diagrams": ["m1-14-append-fold", "m1-23-dataflow"],
        "prompt": "说明追加写的顺序与序号规则、写失败的返回形式、读取的失败形式，以及折叠如何从事件产生受保护头部与正文消息。",
    },
    {
        "slug": "确定性与回放",
        "name": "确定性与回放",
        "parent": "核心运行时",
        "level": 2,
        "order": 2,
        "files": [
            "src/mini_harness/events/fold.py",
            "src/mini_harness/cli/main.py",
            "tests/test_cli_replay.py",
        ],
        "diagrams": ["m1-15-determinism", "m1-20-seq-replay"],
        "prompt": "解释回放与实时装配为什么必然一致：同一折叠函数、同一头部指纹算法、同一事件顺序；给出验证这一点的测试与判据。",
    },
    {
        "slug": "取消与信号处理",
        "name": "取消与信号处理",
        "parent": "核心运行时",
        "level": 2,
        "order": 3,
        "files": [
            "src/mini_harness/cli/main.py",
            "src/mini_harness/loop/turn_loop.py",
            "tests/test_cli_run.py",
        ],
        "diagrams": ["m1-19-seq-cancel", "m1-07-state-session"],
        "prompt": "说明 SIGINT 的处理路径、取消标志在哪个边界被检查、取消写哪些事件、退出码 5 的由来，以及当前测试覆盖的局限。",
    },
    {
        "slug": "回合循环内核",
        "name": "回合循环内核",
        "parent": "核心运行时",
        "level": 2,
        "order": 4,
        "files": ["src/mini_harness/loop/turn_loop.py"],
        "diagrams": ["m1-13-turn-loop-steps", "m1-06-seq-run"],
        "prompt": "作为三级目录的枢纽页，给出 run_session 的输入输出契约、内核失败与运行失败的区别，以及本目录两页的分工。",
    },
    {
        "slug": "五步回合循环",
        "name": "五步回合循环",
        "parent": "回合循环内核",
        "level": 3,
        "order": 1,
        "files": [
            "src/mini_harness/loop/turn_loop.py",
            "src/mini_harness/events/fold.py",
            "src/mini_harness/tools/dispatch.py",
        ],
        "diagrams": ["m1-13-turn-loop-steps", "m1-16-event-vocabulary"],
        "prompt": "按记账、装配上下文、调模型、派发工具、判定停止五步逐一说明每一步写的事件与失败处理。",
    },
    {
        "slug": "停止判定与退出码映射",
        "name": "停止判定与退出码映射",
        "parent": "回合循环内核",
        "level": 3,
        "order": 2,
        "files": ["src/mini_harness/loop/turn_loop.py", "src/mini_harness/cli/main.py"],
        "diagrams": ["m1-21-exit-code", "m1-07-state-session"],
        "prompt": "列出五种停止原因、它们到退出码的映射表、词表外原因的兜底行为，以及保留但不可达的退出码。",
    },
    # -------------------------------------------------- 工具与能力契约
    {
        "slug": "工具与能力契约",
        "name": "工具与能力契约",
        "parent": "",
        "level": 1,
        "order": 9,
        "files": ["src/mini_harness/tools/registry.py", "src/mini_harness/tools/dispatch.py"],
        "diagrams": ["m1-18-tool-dispatch", "m1-24-fence-matrix"],
        "prompt": "作为本目录的枢纽页，说明工具作为能力契约的含义：登记、查询、派发三段，以及失败作为结果的表达方式。",
    },
    {
        "slug": "工具注册与派发",
        "name": "工具注册与派发",
        "parent": "工具与能力契约",
        "level": 2,
        "order": 1,
        "files": [
            "src/mini_harness/tools/registry.py",
            "src/mini_harness/tools/dispatch.py",
            "tests/test_tool_dispatch.py",
        ],
        "diagrams": ["m1-18-tool-dispatch", "m1-06-seq-run"],
        "prompt": "说明 ToolDefinition、ToolRegistry、dispatch_tool_call、ToolResult 的现状与 M1 的边界：只有定义与派发骨架，没有真实文件工具。",
    },
    {
        "slug": "围栏与工作区边界",
        "name": "围栏与工作区边界",
        "parent": "工具与能力契约",
        "level": 2,
        "order": 2,
        "files": ["AGENTS.md", "docs/roadmap.md", "openspec/config.yaml"],
        "diagrams": ["m1-24-fence-matrix"],
        "prompt": "解释围栏两轴的独立性：工作区边界与写前必读，以及审批轴与边界轴互不解锁；明确 M1 未实现、M2 的完成判据。",
    },
    {
        "slug": "并发与超时计划",
        "name": "并发与超时计划",
        "parent": "工具与能力契约",
        "level": 2,
        "order": 3,
        "files": ["docs/roadmap.md", "AGENTS.md"],
        "diagrams": ["m1-32-roadmap"],
        "prompt": "说明只读工具并发上限、写与命令串行、超时与取消事件的计划口径，并明确这些是设计决策而非当前实现。",
    },
    # -------------------------------------------------- Provider 抽象
    {
        "slug": "Provider抽象",
        "name": "Provider 抽象",
        "parent": "",
        "level": 1,
        "order": 10,
        "files": ["src/mini_harness/provider/contract.py", "src/mini_harness/provider/mock.py"],
        "diagrams": ["m1-22-provider-contract", "m1-09b-class-contracts"],
        "prompt": "作为本目录的枢纽页，说明 Provider 接缝的作用、一个方法的两种返回，以及 mock 与真实提供方共用同一接口的设计意图。",
    },
    {
        "slug": "Provider协议",
        "name": "Provider 协议",
        "parent": "Provider抽象",
        "level": 2,
        "order": 1,
        "files": ["src/mini_harness/provider/contract.py"],
        "diagrams": ["m1-22-provider-contract", "m1-09b-class-contracts"],
        "prompt": "逐字段说明 AssistantTurn、ToolCall、ToolSpec、Usage、ProviderFailure 与 Provider 协议签名，并说明协议被内核使用的位置。",
    },
    {
        "slug": "FixtureProvider与测试剧本",
        "name": "FixtureProvider 与测试剧本",
        "parent": "Provider抽象",
        "level": 2,
        "order": 2,
        "files": [
            "src/mini_harness/provider/mock.py",
            "tests/test_provider_mock.py",
            "tests/fixtures",
        ],
        "diagrams": ["m1-22-provider-contract"],
        "prompt": "说明剧本文件的结构、加载失败的形式、逐条消费的行为，以及测试如何用剧本注入成功与失败两种路径。",
    },
    {
        "slug": "真实Provider接入计划",
        "name": "真实 Provider 接入计划",
        "parent": "Provider抽象",
        "level": 2,
        "order": 3,
        "files": ["docs/roadmap.md", "docs/adr/0001-m1-simplifications.md"],
        "diagrams": ["m1-32-roadmap", "m1-34-budget-formula"],
        "prompt": "说明 M4 接真实 OpenAI 兼容提供方的计划：并行工具调用、限流与重试一次的口径，以及窗口预算为什么留到 M5。",
    },
    # -------------------------------------------------- CLI 命令
    {
        "slug": "CLI命令",
        "name": "CLI 命令",
        "parent": "",
        "level": 1,
        "order": 11,
        "files": ["src/mini_harness/cli/main.py"],
        "diagrams": ["m1-21-exit-code", "m1-02-container-view"],
        "prompt": "作为本目录的枢纽页，给出命令面全貌：子命令、参数、默认值、输出流约定，以及 CLI 作为黑盒接缝的意义。",
    },
    {
        "slug": "run命令",
        "name": "run 命令",
        "parent": "CLI命令",
        "level": 2,
        "order": 1,
        "files": [
            "src/mini_harness/cli/main.py",
            "src/mini_harness/loop/turn_loop.py",
            "tests/test_cli_run.py",
        ],
        "diagrams": ["m1-06-seq-run", "m1-21-exit-code"],
        "prompt": "逐项说明 run 的参数与默认值、会话目录的创建、异步等待与信号注册的顺序、失败如何写到 stderr。",
    },
    {
        "slug": "replay命令",
        "name": "replay 命令",
        "parent": "CLI命令",
        "level": 2,
        "order": 2,
        "files": [
            "src/mini_harness/cli/main.py",
            "src/mini_harness/events/reader.py",
            "tests/test_cli_replay.py",
        ],
        "diagrams": ["m1-20-seq-replay"],
        "prompt": "说明 replay 的输入、输出格式、工具描述当前如何得到、与实时装配的一致性判据，以及已知缺口。",
    },
    {
        "slug": "参数解析与退出码",
        "name": "参数解析与退出码",
        "parent": "CLI命令",
        "level": 2,
        "order": 3,
        "files": ["src/mini_harness/cli/main.py"],
        "diagrams": ["m1-21-exit-code", "m1-05-lifecycle"],
        "prompt": "说明参数错误的统一处理形式、非法值如何被拒、退出码常量与映射函数，以及词表外原因的兜底策略。",
    },
    # -------------------------------------------------- 事件与数据模型
    {
        "slug": "事件与数据模型",
        "name": "事件与数据模型",
        "parent": "",
        "level": 1,
        "order": 12,
        "files": [
            "src/mini_harness/events/record.py",
            "src/mini_harness/events/vocabulary.py",
            "src/mini_harness/events/fold.py",
        ],
        "diagrams": ["m1-16-event-vocabulary", "m1-08-er-log"],
        "prompt": "作为本目录的枢纽页，说明持久对象只有一种、其余都是投影这一核心事实，并给出三页分工。",
    },
    {
        "slug": "事件词表与模式版本",
        "name": "事件词表与模式版本",
        "parent": "事件与数据模型",
        "level": 2,
        "order": 1,
        "files": [
            "src/mini_harness/events/vocabulary.py",
            "src/mini_harness/events/record.py",
            "src/mini_harness/events/writer.py",
        ],
        "diagrams": ["m1-16-event-vocabulary", "m1-14-append-fold"],
        "prompt": "列出九种具体事件类型与错误命名空间、模式版本常量、未知类型的判定方式，以及词表在写入路径上的强制位置。",
    },
    {
        "slug": "核心类图与契约",
        "name": "核心类图与契约",
        "parent": "事件与数据模型",
        "level": 2,
        "order": 2,
        "files": [
            "src/mini_harness/events/record.py",
            "src/mini_harness/events/fold.py",
            "src/mini_harness/events/writer.py",
            "src/mini_harness/provider/contract.py",
        ],
        "diagrams": ["m1-09-class-core", "m1-09b-class-contracts"],
        "prompt": "按类图逐类说明字段与方法、组合与依赖关系，并给出每个类的源码行区间。",
    },
    {
        "slug": "实体关系与投影模型",
        "name": "实体关系与投影模型",
        "parent": "事件与数据模型",
        "level": 2,
        "order": 3,
        "files": ["src/mini_harness/events/fold.py", "src/mini_harness/events/record.py"],
        "diagrams": ["m1-08-er-log", "m1-34-budget-formula"],
        "prompt": "用实体关系解释会话与事件的一对多、事件到上下文的折叠、上下文到消息的一对多，并说明投影不落盘的原因与代价。",
    },
    # -------------------------------------------------- 测试与质量门禁
    {
        "slug": "测试与质量门禁",
        "name": "测试与质量门禁",
        "parent": "",
        "level": 1,
        "order": 13,
        "files": ["tests", "AGENTS.md", "pyproject.toml"],
        "diagrams": ["m1-25-seam-map", "m1-33-coverage"],
        "prompt": "作为本目录的枢纽页，说明六个测试接缝、62 个测试的分布、覆盖率底线与门禁顺序，并给出子页分工。",
    },
    {
        "slug": "测试接缝与测试清单",
        "name": "测试接缝与测试清单",
        "parent": "测试与质量门禁",
        "level": 2,
        "order": 1,
        "files": [
            "tests/test_turn_loop.py",
            "tests/test_cli_run.py",
            "tests/test_cli_replay.py",
            "tests/test_context_fold.py",
            "tests/test_event_log_append.py",
            "tests/test_provider_mock.py",
            "tests/test_tool_dispatch.py",
            "tests/test_integration.py",
            "tests/cli_blackbox.py",
            "tests/paths.py",
        ],
        "diagrams": ["m1-25-seam-map"],
        "prompt": "逐接缝列出测试文件、行数、覆盖的行为，以及黑盒测试如何起真进程、路径常量如何集中管理。",
    },
    {
        "slug": "覆盖率与门禁流水线",
        "name": "覆盖率与门禁流水线",
        "parent": "测试与质量门禁",
        "level": 2,
        "order": 2,
        "files": ["pyproject.toml", "AGENTS.md", "docs/lessons.md"],
        "diagrams": ["m1-33-coverage", "m1-27-gate-pipeline"],
        "prompt": "给出逐模块覆盖率数字与未覆盖行、门禁命令的固定顺序与每条命令的干净输出长什么样，以及覆盖率纪律。",
    },
    {
        "slug": "变异测试记录",
        "name": "变异测试记录",
        "parent": "测试与质量门禁",
        "level": 2,
        "order": 3,
        "files": ["docs/verification/m1-mutation.md", "src/mini_harness/cli/main.py"],
        "diagrams": ["m1-28-mutation"],
        "prompt": "说明变异测试的做法与判据、M1 的 17 个变异结果、存活变异换回的设计改进，以及无效变体的剔除规则。",
    },
]


def by_slug() -> dict[str, dict[str, Any]]:
    return {item["slug"]: item for item in CATALOG}


def children_of(slug: str) -> list[dict[str, Any]]:
    return [item for item in CATALOG if item["parent"] == slug]


def is_dir(item: dict[str, Any]) -> bool:
    """有子页面的条目是目录，其同名枢纽页放在目录内部。"""
    return bool(children_of(item["slug"]))


def chain_of(item: dict[str, Any]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    cursor: dict[str, Any] | None = item
    while cursor is not None:
        chain.append(cursor)
        cursor = by_slug()[cursor["parent"]] if cursor["parent"] else None
    chain.reverse()
    return chain


def path_of(item: dict[str, Any]) -> str:
    parts = [entry["name"] for entry in chain_of(item)]
    if is_dir(item):
        parts.append(item["name"])
    return "/".join(parts) + ".html"
