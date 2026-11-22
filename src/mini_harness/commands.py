"""命令面（M14）：人机直连的 UI 动作，不创建模型消息、不开启段。

命令的语法/未知名字是 admission miss——调用方不落任何日志；已知命令的参数错误是
handler 的结果（`ok=false`），照样落 `command/run` + `command/done`（照 DSH）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mini_harness.events.projection import project, render_todos
from mini_harness.events.record import EventRecord
from mini_harness.events.writer import LogWriteFailure
from mini_harness.goals import (
    GoalRefusal,
    GoalSnapshot,
    complete_goal,
    edit_goal,
    fold_goal,
    pause_goal,
    resume_goal,
)
from mini_harness.skills import Skill, read_skill_body

if TYPE_CHECKING:
    # 只给类型检查看：命令面只用到 log 与进程内武装位，不把整个回合循环拉进来。
    from mini_harness.loop.turn_loop import SessionEnv


@dataclass(frozen=True)
class CommandSpec:
    """一条命令的名字与一句描述；CLI 与 host 共用这份清单。"""

    name: str
    description: str


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("skills", "列出可用技能"),
    CommandSpec("skill", "加载一个技能的正文"),
    CommandSpec("plan", "进入计划模式；`/plan off` 退出"),
    CommandSpec("todo", "打印当前待办表"),
    CommandSpec(
        "goal",
        "查看目标；`/goal pause` / `resume` / `complete` / `clear`；`/goal edit <新正文>` 改目标",
    ),
)


RESERVED = frozenset(command.name for command in COMMANDS) | {"help"}


def command_catalog(skills: Sequence[Skill]) -> list[CommandSpec]:
    """内置命令 + 技能命令；内置名优先（技能同名时不覆盖，仍可用 `/skill <名字>`）。"""
    catalog = list(COMMANDS)
    seen = set(RESERVED)
    for skill in skills:
        if not skill.user_invocable or skill.name in seen:
            continue
        seen.add(skill.name)
        catalog.append(CommandSpec(skill.name, skill.description))
    return catalog


def direct_skill(name: str, skills: Sequence[Skill]) -> Skill | None:
    """`/<技能名>` 命中的用户可调技能；内置命令名优先，返回 None。"""
    if name in RESERVED:
        return None
    return next(
        (candidate for candidate in skills if candidate.name == name and candidate.user_invocable),
        None,
    )


def find_skill(name: str, skills: Sequence[Skill]) -> Skill | None:
    """按名字找技能（不分策略），供命令面区分「未知」与「不可由用户调用」。"""
    return next((candidate for candidate in skills if candidate.name == name), None)


@dataclass(frozen=True)
class CommandOutcome:
    """handler 的结果：成功与否 + 给 UI 的文本 + 可选的计划状态翻转。"""

    ok: bool
    text: str
    plan_active: bool | None = None


def _goal_command(
    arguments: str, records: Sequence[EventRecord], env: SessionEnv | None
) -> CommandOutcome:
    """`/goal` 命令面：查看、暂停、恢复、完成、清除、替换正文。

    会话内只做**无参数动词**；带参数的定义编辑归 CLI（`minihns goal <id> edit`）与
    `update_goal` 工具。`/goal <新正文>` 是最主流的形状（Codex `/goal "..."`、
    DSH `/goal <objective>`）：整段替换 objective，相位与武装位都不动。
    """
    goal = fold_goal(records)
    action = arguments.strip()
    armed = env is not None and env.goal_runtime.armed
    if action == "":
        if goal is None:
            return CommandOutcome(True, "没有当前目标")
        lines = [
            f"目标 {goal.id}（revision {goal.revision}）：{goal.objective}",
            f"相位 {goal.phase} · 轮次 {goal.rounds_started}/{goal.max_rounds} · "
            + ("已武装" if armed else "未武装"),
        ]
        if goal.blocked_reason is not None:
            lines.append(f"阻塞 {goal.blocked_reason.code}：{goal.blocked_reason.message}")
        return CommandOutcome(True, "\n".join(lines))

    verb, _, rest = action.partition(" ")
    verbs = {"pause", "resume", "complete", "clear", "edit"}
    if verb not in verbs:
        # 不是已知动词：整段当新正文。这是 `/goal 把测试修到全绿` 的路径。
        if goal is None:
            return CommandOutcome(False, "没有当前目标：无法改写。先用 create_goal 建一个")
        if env is None:
            return CommandOutcome(False, "这个入口没有会话运行期状态，/goal 不可用")
        return _replace_objective(goal, action, env)
    if verb == "edit":
        # `edit` 吃正文、不吃 flag：带参数的上限编辑归 CLI（C 方案）。
        if not rest.strip():
            return CommandOutcome(False, "用法：/goal edit <新正文>")
        if goal is None:
            return CommandOutcome(False, "没有当前目标：无法改写。先用 create_goal 建一个")
        if env is None:
            return CommandOutcome(False, "这个入口没有会话运行期状态，/goal 不可用")
        return _replace_objective(goal, rest.strip(), env)
    if rest.strip():
        # 其余动词不吃参数：`/goal pause 现在` 是打错了，不猜。
        return CommandOutcome(
            False,
            f"/goal {verb} 不接受参数；改正文用 `/goal edit <新正文>`",
        )
    if goal is None:
        return CommandOutcome(False, f"没有当前目标：无法执行 /goal {verb}")
    if env is None:
        return CommandOutcome(False, "这个入口没有会话运行期状态，/goal 不可用")

    if verb == "clear":
        # 清空是整值替换：`goal: null` 让 fold 回 None，也让旧引用失效。
        written = env.log.append("goal/updated", {"goal": None})
        if isinstance(written, LogWriteFailure):
            return CommandOutcome(False, "清除写不进日志，目标保持原样")
        env.goal_runtime.armed = False
        return CommandOutcome(True, "已清除当前目标")

    if verb == "resume" and goal.phase == "active" and armed:
        return CommandOutcome(True, "目标已经在自动推进（无需 resume）")

    result: GoalSnapshot | GoalRefusal
    if verb == "pause":
        result = pause_goal(goal)
    elif verb == "complete":
        result = complete_goal(goal)
    else:
        # 人的 resume 才放行 `paused`；工具面仍然拒绝（GOAL_RESUME_BY_TOOL_DENIED）。
        result = resume_goal(goal, armed=armed, human=True)
    if isinstance(result, GoalRefusal):
        return CommandOutcome(False, result.detail)
    written = env.log.append("goal/updated", {"goal": result.model_dump(exclude_none=True)})
    if isinstance(written, LogWriteFailure):
        return CommandOutcome(False, "改动写不进日志，本次操作作废")
    if verb == "pause":
        env.goal_runtime.armed = False
        return CommandOutcome(True, "已暂停目标")
    if verb == "complete":
        env.goal_runtime.armed = False
        return CommandOutcome(True, "已把目标标为完成")
    env.goal_runtime.armed = True
    return CommandOutcome(True, "已恢复目标：继续自动推进")


def _replace_objective(goal: GoalSnapshot, objective: str, env: SessionEnv) -> CommandOutcome:
    """`/goal <新正文>`：只换正文，`revision + 1`，相位与武装位不动。

    上限不在这里改：它是部署预算，归 CLI 的 `minihns goal <id> edit --max-rounds`
    或模型的 `update_goal edit`。会话内命令保持无参数，避免在提示符上做 flag 解析。
    """
    result = edit_goal(goal, objective=objective, max_rounds=None)
    if isinstance(result, GoalRefusal):
        return CommandOutcome(False, result.detail)
    written = env.log.append("goal/updated", {"goal": result.model_dump(exclude_none=True)})
    if isinstance(written, LogWriteFailure):
        return CommandOutcome(False, "改动写不进日志，本次操作作废")
    return CommandOutcome(
        True,
        f"已改写目标（revision {result.revision}）：{result.objective}",
    )


def execute_command(
    name: str,
    arguments: str,
    skills: Sequence[Skill],
    records: Sequence[EventRecord] = (),
    env: SessionEnv | None = None,
) -> CommandOutcome | None:
    """执行一条命令；未知命令返回 `None`（admission miss，不落日志）。

    `env` 只有 `/goal` 用：它要写 `goal/updated` 并翻转进程内的武装位。
    """
    if name == "goal":
        return _goal_command(arguments, records, env)
    if name == "skills":
        if arguments.strip():
            return CommandOutcome(False, "用法：/skills")
        lines = [
            f"- {skill.name}（rank {skill.rank}）：{skill.description}"
            for skill in skills
            if skill.user_invocable
        ]
        return CommandOutcome(True, "\n".join(lines) if lines else "（没有发现技能）")
    if name == "skill":
        target = arguments.strip()
        if not target:
            return CommandOutcome(False, "用法：/skill <name>")
        skill = find_skill(target, skills)
        if skill is None:
            return CommandOutcome(False, f"未知技能：{target}")
        if not skill.user_invocable:
            return CommandOutcome(False, f"技能 {target} 不可由用户调用")
        return CommandOutcome(True, read_skill_body(skill))
    if name == "plan":
        target = arguments.strip()
        if target == "off":
            return CommandOutcome(True, "已退出计划模式", plan_active=False)
        if target:
            return CommandOutcome(False, "用法：/plan 或 /plan off")
        return CommandOutcome(True, "已进入计划模式：批准计划前，写类工具不可用", plan_active=True)
    if name == "todo":
        if arguments.strip():
            return CommandOutcome(False, "用法：/todo")
        items = project(records, "todos")["value"]
        lines = render_todos(items)
        return CommandOutcome(True, "\n".join(lines) if lines else "（没有待办）")
    # 直接技能名由壳走「注入 + 开段」的执行路径；这里只处理内置命令。
    return None
