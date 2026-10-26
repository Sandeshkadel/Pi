# Android App

## Requirements

- Android Studio and Android SDK 35
- Android 10 or newer (API 29+)

## Build

Open `android-app/` in Android Studio and build the `app` configuration. The
starter app uses Gradle and Kotlin with a minimal Compose screen.

The starter does not request microphone, notification, Bluetooth, or
Accessibility permissions. Those permissions must be added only alongside
their user-facing feature and permission-denial handling.

## Current limitations

- The BLE credential envelope codec is implemented, but BLE scanning/GATT,
  secure bootstrap-key exchange, user pairing confirmation, Wi-Fi handoff,
  and WebSocket connection are not implemented.
- No notification listener or Accessibility service is implemented.
- No phone automation is performed.

The provisioning codec requires a trusted high-entropy bootstrap secret. BLE
device discovery and names are not authentication. Do not enter or send real
Wi-Fi credentials until the complete pairing and transport flow is in place.
The Android unit tests include a fixed envelope produced by the Python
implementation. Run `gradle testDebugUnitTest assembleDebug` from this
directory when Gradle and Android SDK 35 are installed.
