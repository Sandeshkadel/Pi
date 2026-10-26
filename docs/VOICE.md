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
application does not configure a production voice handler. Tests use fake
adapters and synthetic PCM; passing them does not demonstrate recognition
quality or performance on a Raspberry Pi.

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

## Planned device validation

On the target Pi, measure wake-word false accepts/latency, 5-second command
transcription time, memory, CPU temperature/throttling, and behavior under
network loss. Use the project targets only as measured acceptance criteria,
not as assumed performance.
