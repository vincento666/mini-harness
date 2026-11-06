"""委派的会话级账本：活跃子代理数与宿主登记回调（M12 design D3 / D7）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # 只给类型检查看：运行时导入会绕成 loop → tools.dispatch → fences → 本模块的环。
    from mini_harness.loop.turn_loop import SessionEnv

# DSH 的 `maxDepth` 默认 1：根会话（depth 0）能派子代理，子代理不能再派。
MAX_DEPTH = 1
# DSH 的 `maxActiveSubagents` 默认 8：每个父会话同时活着的子代理上限。
MAX_ACTIVE_SUBAGENTS = 8


@dataclass
class DelegationState:
    """一个会话的委派额度，外加「子会话收尾了」的宿主回调（根会话没有回调）。"""

    active: int = 0
    on_child_finished: Callable[[SessionEnv], None] | None = None
