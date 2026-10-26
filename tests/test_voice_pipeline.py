import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_token
from app.core.state import AgentState
from app.main import create_app
from app.server.schemas import AudioChunk
from app.server.websocket import MessageHandlerFactory
from app.voice.pipeline import (
    AudioBufferOverflow,
    PCMBuffer,
    VoiceBackendError,
    VoicePipeline,
    VoicePipelineBusyError,
    VoiceSettings,
)
from app.voice.websocket import create_voice_message_handler_factory

SPEECH_FRAME = b"\x01\x00" * 640
SILENCE_FRAME = b"\x00\x00" * 640


def _chunk(sequence: int, pcm: bytes) -> AudioChunk:
    return AudioChunk(
        type="audio_chunk",
        sequence=sequence,
        format="pcm_s16le",
        sample_rate=16_000,
        data=base64.b64encode(pcm).decode("ascii"),
    )


class FakeWakeWordDetector:
    async def detected(self, pcm_s16le: bytes) -> bool:
        return pcm_s16le == b"\x02\x00"


class FakeVad:
    async def is_speech(self, pcm_s16le: bytes) -> bool:
        return pcm_s16le.startswith(b"\x01\x00")


class FakeRecognizer:
    def __init__(self, transcript: str = "set a timer", error: Exception | None = None) -> None:
        self.transcript = transcript
        self.error = error
        self.audio: bytes | None = None

    async def transcribe(self, pcm_s16le: bytes) -> str:
        self.audio = pcm_s16le
        if self.error is not None:
            raise self.error
        return self.transcript


class SlowRecognizer:
    async def transcribe(self, pcm_s16le: bytes) -> str:
        await asyncio.sleep(1)
        return "this should time out"


class FakeSpeechOutput:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def speak(self, text: str) -> None:
        self.messages.append(text)


def _pipeline(
    recognizer: FakeRecognizer | None = None,
    settings: VoiceSettings | None = None,
) -> tuple[VoicePipeline, FakeRecognizer, FakeSpeechOutput]:
    speech_recognizer = recognizer or FakeRecognizer()
    speech_output = FakeSpeechOutput()
    pipeline = VoicePipeline(
        wake_word_detector=FakeWakeWordDetector(),
        vad=FakeVad(),
        recognizer=speech_recognizer,
        speech_output=speech_output,
        settings=settings or VoiceSettings(silence_timeout_ms=80),
    )
    return pipeline, speech_recognizer, speech_output


@pytest.mark.asyncio
async def test_wake_word_starts_listening_without_retaining_wake_audio() -> None:
    pipeline, recognizer, speech = _pipeline()

    update = await pipeline.process_chunk(_chunk(0, b"\x02\x00"))

    assert update.listening_started is True
    assert update.state is AgentState.LISTENING
    assert update.speech == "Listening."
    assert speech.messages == ["Listening."]
    assert recognizer.audio is None


@pytest.mark.asyncio
async def test_silence_ends_utterance_and_transcribes_only_speech() -> None:
    pipeline, recognizer, _ = _pipeline()
    await pipeline.process_chunk(_chunk(0, b"\x02\x00"))
    await pipeline.process_chunk(_chunk(1, SPEECH_FRAME))

    partial = await pipeline.process_chunk(_chunk(2, SILENCE_FRAME))
    complete = await pipeline.process_chunk(_chunk(3, SILENCE_FRAME))

    assert partial.state is AgentState.LISTENING
    assert complete.state is AgentState.THINKING
    assert complete.transcript == "set a timer"
    assert recognizer.audio == SPEECH_FRAME


@pytest.mark.asyncio
async def test_empty_transcription_prompts_and_returns_to_idle() -> None:
    pipeline, _, speech = _pipeline(FakeRecognizer(transcript="  "))
    await pipeline.process_chunk(_chunk(0, b"\x02\x00"))
    await pipeline.process_chunk(_chunk(1, SPEECH_FRAME))
    await pipeline.process_chunk(_chunk(2, SILENCE_FRAME))

    update = await pipeline.process_chunk(_chunk(3, SILENCE_FRAME))

    assert update.state is AgentState.IDLE
    assert update.speech == "I didn't catch that. Please try again."
    assert speech.messages[-1] == update.speech


@pytest.mark.asyncio
async def test_backend_failure_enters_error_state_and_can_reset() -> None:
    pipeline, _, _ = _pipeline(FakeRecognizer(error=VoiceBackendError("model unavailable")))
    await pipeline.process_chunk(_chunk(0, b"\x02\x00"))
    await pipeline.process_chunk(_chunk(1, SPEECH_FRAME))
    await pipeline.process_chunk(_chunk(2, SILENCE_FRAME))

    with pytest.raises(VoiceBackendError, match="model unavailable"):
        await pipeline.process_chunk(_chunk(3, SILENCE_FRAME))

    assert pipeline.state is AgentState.ERROR
    assert (await pipeline.reset()).state is AgentState.IDLE


@pytest.mark.asyncio
async def test_transcription_timeout_enters_error_state() -> None:
    pipeline = VoicePipeline(
        wake_word_detector=FakeWakeWordDetector(),
        vad=FakeVad(),
        recognizer=SlowRecognizer(),
        settings=VoiceSettings(
            silence_timeout_ms=80,
            transcription_timeout_seconds=0.01,
        ),
    )
    await pipeline.process_chunk(_chunk(0, b"\x02\x00"))
    await pipeline.process_chunk(_chunk(1, SPEECH_FRAME))
    await pipeline.process_chunk(_chunk(2, SILENCE_FRAME))

    with pytest.raises(VoiceBackendError, match="timed out"):
        await pipeline.process_chunk(_chunk(3, SILENCE_FRAME))

    assert pipeline.state is AgentState.ERROR


@pytest.mark.asyncio
async def test_overlong_audio_is_cleared_and_not_truncated_into_a_command() -> None:
    pipeline, recognizer, _ = _pipeline(
        settings=VoiceSettings(silence_timeout_ms=80, max_command_seconds=1)
    )
    await pipeline.process_chunk(_chunk(0, b"\x02\x00"))
    update = None
    for sequence in range(1, 27):
        update = await pipeline.process_chunk(_chunk(sequence, SPEECH_FRAME))

    assert update is not None
    assert update.state is AgentState.IDLE
    assert "too long" in (update.speech or "")
    assert recognizer.audio is None


@pytest.mark.asyncio
async def test_audio_sequence_must_increase_and_busy_pipeline_rejects_audio() -> None:
    pipeline, _, _ = _pipeline()
    await pipeline.process_chunk(_chunk(0, b"\x02\x00"))
    await pipeline.process_chunk(_chunk(1, SPEECH_FRAME))

    with pytest.raises(ValueError, match="increase monotonically"):
        await pipeline.process_chunk(_chunk(1, SPEECH_FRAME))

    await pipeline.process_chunk(_chunk(2, SILENCE_FRAME))
    await pipeline.process_chunk(_chunk(3, SILENCE_FRAME))
    with pytest.raises(VoicePipelineBusyError, match="thinking"):
        await pipeline.process_chunk(_chunk(4, SPEECH_FRAME))


def test_mock_audio_round_trips_through_authenticated_websocket() -> None:
    async def handle_transcript(transcript: str) -> str:
        assert transcript == "set a timer"
        return "Timer set."

    def pipeline_factory() -> VoicePipeline:
        return _pipeline()[0]
    handler_factory: MessageHandlerFactory = create_voice_message_handler_factory(
        pipeline_factory,
        handle_transcript,
    )
    token = "voice-test-token-with-at-least-thirty-two-characters"
    app = create_app(
        message_handler_factory=handler_factory,
        token_hash=hash_token(token),
    )

    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws/agent",
            headers={"Authorization": f"Bearer {token}"},
        ) as websocket:
            websocket.send_json(_chunk(0, b"\x02\x00").model_dump(mode="json"))
            assert websocket.receive_json() == {"type": "listening"}
            assert websocket.receive_json() == {
                "type": "speak",
                "text": "Listening.",
                "interrupt": True,
            }
            assert websocket.receive_json()["type"] == "accepted"

            websocket.send_json(_chunk(1, SPEECH_FRAME).model_dump(mode="json"))
            assert websocket.receive_json()["type"] == "accepted"

            websocket.send_json(_chunk(2, SILENCE_FRAME).model_dump(mode="json"))
            assert websocket.receive_json()["type"] == "accepted"

            websocket.send_json(_chunk(3, SILENCE_FRAME).model_dump(mode="json"))
            assert websocket.receive_json() == {
                "type": "speak",
                "text": "Timer set.",
                "interrupt": True,
            }
            assert websocket.receive_json()["type"] == "accepted"

            websocket.send_json(_chunk(4, b"\x02\x00").model_dump(mode="json"))
            assert websocket.receive_json() == {"type": "listening"}
            assert websocket.receive_json()["type"] == "speak"
            assert websocket.receive_json()["type"] == "accepted"
            websocket.send_json(_chunk(5, SPEECH_FRAME).model_dump(mode="json"))
            assert websocket.receive_json()["type"] == "accepted"
            websocket.send_json(_chunk(6, SILENCE_FRAME).model_dump(mode="json"))
            assert websocket.receive_json()["type"] == "accepted"
            websocket.send_json(_chunk(7, SILENCE_FRAME).model_dump(mode="json"))
            assert websocket.receive_json()["type"] == "speak"
            assert websocket.receive_json()["type"] == "accepted"


def test_pcm_buffer_rejects_overflow_and_odd_sample_bytes() -> None:
    buffer = PCMBuffer(max_bytes=2)
    buffer.append(b"\x01\x00")

    with pytest.raises(AudioBufferOverflow):
        buffer.append(b"\x02\x00")
    with pytest.raises(ValueError, match="complete 16-bit"):
        buffer.append(b"\x00")
