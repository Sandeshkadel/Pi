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
- The token remains in memory only and is not saved by the app.
- View a permission status list. Sensitive permissions are not requested at
  startup; Bluetooth, microphone, notification access, and Accessibility
  remain unrequested until their user-facing features are implemented.

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
- Voice input/output, NotificationListenerService, or Accessibility
  automation.
- Sending commands, notifications, or phone actions. The current connection
  supports authentication and heartbeat only.

The Python and Android provisioning codecs share a cross-language test vector,
but the complete provisioning flow is not ready. Do not enter or transfer real
Wi-Fi credentials. The status dashboard is a separate diagnostic page, not
the Android app or a replacement for its connection UI.
