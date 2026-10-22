"""事件层：只追加的日志与折叠。"""

from mini_harness.events.reader import LogReadFailure, LogTail, read_events
from mini_harness.events.record import SCHEMA_VERSION, EventRecord
from mini_harness.events.writer import EventLog, LogWriteFailure

__all__ = [
    "SCHEMA_VERSION",
    "EventLog",
    "EventRecord",
    "LogReadFailure",
    "LogTail",
    "LogWriteFailure",
    "read_events",
]
