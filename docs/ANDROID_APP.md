# Android App

## Requirements

- Android Studio and Android SDK 35
- Android 10 or newer (API 29+)
- Java 17 and Gradle

## Build and tests

Open `android-app/` in Android Studio and run the `app` configuration, or use
Gradle:

```powershell
gradle testDebugUnitTest assembleDebug
```

## Current app capabilities

- Enter a Pi's local WebSocket address and agent token. The app rejects public
  hosts, credentials or tokens embedded in URLs, and non-agent paths.
- Establish an authenticated WebSocket connection and exchange the protocol
  heartbeat, displaying connection and authentication failures without
  logging the token.
- Speak validated Pi `speak` messages with the highest-quality installed
  offline system voice for the phone's language (English fallback). The app
  never silently selects a network-required TTS voice; install offline voice
  data in Android's text-to-speech settings if none is available.
- Adjust and locally save the selected phone voice's pitch and speaking rate,
  preview it, and optionally hear a “Pi is connected and ready” cue after an
  authenticated connection. The defaults are neutral pitch (1.0×) and a
  slightly slower rate (0.95×), adjustable from 0.8× to 1.2×. Android's
  generic TTS API does not expose direct frequency-in-hertz control. Audio
  plays on the phone, not the Raspberry Pi.
- Start and stop foreground-only capture from the phone microphone. Permission
  is requested only when capture starts. Audio is streamed in bounded 100 ms,
  16 kHz mono PCM chunks over the authenticated WebSocket, with no audio file
  or recording retained by the app. Capture stops when the app leaves the
  foreground or after 30 seconds; explicit start/stop protocol messages bound
  the listening session, without synthetic silence frames.
- The token remains in memory only and is not saved by the app.
- The token starts masked and includes an accessible eye control to reveal or
  hide it while entering.
- View a permission status list. Sensitive permissions are not requested at
  startup; microphone permission is requested only when starting capture,
  while Bluetooth, notification access, and Accessibility are not requested.

Run `python -m app.setup --host <PI_PRIVATE_IPV4>` on the Pi once to create the
connection address and token, as described in [SETUP_PI.md](./SETUP_PI.md).
The command displays a strong token once and saves only its hash on the Pi.
The Android app requires a token of at least 32 characters; an eight-digit
number is not accepted as a permanent network credential. If the token is
lost, rotate it on the Pi and enter the replacement.

Use a private network address such as
`ws://192.168.0.10:8000/ws/agent` only when the Pi and phone are on the same
trusted local network. The Pi must have `AGENT_TOKEN_HASH` set to the SHA-256
hash of the token entered in the app. Cleartext WebSocket is permitted for
local development, while the app's connection screen restricts endpoints to
private network addresses, loopback, or `.local` hostnames. A `ws://`
connection does not encrypt the bearer token; use `wss://` with a correctly
configured Pi TLS endpoint for deployment, and never connect over a public or
untrusted shared network. Do not expose the development server or use the
example address as a real device configuration.

## Not implemented

- BLE scanning/GATT, secure bootstrap-key exchange, pairing confirmation, and
  Wi-Fi credential handoff.
- Token persistence or automatic reconnect after process death.
- An always-on background wake-word service; microphone capture is explicit
  and stops when the app leaves the foreground.
- An always-on wake-word detector. Optional local Pi-side faster-whisper
  speech recognition and energy-threshold VAD are available when configured
  with a pre-downloaded model; see [VOICE.md](./VOICE.md). The default Pi
  server leaves this disabled until `WHISPER_MODEL_PATH` is set.
- A phone-action dispatcher. PiAgent can classify and safely respond to
  supported requests, but it does not open apps, send messages, or automate
  Android UI.
- NotificationListenerService, Accessibility automation, and sending
  commands/notifications or triggering phone actions.

The Python and Android provisioning codecs share a cross-language test vector,
but the complete provisioning flow is not ready. Do not enter or transfer real
Wi-Fi credentials. Grant permissions only when the related feature is
available and you choose to enable it; the app must not request every
permission at startup. The status dashboard is a separate diagnostic page,
not the Android app or a replacement for its connection UI.
