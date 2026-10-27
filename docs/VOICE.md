# Voice pipeline

## Current implementation

`app.voice.pipeline.VoicePipeline` is an in-memory, hardware-independent
pipeline. It accepts validated 16 kHz mono `pcm_s16le` chunks, keeps speech
within a bounded 15-second PCM buffer, and supports injected wake-word,
voice-activity, and speech-recognition adapters for tests.

The Android connected screen explicitly starts capture after the user taps
Start and grants microphone permission. It sends a validated `voice_control`
start message, streams 100 ms PCM frames, then sends a stop message when the
user taps Stop, the 30-second capture cap is reached, or the app moves to the
background. Explicitly started sessions do not depend on a wake-word model or
silence timeout. No microphone audio is saved. The Pi returns `listening` and
`speak` protocol messages; Android uses its installed offline system TTS
engine, with local pitch/rate settings, to speak through the phone speaker.

The standard Pi application can enable local speech-to-text when
`WHISPER_MODEL_PATH` points to a pre-downloaded faster-whisper model directory.
The optional adapter loads only local files, runs CPU/int8 inference off the
async event loop, and never downloads a model at runtime. A lightweight
energy-threshold VAD is used to avoid transcribing captured silence. The local
task engine provides deterministic intents and can use loopback-only Ollama
for supported classification or drafting; it does not execute phone actions
because a phone-action dispatcher is not configured. Without a local speech
model path, audio requests receive an explicit `agent_not_ready` response.

There is no always-on or background "Hey Pi" wake-word service; microphone
capture is explicitly started by the user. Saying "Hey Pi" is optional during
the manually started session. The model pipeline, energy threshold, and safety
response are covered by mock-based tests, but real speech recognition speed,
accuracy, and memory use have not been tested on a Raspberry Pi.

## Voicebox evaluation

[Voicebox](https://github.com/jamiepine/voicebox) is an MIT-licensed desktop
voice studio with multiple TTS engines, voice profiles, and local agent APIs.
Its documented Linux workflow builds the complete application from source;
its `/speak` API is intended for agent-triggered playback by a running Voicebox
instance, rather than serving as a bundled PiAgent synthesis library.

The Voicebox README lists Kokoro as an 82-million-parameter, CPU-capable
engine, and the [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M)
states that its weights are Apache-licensed. That makes Kokoro a candidate for
a future Pi-side engine, but this repository has not verified ARM64
dependencies, Raspberry Pi latency, memory use, or model-voice licensing and
distribution terms. Voicebox's MIT application license does not grant licenses
for every engine's model weights or voice data. PiAgent therefore does not
bundle Voicebox, Kokoro, cloned voices, or model files.

The current default uses the phone's offline TTS engine because it avoids
adding another model/runtime to the Pi and speaks on the phone's speaker. The
selected voice and quality are determined by TTS voices already installed on
the phone; the app cannot promise a specific timbre across devices.

The Android app provides local pitch and speaking-rate sliders with a neutral
pitch (1.0×) and slightly slower rate (0.95×) by default; both settings are
stored only in app-private preferences and are bounded to 0.8×–1.2×. Android's
generic TTS API exposes pitch and rate multipliers, not direct frequency-in-Hz
control. A user can preview the installed voice and can enable or mute the
spoken “Pi is connected and ready” cue. When enabled, that cue plays on the
phone after the authenticated WebSocket connects; it does not play through a
speaker attached to the Raspberry Pi. Pi-side audio output remains
unimplemented.

## Enabling local speech recognition

Install the optional Python dependency in the PiAgent virtual environment:

```bash
python -m pip install ".[voice]"
```

Obtain the CTranslate2-format `Systran/faster-whisper-tiny` model files from
the [Hugging Face model card](https://huggingface.co/Systran/faster-whisper-tiny)
using a trusted method, and place the complete model in a local directory such
as `/home/pi/models/faster-whisper-tiny`. Its model card declares an MIT
license. [CTranslate2 documents Linux AArch64 wheels](https://opennmt.net/CTranslate2/installation.html),
but this repository has not verified installation, speed, or resource use on
the target Pi.

Set `WHISPER_MODEL_PATH` to that directory when launching the server. For
example:

```bash
WHISPER_MODEL_PATH=/home/pi/models/faster-whisper-tiny \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  --ws-max-size 65536 --env-file .env
```

The application fails at startup with a clear error if the configured model
directory, optional package, or model is unavailable. Leave
`WHISPER_MODEL_PATH` unset to disable voice processing. `WHISPER_LANGUAGE`
defaults to English, `WHISPER_DEVICE` to `cpu`, and `WHISPER_COMPUTE_TYPE` to
`int8`; `VOICE_VAD_THRESHOLD` can tune the local energy threshold. No model
weights, audio, or transcript are sent to a cloud service.

## Adapter requirements

- Keep CPU-bound inference off the asyncio event loop.
- Wrap expected local model/runtime failures as `VoiceBackendError`.
- Do not log or persist PCM or transcripts.
- Use bounded queues and enforce the configured sample rate, duration, and
  buffer caps.
- Bound transcription time and move the state machine to an explicit error
  state when a backend fails or times out.
- Treat transcripts as untrusted input; intent routing and safety checks remain
  separate deterministic steps.
- Check model and voice licenses before installation or distribution.
- Do not use voice cloning unless the user owns the voice or has explicit
  permission to use it.
- Keep wake-word activation disabled unless a real local detector is configured
  and the user explicitly enables its microphone behavior.

## Planned device validation

On a physical Android phone, verify an offline voice is available and that a
server `speak` event is audible with airplane mode enabled. On the target Pi,
measure 5-second command transcription time, memory, CPU
temperature/throttling, and behavior under network loss. Wake-word false
accepts and latency are not applicable until a local wake-word detector is
implemented. Use the project targets only as measured acceptance criteria, not
as assumed performance.
