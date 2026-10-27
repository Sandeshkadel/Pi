import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.server.schemas import (
    INCOMING_MESSAGE_ADAPTER,
    AudioChunk,
    Notification,
    VoiceControl,
)


def test_audio_chunk_accepts_valid_base64_pcm() -> None:
    message = INCOMING_MESSAGE_ADAPTER.validate_json(
        '{"type":"audio_chunk","sequence":4,"format":"pcm_s16le",'
        '"sample_rate":16000,"data":"AAE="}'
    )

    assert isinstance(message, AudioChunk)
    assert message.sequence == 4


def test_audio_chunk_rejects_invalid_base64() -> None:
    with pytest.raises(ValidationError):
        INCOMING_MESSAGE_ADAPTER.validate_json(
            '{"type":"audio_chunk","sequence":4,"format":"pcm_s16le",'
            '"sample_rate":16000,"data":"not-base64"}'
        )


def test_notification_requires_timezone_aware_timestamp() -> None:
    payload = {
        "type": "notification",
        "notification_id": str(uuid4()),
        "app": "WhatsApp",
        "package": "com.whatsapp",
        "title": "Sender",
        "text": "Hello",
        "timestamp": datetime.now(UTC).replace(tzinfo=None).isoformat(),
    }

    with pytest.raises(ValidationError):
        Notification.model_validate_json(json.dumps(payload))


def test_message_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        INCOMING_MESSAGE_ADAPTER.validate_json(
            '{"type":"command","text":"Open YouTube","source":"voice","extra":true}'
        )


@pytest.mark.parametrize("action", ["start", "stop"])
def test_voice_control_accepts_only_explicit_session_actions(action: str) -> None:
    message = INCOMING_MESSAGE_ADAPTER.validate_json(
        json.dumps({"type": "voice_control", "action": action})
    )

    assert isinstance(message, VoiceControl)
    assert message.action == action


def test_voice_control_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        INCOMING_MESSAGE_ADAPTER.validate_json(
            '{"type":"voice_control","action":"pause"}'
        )
