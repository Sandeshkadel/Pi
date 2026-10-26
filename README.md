# PiAgent

PiAgent is a privacy-first, offline-capable voice-agent project for Raspberry Pi
and Android. The Raspberry Pi hosts the local agent; an Android app is intended
to provide audio, notifications, and user-confirmed phone interactions.

The project is being built in phases. The current implementation includes a
FastAPI health endpoint, a mobile-friendly read-only status dashboard, an
authenticated and schema-validated WebSocket protocol, mocked voice/state
processing, local task/memory foundations, and a minimal Android app shell.
BLE credential-envelope codecs exist on Python and Android and share a
cross-language test vector. Real BLE pairing, Android phone connectivity,
production speech adapters, notifications, phone automation, and Pi deployment
are not complete. The default WebSocket app still has no connected phone agent
handler.

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
Copy-Item .env.example .env
ruff check .
pytest
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 65536
```

Open `http://127.0.0.1:8000/` for the dashboard and
`http://127.0.0.1:8000/health` for the health check.

## Android shell

Open `android-app/` in Android Studio with Android SDK 35 installed, then run
the `app` configuration on an Android 10+ device or emulator. The current app
is a UI shell with tested provisioning-crypto source, but it does not request
permissions, scan/connect over BLE, or connect to a Pi. Do not send real
credentials; the pairing and transport flow is not implemented.

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

## License

MIT; see [LICENSE](LICENSE).
