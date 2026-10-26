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
Raspberry Pi, microphone, Bluetooth radio, phone, or local model. The wheel
must include `dashboard/index.html` so the served dashboard still works after
installation.

The first-run connection setup tests verify private IPv4 validation,
one-time token display, hash-only `.env` contents, refusal to overwrite an
existing file, and POSIX owner-only permissions. The permission-bit check is
skipped on Windows because POSIX mode bits are not enforced there.

## Android build and unit tests

With Android SDK 35 and Java 17 installed, run from `android-app/`:

```powershell
gradle testDebugUnitTest assembleDebug
```

The unit tests cover local endpoint and token validation, provisioning
envelope parsing, credential validation, single-use behavior, tamper rejection,
session binding, and decryption of a fixed ciphertext produced by the Python
implementation. `assembleDebug` must complete before installing an APK.

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
- Python test suite: 83 passed, 1 skipped. The POSIX-only `.env` permission
  assertion is skipped on Windows.
- Python wheel: built and confirmed to contain `dashboard/index.html`.
- Android unit tests: 7 passed (4 provisioning crypto, 3 endpoint/token
  validation); debug APK build passed with the installed local SDK.
- Android API 36 emulator: confirmed the token field starts masked; its
  accessible eye control reveals the test-only input and masks it again.
- Android API 36 emulator: installed and launched the native PiAgent app.
  Connected it through `adb reverse` to the loopback FastAPI server using a
  test-only token; the UI reported an authenticated healthy heartbeat.
  Retried with an invalid token and verified the UI showed authentication
  failure. Disconnect also returned the UI to its not-connected state.
- Android API 36 emulator: verified the token remains masked by default and
  that the accessible eye control reveals and re-masks the entered value.
- The emulator's separate Bluetooth system process briefly crashed and
  restarted; no PiAgent crash was observed. BLE was not exercised.
- Android browser dashboard: the development server was accessed through
  `adb reverse`, loaded in the emulator browser, and displayed the live
  `Online` health state and incomplete integration statuses at 1080x1920.
  This only tests local display; the development server must remain
  loopback-bound and is not a deployable phone connection.

## Not validated by these checks

The BLE GATT peripheral/client, secure bootstrap-key exchange, Wi-Fi
credential handoff, real audio capture/playback, notification forwarding,
Accessibility automation, local model performance, Raspberry Pi resource use,
startup after reboot, and network-loss recovery are not implemented or are
hardware-dependent. Report these as pending until separately tested on the
intended Android phone and Pi.
