# PiAgent

PiAgent is a privacy-first, offline-capable voice-agent project for Raspberry Pi
and Android. The Raspberry Pi hosts the local agent; an Android app is intended
to provide audio, notifications, and user-confirmed phone interactions.

The project is being built in phases. The current implementation includes a
FastAPI health endpoint, a mobile-friendly read-only status dashboard, an
authenticated and schema-validated WebSocket protocol, mocked voice/state
processing, local task/memory foundations, and a native Android connection UI
for private-network authentication, heartbeat checks, and Pi-to-phone speech
responses through an installed offline phone voice. BLE credential-envelope
codecs exist on Python and Android and share a cross-language test vector.
Phone microphone streaming is implemented, but real BLE pairing, Pi-side
production voice adapters, notifications, phone automation, and Pi deployment
are not complete. The default WebSocket app has no command/notification
handler or configured voice adapters.

## Safety and privacy

- Never commit passwords, tokens, Wi-Fi credentials, or private data.
- Do not store or enter device PINs, passwords, one-time codes, or banking credentials.
- PiAgent must not bypass Android lock-screen security.
- External actions must be logged and require task-specific spoken
  confirmation; risky actions must also pass through the safety manager.
- Local/offline processing is the default. Notification history is disabled by
  default.

## Hardware

- Raspberry Pi 5 (4 GB recommended)
- Android phone
- Wi-Fi or a phone hotspot

## Quick start (development)

Requires Python 3.11 or newer.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
ruff check .
pytest
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 65536
```

Open `http://127.0.0.1:8000/` for the dashboard and
`http://127.0.0.1:8000/health` for the health check.
For local WebSocket authentication, run the one-time connection setup in
[SETUP_PI.md](docs/SETUP_PI.md) with a private Pi address. Development mode
without a configured token intentionally rejects WebSocket connections.

## Android shell

Open `android-app/` in Android Studio with Android SDK 35 installed, then run
the `app` configuration on an Android 10+ device or emulator. It can connect
to the authenticated local WebSocket heartbeat when a Pi endpoint and token
are configured. With explicit in-app microphone permission, it can stream
16 kHz audio from the phone mic to the Pi while capture is active and speak Pi
responses through the phone speaker using its installed offline TTS voice.
The standard Pi server still needs voice model adapters configured to process
audio. BLE pairing, notifications, and phone actions are not implemented.
Permissions are listed in-app and requested only when
their features are available. Do not send real Wi-Fi credentials; pairing and
credential handoff are not implemented.

The status dashboard is informational only. Keep the development server bound
to `127.0.0.1`; its health endpoint is unauthenticated and it is not ready for
direct access from a phone over Wi-Fi.

## Documentation

- [Raspberry Pi setup](docs/SETUP_PI.md)
- [Android app](docs/ANDROID_APP.md)
- [Network protocol](docs/NETWORK.md)
- [Voice pipeline](docs/VOICE.md)
- [Local AI](docs/AI.md)
- [Local memory](docs/MEMORY.md)
- [Security model](docs/SECURITY.md)
- [API](docs/API.md)
- [Local testing and emulator validation](docs/TESTING.md)

For initial Pi connection details, run
`python -m app.setup --host <PI_PRIVATE_IPV4> --start`. It creates a new
`.env` with only a strong token hash, shows the WebSocket address and token
once, and starts the server. On later starts it shows the address but never
reprints the token. The token is intentionally not eight digits. The Pi/phone
service still needs deployment hardening; production voice, BLE pairing,
notifications, and phone actions are not implemented.

## License

MIT; see [LICENSE](LICENSE).
