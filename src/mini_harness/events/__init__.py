"""事件层：只追加的日志与折叠。"""

from mini_harness.events.record import SCHEMA_VERSION, EventRecord
from mini_harness.events.reader import LogReadFailure, read_events
from mini_harness.events.writer import EventLog, LogWriteFailure

__all__ = [
    "EventLog",
    "EventRecord",
    "LogReadFailure",
    "LogWriteFailure",
    "SCHEMA_VERSION",
    "read_events",
]
