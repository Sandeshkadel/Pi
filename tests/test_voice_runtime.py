import asyncio
import base64
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_token
from app.main import create_app
from app.server.schemas import AudioChunk, VoiceControl
from app.voice.pipeline import VoiceBackendError
from app.voice.runtime import (
    EnergyVoiceActivityDetector,
    FasterWhisperRecognizer,
)


class FakeWhisperModel:
    def __init__(self, transcript: str = " open YouTube ") -> None:
        self.transcript = transcript
        self.audio: object | None = None
        self.options: dict[str, object] = {}

    def transcribe(
        self,
        audio: object,
        **options: object,
    ) -> tuple[list[SimpleNamespace], None]:
        self.audio = audio
        self.options = options
        return [SimpleNamespace(text=self.transcript)], None


class MockRecognizer:
    async def transcribe(self, pcm_s16le: bytes) -> str:
        return "open YouTube"


def test_energy_vad_distinguishes_speech_from_silence() -> None:
    vad = EnergyVoiceActivityDetector(threshold=400)

    assert asyncio.run(vad.is_speech(b"\x00\x00" * 640)) is False
    assert asyncio.run(vad.is_speech(b"\xe8\x03" * 640)) is True


def test_local_recognizer_uses_local_model_without_cloud_or_download(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_path = tmp_path / "whisper-tiny"
    model_path.mkdir()
    model = FakeWhisperModel(" hello there ")
    requested: dict[str, object] = {}

    class FakeWhisperModelLoader:
        def __init__(self, path: str, **options: object) -> None:
            requested.update(path=path, **options)

        def transcribe(
            self,
            audio: object,
            **options: object,
        ) -> tuple[list[SimpleNamespace], None]:
            return model.transcribe(audio, **options)

    fake_package = ModuleType("faster_whisper")
    fake_package.WhisperModel = FakeWhisperModelLoader
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_package)

    recognizer = FasterWhisperRecognizer.from_local_path(model_path)
    test_recognizer = FasterWhisperRecognizer(
        model,
        audio_decoder=lambda pcm: pcm,
    )

    assert isinstance(recognizer, FasterWhisperRecognizer)
    assert asyncio.run(test_recognizer.transcribe(b"\x01\x00" * 640)) == "hello there"
    assert model.options == {
        "beam_size": 1,
        "condition_on_previous_text": False,
        "vad_filter": False,
    }
    assert requested["path"] == str(model_path)
    assert requested["local_files_only"] is True
    assert requested["device"] == "cpu"
    assert requested["compute_type"] == "int8"


def test_local_recognizer_rejects_missing_model_directory(tmp_path) -> None:
    with pytest.raises(VoiceBackendError, match="directory does not exist"):
        FasterWhisperRecognizer.from_local_path(tmp_path / "missing")


def test_configured_application_processes_phone_audio_with_local_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WHISPER_MODEL_PATH", "C:\\models\\whisper-tiny")
    monkeypatch.setenv("USE_OLLAMA", "false")
    monkeypatch.setattr(
        FasterWhisperRecognizer,
        "from_local_path",
        classmethod(lambda _cls, *_args, **_kwargs: MockRecognizer()),
    )
    token = "local-voice-test-token-with-at-least-thirty-two-characters"
    app = create_app(token_hash=hash_token(token))
    speech = b"\xe8\x03" * 1_600

    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws/agent",
            headers={"Authorization": "Bearer " + token},
        ) as websocket:
            websocket.send_json(VoiceControl(type="voice_control", action="start").model_dump())
            assert websocket.receive_json()["type"] == "listening"
            assert websocket.receive_json()["text"] == "Listening."
            assert websocket.receive_json()["type"] == "accepted"

            websocket.send_json(
                AudioChunk(
                    type="audio_chunk",
                    sequence=0,
                    format="pcm_s16le",
                    sample_rate=16_000,
                    data=base64.b64encode(speech).decode("ascii"),
                ).model_dump(mode="json")
            )
            assert websocket.receive_json()["type"] == "accepted"

            websocket.send_json(VoiceControl(type="voice_control", action="stop").model_dump())
            response = websocket.receive_json()
            assert response == {
                "type": "speak",
                "text": "Phone control is not connected, so I did not open an app.",
                "interrupt": True,
            }
            assert websocket.receive_json()["type"] == "accepted"
