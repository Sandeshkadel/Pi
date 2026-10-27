"""In-memory, mockable PCM voice pipeline."""

import asyncio
import base64
import binascii
from dataclasses import dataclass
from typing import Protocol

from app.core.state import AgentState, AgentStateMachine
from app.server.schemas import AudioChunk


class VoiceBackendError(RuntimeError):
    """Raised by a model adapter when local inference cannot complete."""


class AudioBufferOverflow(ValueError):
    """Raised rather than truncating an utterance when its memory cap is reached."""


class VoicePipelineBusyError(RuntimeError):
    """Raised when audio arrives while the agent is in a non-listening state."""


class WakeWordDetector(Protocol):
    async def detected(self, pcm_s16le: bytes) -> bool: ...


class VoiceActivityDetector(Protocol):
    async def is_speech(self, pcm_s16le: bytes) -> bool: ...


class SpeechRecognizer(Protocol):
    """Async adapter; expensive blocking inference must not run on the event loop."""

    async def transcribe(self, pcm_s16le: bytes) -> str: ...


class SpeechOutput(Protocol):
    async def speak(self, text: str) -> None: ...


@dataclass(frozen=True)
class VoiceSettings:
    sample_rate: int = 16_000
    channels: int = 1
    chunk_ms: int = 40
    silence_timeout_ms: int = 1_200
    max_command_seconds: int = 15
    transcription_timeout_seconds: float = 12

    def __post_init__(self) -> None:
        if self.sample_rate <= 0 or self.channels != 1:
            raise ValueError("Voice input must use a positive sample rate and mono audio.")
        if (
            self.chunk_ms <= 0
            or self.silence_timeout_ms <= 0
            or self.max_command_seconds <= 0
            or self.transcription_timeout_seconds <= 0
        ):
            raise ValueError("Voice time limits must be positive.")
        if self.sample_rate * self.chunk_ms % 1_000:
            raise ValueError("Sample rate and chunk duration must produce whole samples.")

    @property
    def max_command_bytes(self) -> int:
        return self.sample_rate * self.max_command_seconds * 2

    @property
    def silence_timeout_samples(self) -> int:
        return self.sample_rate * self.silence_timeout_ms // 1_000


@dataclass(frozen=True)
class VoiceUpdate:
    state: AgentState
    listening_started: bool = False
    transcript: str | None = None
    speech: str | None = None


class PCMBuffer:
    """Bounded in-memory PCM buffer with explicit overflow behavior."""

    def __init__(self, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("PCM buffer size must be positive.")
        self._max_bytes = max_bytes
        self._data = bytearray()

    def append(self, pcm_s16le: bytes) -> None:
        if len(pcm_s16le) % 2:
            raise ValueError("PCM s16le data must contain complete 16-bit samples.")
        if len(self._data) + len(pcm_s16le) > self._max_bytes:
            raise AudioBufferOverflow("Maximum command audio size exceeded.")
        self._data.extend(pcm_s16le)

    def take(self) -> bytes:
        data = bytes(self._data)
        self.clear()
        return data

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class VoicePipeline:
    """Per-connection pipeline that retains only the active utterance in memory."""

    def __init__(
        self,
        wake_word_detector: WakeWordDetector,
        vad: VoiceActivityDetector,
        recognizer: SpeechRecognizer,
        speech_output: SpeechOutput | None = None,
        settings: VoiceSettings | None = None,
        state_machine: AgentStateMachine | None = None,
    ) -> None:
        self._wake_word_detector = wake_word_detector
        self._vad = vad
        self._recognizer = recognizer
        self._speech_output = speech_output
        self._settings = settings or VoiceSettings()
        self._state_machine = state_machine or AgentStateMachine()
        self._audio = PCMBuffer(self._settings.max_command_bytes)
        self._silence_samples = 0
        self._has_speech = False
        self._manual_session = False
        self._last_sequence: int | None = None

    @property
    def state(self) -> AgentState:
        return self._state_machine.state

    async def begin_listening(self) -> VoiceUpdate:
        """Start a user-initiated microphone session without wake-word detection."""
        if self.state is not AgentState.IDLE:
            raise VoicePipelineBusyError(
                f"Cannot start listening while the agent is {self.state.value}."
            )
        self._clear_utterance()
        self._manual_session = True
        self._state_machine.transition(AgentState.LISTENING)
        prompt = "Listening."
        await self._speak(prompt)
        return VoiceUpdate(state=self.state, listening_started=True, speech=prompt)

    async def finish_listening(self) -> VoiceUpdate:
        """Finish a push-to-talk session and transcribe any buffered speech."""
        if self.state is AgentState.IDLE:
            return VoiceUpdate(state=self.state)
        if self.state is not AgentState.LISTENING:
            raise VoicePipelineBusyError(
                f"Cannot finish listening while the agent is {self.state.value}."
            )
        if self._has_speech:
            return await self._transcribe_utterance()

        self._state_machine.transition(AgentState.RESPONDING)
        prompt = "I didn't hear a command. Please try again."
        await self._speak(prompt)
        self._state_machine.transition(AgentState.IDLE)
        self._clear_utterance()
        return VoiceUpdate(state=self.state, speech=prompt)

    async def process_chunk(self, chunk: AudioChunk) -> VoiceUpdate:
        """Process one already-validated audio message and return any user-facing event."""
        if chunk.format != "pcm_s16le" or chunk.sample_rate != self._settings.sample_rate:
            raise ValueError("Audio format or sample rate does not match the voice pipeline.")
        if self._last_sequence is not None and chunk.sequence <= self._last_sequence:
            raise ValueError("Audio sequence numbers must increase monotonically.")
        self._last_sequence = chunk.sequence

        try:
            pcm = base64.b64decode(chunk.data, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Audio data must be valid base64.") from error
        if not pcm or len(pcm) % 2:
            raise ValueError("PCM s16le data must contain complete 16-bit samples.")

        if self.state is AgentState.IDLE:
            if await self._wake_word_detector.detected(pcm):
                self._state_machine.transition(AgentState.LISTENING)
                self._clear_utterance()
                await self._speak("Listening.")
                return VoiceUpdate(
                    state=self.state,
                    listening_started=True,
                    speech="Listening.",
                )
            return VoiceUpdate(state=self.state)

        if self.state is not AgentState.LISTENING:
            raise VoicePipelineBusyError(
                f"Cannot accept audio while the agent is {self.state.value}."
            )

        if await self._vad.is_speech(pcm):
            try:
                self._audio.append(pcm)
            except AudioBufferOverflow:
                await self._finish_overlong_utterance()
                return VoiceUpdate(
                    state=self.state,
                    speech="That command was too long. Please try a shorter command.",
                )
            self._has_speech = True
            self._silence_samples = 0
            return VoiceUpdate(state=self.state)

        if not self._has_speech:
            return VoiceUpdate(state=self.state)

        if self._manual_session:
            return VoiceUpdate(state=self.state)

        self._silence_samples += len(pcm) // 2
        if self._silence_samples < self._settings.silence_timeout_samples:
            return VoiceUpdate(state=self.state)

        return await self._transcribe_utterance()

    async def stop(self) -> VoiceUpdate:
        """Clear buffered audio and enter the terminal stopped state."""
        self._clear_utterance()
        self._state_machine.transition(AgentState.STOPPED)
        return VoiceUpdate(state=self.state)

    async def reset(self) -> VoiceUpdate:
        """Return an errored or stopped pipeline to idle."""
        if self.state not in {AgentState.ERROR, AgentState.STOPPED}:
            raise VoicePipelineBusyError("Only a stopped or errored pipeline can be reset.")
        self._clear_utterance()
        self._last_sequence = None
        self._state_machine.transition(AgentState.IDLE)
        return VoiceUpdate(state=self.state)

    async def complete_response(self) -> VoiceUpdate:
        """Return to idle after the downstream intent/task handler responds."""
        if self.state is not AgentState.THINKING:
            raise VoicePipelineBusyError("Only a thinking pipeline can complete a response.")
        self._state_machine.transition(AgentState.RESPONDING)
        self._state_machine.transition(AgentState.IDLE)
        self._clear_utterance()
        return VoiceUpdate(state=self.state)

    async def _transcribe_utterance(self) -> VoiceUpdate:
        audio = self._audio.take()
        self._silence_samples = 0
        self._has_speech = False
        self._manual_session = False
        self._state_machine.transition(AgentState.TRANSCRIBING)
        try:
            transcript = (
                await asyncio.wait_for(
                    self._recognizer.transcribe(audio),
                    timeout=self._settings.transcription_timeout_seconds,
                )
            ).strip()
        except TimeoutError as error:
            self._state_machine.transition(AgentState.ERROR)
            raise VoiceBackendError("Speech recognition timed out.") from error
        except VoiceBackendError:
            self._state_machine.transition(AgentState.ERROR)
            raise

        if not transcript:
            self._state_machine.transition(AgentState.RESPONDING)
            prompt = "I didn't catch that. Please try again."
            await self._speak(prompt)
            self._state_machine.transition(AgentState.IDLE)
            return VoiceUpdate(state=self.state, speech=prompt)

        self._state_machine.transition(AgentState.THINKING)
        return VoiceUpdate(state=self.state, transcript=transcript)

    async def _finish_overlong_utterance(self) -> None:
        self._state_machine.transition(AgentState.RESPONDING)
        self._clear_utterance()
        prompt = "That command was too long. Please try a shorter command."
        await self._speak(prompt)
        self._state_machine.transition(AgentState.IDLE)

    async def _speak(self, text: str) -> None:
        if self._speech_output is not None:
            await self._speech_output.speak(text)

    def _clear_utterance(self) -> None:
        self._audio.clear()
        self._silence_samples = 0
        self._has_speech = False
        self._manual_session = False
