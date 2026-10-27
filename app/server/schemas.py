"""Validated WebSocket message contracts."""

import base64
import binascii
from datetime import datetime
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

MAX_AUDIO_BYTES = 48_000
MAX_AUDIO_BASE64_LENGTH = 64_000


class StrictMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HealthResponse(StrictMessage):
    status: Literal["ok"]
    service: Literal["piagent"]


class AudioChunk(StrictMessage):
    type: Literal["audio_chunk"]
    sequence: int = Field(ge=0)
    format: Literal["pcm_s16le"]
    sample_rate: Literal[16_000]
    data: str = Field(min_length=4, max_length=MAX_AUDIO_BASE64_LENGTH)

    @field_validator("data")
    @classmethod
    def validate_audio_data(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Audio data must be valid base64.") from error
        if not decoded or len(decoded) > MAX_AUDIO_BYTES:
            raise ValueError(f"Decoded audio must be between 1 and {MAX_AUDIO_BYTES} bytes.")
        return value


class Notification(StrictMessage):
    type: Literal["notification"]
    notification_id: UUID
    app: str = Field(min_length=1, max_length=100)
    package: str = Field(min_length=1, max_length=255)
    title: str = Field(max_length=500)
    text: str = Field(max_length=4_000)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone.")
        return value


class Command(StrictMessage):
    type: Literal["command"]
    text: str = Field(min_length=1, max_length=1_000)
    source: Literal["voice", "app"]


class ActionResult(StrictMessage):
    type: Literal["action_result"]
    task_id: UUID
    success: bool
    details: str = Field(max_length=1_000)


class VoiceControl(StrictMessage):
    type: Literal["voice_control"]
    action: Literal["start", "stop"]


class Heartbeat(StrictMessage):
    type: Literal["heartbeat"]
    sequence: int = Field(ge=0)


IncomingMessage: TypeAlias = Annotated[
    AudioChunk | Notification | Command | ActionResult | VoiceControl | Heartbeat,
    Field(discriminator="type"),
]
INCOMING_MESSAGE_ADAPTER = TypeAdapter(IncomingMessage)
INCOMING_MESSAGE_TYPES = frozenset(
    {"audio_chunk", "notification", "command", "action_result", "voice_control", "heartbeat"}
)


class Listening(StrictMessage):
    type: Literal["listening"]


class Speak(StrictMessage):
    type: Literal["speak"]
    text: str = Field(min_length=1, max_length=2_000)
    interrupt: bool


class PermissionRequest(StrictMessage):
    type: Literal["permission_request"]
    task_id: UUID
    action: str = Field(min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=200)
    draft: str | None = Field(default=None, max_length=4_000)
    risk: Literal["low", "medium", "high"]


class AutomationTask(StrictMessage):
    type: Literal["automation_task"]
    task_id: UUID
    task: str = Field(min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=4_000)
    require_confirmation: bool


class HeartbeatAck(StrictMessage):
    type: Literal["heartbeat_ack"]
    sequence: int = Field(ge=0)


class MessageAccepted(StrictMessage):
    type: Literal["accepted"]
    message_type: Literal[
        "audio_chunk",
        "notification",
        "command",
        "action_result",
        "voice_control",
    ]


class ProtocolError(StrictMessage):
    type: Literal["error"]
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)


OutgoingMessage: TypeAlias = (
    Listening
    | Speak
    | PermissionRequest
    | AutomationTask
    | HeartbeatAck
    | MessageAccepted
    | ProtocolError
)
OUTGOING_MESSAGE_ADAPTER = TypeAdapter(OutgoingMessage)
