# Voice pipeline

## Current implementation

`app.voice.pipeline.VoicePipeline` is an in-memory, hardware-independent
pipeline. It accepts validated 16 kHz mono `pcm_s16le` chunks, calls
injected wake-word, voice-activity, and speech-recognition adapters, and
reports listening, transcript, and speech events. Its PCM buffer is bounded
by `max_command_seconds`; it does not write audio to disk or retain completed
utterances.

The state machine supports the agent states in the system design and rejects
illegal transitions. `create_voice_message_handler_factory` provides
per-WebSocket-session integration for injected adapters; the default
application does not configure a production voice handler. From its connected
screen, Android asks for microphone permission when capture starts and streams
100 ms, 16 kHz mono PCM chunks over the authenticated WebSocket. Capture ends
on user stop, app backgrounding, disconnect, or a 30-second limit. User stop
adds bounded trailing silence to trigger VAD finalization. The app does not
save microphone audio. Android speaks validated Pi `speak` messages through
its installed system TTS engine.
It selects the highest-quality voice available offline for the device language
(English as fallback), and does not send speech text to a network voice. If no
offline voice is installed, the app reports that rather than silently using a
cloud voice. Phone microphone streaming is implemented, but the default Pi app
has no configured wake-word detector, VAD, speech recognizer, intent router,
or task handler. A real spoken request therefore is not processed by the
default server until local adapters are configured. There is no always-on
background wake-word service; microphone capture is explicitly started by the
user and stops when the app leaves the foreground.

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

## Planned device validation

On a physical Android phone, verify an offline voice is available and that a
server `speak` event is audible with airplane mode enabled. On the target Pi,
measure wake-word false accepts/latency, 5-second command transcription time,
memory, CPU temperature/throttling, and behavior under network loss. Use the
project targets only as measured acceptance criteria, not as assumed
performance.
