"""事件层：只追加的日志与折叠。"""

from mini_harness.events.record import SCHEMA_VERSION, EventRecord
from mini_harness.events.writer import EventLog

__all__ = ["EventLog", "EventRecord", "SCHEMA_VERSION"]
