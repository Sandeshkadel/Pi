"""Optional, local-only voice adapters for the standard Pi application."""

from __future__ import annotations

import asyncio
import logging
import os
import struct
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol

from app.ai.intent_router import IntentRouter
from app.ai.ollama import OllamaClient
from app.core.task_engine import TaskEngine
from app.server.websocket import MessageHandlerFactory
from app.voice.pipeline import (
    SpeechRecognizer,
    VoiceBackendError,
    VoicePipeline,
    VoiceSettings,
)
from app.voice.websocket import create_voice_message_handler_factory

logger = logging.getLogger(__name__)


class _WhisperModel(Protocol):
    def transcribe(
        self,
        audio: object,
        **options: object,
    ) -> tuple[Iterable[object], object]: ...


class ManualActivationDetector:
    """Wake-word adapter for explicitly started phone-microphone sessions."""

    async def detected(self, pcm_s16le: bytes) -> bool:
        return False


class EnergyVoiceActivityDetector:
    """Small CPU-only VAD used after the user explicitly starts capture."""

    def __init__(self, threshold: float = 400) -> None:
        if threshold <= 0:
            raise ValueError("VAD energy threshold must be positive.")
        self._threshold = threshold

    async def is_speech(self, pcm_s16le: bytes) -> bool:
        if not pcm_s16le or len(pcm_s16le) % 2:
            raise ValueError("VAD requires non-empty 16-bit PCM samples.")
        sample_count = len(pcm_s16le) // 2
        square_sum = sum(
            sample * sample
            for (sample,) in struct.iter_unpack("<h", pcm_s16le)
        )
        return (square_sum / sample_count) ** 0.5 >= self._threshold


class FasterWhisperRecognizer(SpeechRecognizer):
    """Run a pre-downloaded faster-whisper model without network access."""

    def __init__(
        self,
        model: _WhisperModel,
        *,
        language: str | None = None,
        max_audio_bytes: int = 480_000,
        audio_decoder: Callable[[bytes], object] | None = None,
    ) -> None:
        if max_audio_bytes <= 0:
            raise ValueError("Maximum transcription audio size must be positive.")
        self._model = model
        self._language = language
        self._max_audio_bytes = max_audio_bytes
        self._audio_decoder = audio_decoder
        self._inference_lock = asyncio.Lock()

    @classmethod
    def from_local_path(
        cls,
        model_path: str | Path,
        *,
        language: str | None = None,
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> FasterWhisperRecognizer:
        path = Path(model_path).expanduser()
        if not path.is_dir():
            raise VoiceBackendError(
                f"Local speech model directory does not exist: {path}"
            )
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise VoiceBackendError(
                "Install PiAgent's optional voice dependencies before enabling speech recognition."
            ) from error

        try:
            model = WhisperModel(
                str(path),
                device=device,
                compute_type=compute_type,
                local_files_only=True,
                cpu_threads=2,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise VoiceBackendError(
                "The local faster-whisper model could not be loaded."
            ) from error
        return cls(model, language=language)

    async def transcribe(self, pcm_s16le: bytes) -> str:
        if not pcm_s16le or len(pcm_s16le) % 2 or len(pcm_s16le) > self._max_audio_bytes:
            raise VoiceBackendError("Transcription audio is empty or outside its size limit.")
        async with self._inference_lock:
            try:
                return await asyncio.to_thread(self._transcribe_sync, pcm_s16le)
            except VoiceBackendError:
                raise
            except (OSError, RuntimeError, ValueError, ImportError) as error:
                raise VoiceBackendError("Local speech recognition failed.") from error

    def _transcribe_sync(self, pcm_s16le: bytes) -> str:
        if self._audio_decoder is None:
            try:
                import numpy
            except ImportError as error:
                raise VoiceBackendError(
                    "The local speech model's audio dependency is unavailable."
                ) from error
            audio = numpy.frombuffer(pcm_s16le, dtype=numpy.int16)
            audio = audio.astype(numpy.float32) / 32768
        else:
            audio = self._audio_decoder(pcm_s16le)

        options: dict[str, object] = {
            "beam_size": 1,
            "condition_on_previous_text": False,
            "vad_filter": False,
        }
        if self._language is not None:
            options["language"] = self._language
        segments, _ = self._model.transcribe(audio, **options)
        return " ".join(
            text
            for segment in segments
            if (text := str(getattr(segment, "text", "")).strip())
        )


def create_configured_voice_handler_factory() -> MessageHandlerFactory | None:
    """Build the default voice handler only when a local model is configured."""
    model_path = os.getenv("WHISPER_MODEL_PATH", "").strip()
    if not model_path:
        return None

    recognizer = FasterWhisperRecognizer.from_local_path(
        model_path,
        language=os.getenv("WHISPER_LANGUAGE") or None,
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
    )
    vad = EnergyVoiceActivityDetector(
        threshold=float(os.getenv("VOICE_VAD_THRESHOLD", "400"))
    )
    wake_word_detector = ManualActivationDetector()
    voice_settings = VoiceSettings(
        max_command_seconds=15,
        transcription_timeout_seconds=45,
    )

    local_llm = (
        OllamaClient(
            base_url=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"),
            timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "12")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "180")),
        )
        if os.getenv("USE_OLLAMA", "true").casefold() == "true"
        else None
    )
    task_engine = TaskEngine(IntentRouter(llm=local_llm), llm=local_llm)

    async def handle_transcript(transcript: str) -> str:
        result = await task_engine.handle(transcript)
        logger.info(
            "Voice request handled: intent=%s status=%s",
            result.intent,
            result.status,
        )
        return result.response

    return create_voice_message_handler_factory(
        lambda: VoicePipeline(
            wake_word_detector=wake_word_detector,
            vad=vad,
            recognizer=recognizer,
            settings=voice_settings,
        ),
        handle_transcript,
    )
