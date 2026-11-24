"""事件记录信封（日志里每一行的形状）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from mini_harness.events.vocabulary import CONCRETE_EVENT_TYPES, LEGACY_EVENT_TYPES, is_known_type

SCHEMA_VERSION = 2

# v1 → v2 的名字映射。`turn` 在两版里意思相反（v1 的 `turn` 是步，v2 的 `turn` 是轮），
# 所以必须整表查一次，不能做两遍字符串替换：`segment→turn` 的产物会被 `turn→step` 再改一次。
_V1_TYPE_MAP: dict[str, str] = {
    "segment/start": "turn/start",
    "segment/end": "turn/end",
    "turn/start": "step/start",
    "turn/end": "step/end",
}

# 载荷键同样整表换：`turn_id` 是轮的 id，`step_id` 是步的 id。
_V1_KEY_MAP: dict[str, str] = {
    "segment_id": "turn_id",
    "turn_id": "step_id",
    "turns": "steps",
    # `session/start` 的配置快照：键跟着设置字段一起改名。
    "max_turns": "max_steps",
}

# 封闭词表里的**值**也要换名：`stop_reason` 的 `MAX_TURNS` 在 v2 叫 `MAX_STEPS`。
# 只对点名过的键做值映射——载荷里还有模型输出的自然语言，不能全文替换。
_V1_VALUE_MAP: dict[str, dict[str, str]] = {
    "stop_reason": {"MAX_TURNS": "MAX_STEPS"},
}


class SchemaUnsupported(ValueError):
    """日志 schema_version 不是当前或相邻旧版：拒绝，不猜迁移。"""


class EventRecord(BaseModel):
    """日志里的一条事件记录。"""

    schema_version: int
    type: str
    session_id: str
    seq: int
    ts: str
    payload: dict[str, Any]

    @field_validator("type")
    @classmethod
    def _type_is_in_the_vocabulary(cls, value: str) -> str:
        """词表外的类型过不了校验：读回这样的行是日志层失败。"""
        if not is_known_type(value):
            raise ValueError(f"事件类型不在词表内：{value}")
        return value

    @model_validator(mode="after")
    def _legacy_names_belong_to_v1(self) -> EventRecord:
        """只属于 v1 的名字不能以 v2 的身份出现（`turn/start` 两版都有，不在禁列）。"""
        v1_only = LEGACY_EVENT_TYPES - CONCRETE_EVENT_TYPES
        if self.schema_version == SCHEMA_VERSION and self.type in v1_only:
            raise ValueError(f"schema v{SCHEMA_VERSION} 不能带 v1 事件名：{self.type}")
        return self


def _upcast_v1(record: EventRecord) -> EventRecord:
    """把一条 v1 记录整体翻译成 v2：换类型、换载荷键与封闭词表里的值，其余字段原样保留。

    纯函数，不写文件；`seq` / `ts` / `session_id` 与载荷里的自由文本都不动（design D2）。
    """
    payload: dict[str, Any] = {}
    for key, value in record.payload.items():
        new_key = _V1_KEY_MAP.get(key, key)
        values = _V1_VALUE_MAP.get(new_key)
        if values is not None and isinstance(value, str):
            value = values.get(value, value)
        payload[new_key] = value
    return record.model_copy(
        update={
            "schema_version": SCHEMA_VERSION,
            "type": _V1_TYPE_MAP.get(record.type, record.type),
            "payload": payload,
        }
    )


def migrate_schema(record: EventRecord) -> EventRecord:
    """当前版本原样返回；只接受 N-1 → N（v1 上迁到 v2），其余版本拒绝。"""
    if record.schema_version == SCHEMA_VERSION:
        return record
    if record.schema_version == SCHEMA_VERSION - 1:
        return _upcast_v1(record)
    raise SchemaUnsupported(
        f"不支持的 schema_version {record.schema_version}（当前 {SCHEMA_VERSION}）"
    )
