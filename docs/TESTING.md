# Local testing and device validation

Run these checks on the development computer before publishing a change. GitHub
Actions is not a substitute for the local Android build or emulator checks.

## Python and packaged resources

From the repository root:

```powershell
python -m ruff check .
python -m pytest -q
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir $env:TEMP
```

The Python tests use mocked or in-memory dependencies; they do not require a
Raspberry Pi, microphone, Bluetooth radio, phone, or local model. The wheel must include `dashboard/index.html` and `app/setup.py` so the
dashboard and first-run setup command work after installation.

The first-run connection setup tests verify private IPv4 validation,
one-time token display, hash-only `.env` contents, refusal to overwrite an
existing file, token rotation, startup without redisplaying the token,
environment-token conflict detection, authenticated WebSocket heartbeat,
cross-instance BLE replay protection, and POSIX owner-only permissions. The
permission-bit check is skipped on Windows because POSIX mode bits are not
enforced there.

## Android build and unit tests

With Android SDK 35 and Java 17 installed, run from `android-app/`:

```powershell
gradle testDebugUnitTest assembleDebug
```

The unit tests cover local endpoint and token validation, provisioning
envelope parsing, credential validation, single-use behavior, tamper rejection,
session binding, decryption of a fixed ciphertext produced by the Python
implementation, strict parsing of Pi speech messages, offline-only TTS voice
selection, supported speech-tuning bounds/defaults, and audio frame encoding
limits. `assembleDebug` must complete before installing an APK.

## Emulator smoke test

Start an Android API 29+ virtual device, then run from the repository root:

```powershell
adb devices -l
adb install -r android-app\app\build\outputs\apk\debug\app-debug.apk
adb shell am force-stop com.sandeshkadel.piagent
adb shell am start -n com.sandeshkadel.piagent/.MainActivity
adb shell dumpsys activity activities
```

Verify the PiAgent activity is resumed, the connection and permission
sections are visible, and `adb logcat` contains no PiAgent fatal exception.
To test the actual WebSocket from the emulator, run the authenticated FastAPI
service on the host, configure the corresponding token hash, then use
`adb reverse tcp:8000 tcp:8000` and enter
`ws://127.0.0.1:8000/ws/agent` with the matching token in the app. The app
should show an authenticated, healthy heartbeat. This is an emulator-to-host
local test, not a real Pi over Wi-Fi test.

To display the local status dashboard in the emulator browser while the
development server runs on the computer:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
adb reverse tcp:8000 tcp:8000
adb shell am start -a android.intent.action.VIEW -d http://127.0.0.1:8000/
```

This uses the emulator's host loopback bridge. It does not demonstrate phone
connectivity to a Raspberry Pi over Wi-Fi.

## Current local verification record

- Python lint: passed.
- Python test suite: 90 passed, 1 skipped. The POSIX-only `.env` permission
  assertion is skipped on Windows.
- Python wheel: built and confirmed to contain `dashboard/index.html`.
- Android unit tests: 23 passed (7 provisioning crypto, 3 endpoint/token
  validation, 3 audio-message encoding, 4 Pi speech-message parsing, 3 offline
  voice selection, and 3 speech-tuning tests); debug APK build passed.
- Android API 36 emulator: installed and launched the native PiAgent app.
  Connected it through `adb reverse` to the loopback FastAPI server using a
  test-only token; the UI reported an authenticated healthy heartbeat.
  Retried with an invalid token and verified the UI showed authentication
  failure. Disconnect also returned the UI to its not-connected state.
- Android API 36 emulator: confirmed the selected `en-AU-language` voice is
  offline, the pitch/rate controls and connection-cue toggle render, and a
  voice preview completed according to the Android TTS callback. A separate
  local authenticated WebSocket test reached a healthy heartbeat and completed
  the connection-ready cue through the offline phone TTS. This confirms TTS
  synthesis, not what a person hears from an emulator or physical speaker.
- Android API 36 emulator: verified the token remains masked by default and
  that the accessible eye control reveals and re-masks the entered value.
- Android API 36 emulator: microphone permission was requested only after
  tapping Start. The app streamed captured PCM through `adb reverse` to a
  local authenticated FastAPI server with mocked wake-word, VAD, and STT
  adapters. The mock server returned `listening` and a speech response; the
  installed offline phone TTS reported that it finished speaking.
- Android API 36 emulator: starting capture and backgrounding PiAgent stopped
  the microphone; returning to the app showed the microphone inactive.
- The emulator test used mocked voice recognition; it did not test real human
  speech recognition or a production model on the Pi.
- Android release variant: `assembleRelease` passed. The generated APK is
  unsigned because no user-owned release signing key is configured; it is not
  a publishable or installable signed release.
- The emulator's separate Bluetooth system process briefly crashed and
  restarted; no PiAgent crash was observed. BLE was not exercised.
- Android browser dashboard: the development server was accessed through
  `adb reverse`, loaded in the emulator browser, and displayed the live
  `Online` health state and incomplete integration statuses at 1080x1920.
  This only tests local display; the development server must remain
  loopback-bound and is not a deployable phone connection.

## Not validated by these checks

The BLE GATT peripheral/client, secure bootstrap-key exchange, Wi-Fi
credential handoff, physical-phone microphone/audio behavior and audible TTS
quality, Pi-side production voice adapters, notification forwarding,
Accessibility automation, local model performance, Raspberry Pi resource use,
startup after reboot, and network-loss recovery are not implemented or are
hardware-dependent. Report these as pending until separately tested on the
intended Android phone and Pi.
