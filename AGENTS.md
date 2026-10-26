# PiAgent — Repository Instructions

## Project

PiAgent is a privacy-first, offline-capable AI voice agent.

It runs on a Raspberry Pi 5 and connects to an Android phone using:
- BLE for first-time discovery and provisioning
- Wi-Fi WebSocket for real-time audio, notifications, and commands
- Android Accessibility for safe UI automation
- Android NotificationListenerService for notification access

The user activates it by saying “Hey Pi” or “Hello Pi”.

## Non-negotiable rules

- Never commit secrets, passwords, tokens, Wi-Fi credentials, or private data.
- Never implement Android lock-screen bypass.
- Never store or enter PINs, passwords, OTPs, or banking credentials.
- Never allow automatic high-risk actions without explicit user confirmation.
- Use local/offline AI first; do not require cloud API keys.
- Keep the system fast and suitable for Raspberry Pi 5 4 GB.
- Use small local models: qwen2.5:1.5b or llama3.2:1b via Ollama.
- Use faster-whisper tiny/base for speech-to-text.
- Use Piper for text-to-speech.
- Use OpenWakeWord for wake-word detection.
- Use SQLite for local memory.
- Use FastAPI and WebSockets on the Pi.
- Use Kotlin for Android.
- Use async Python and Kotlin coroutines.
- Every external action must be logged.
- Every risky action must pass through the safety manager.

## Python standards

- Python 3.11+
- Type hints required
- Pydantic models for all WebSocket and API payloads
- FastAPI async endpoints
- Modular architecture
- No circular imports
- No global mutable state
- Use dependency injection where practical
- Use Ruff for linting
- Use pytest for testing

## Android standards

- Kotlin
- Coroutines
- MVVM-lite structure
- Foreground services for microphone and agent connection
- Material 3
- No unnecessary dependencies
- Handle permission denial gracefully
- Auto-reconnect WebSocket and BLE where appropriate

## Testing

Every core module must have tests:

- Intent router
- Safety manager
- Permission manager
- State machine
- WebSocket schemas
- Notification handler
- Memory
- BLE provisioning validation

Run:

```bash
ruff check .
pytest
```

## Definition of done

A feature is complete only when:

- Code is implemented
- Tests exist
- Documentation is updated
- No secrets are exposed
- Error handling exists
- Logging exists
- The feature works with mocked hardware where real hardware is unavailable