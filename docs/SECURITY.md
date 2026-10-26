# Security Model

## Safety requirements

- Never store or enter a phone PIN, password, one-time code, or banking
  credential.
- Never bypass Android lock-screen security.
- Do not automatically message unknown contacts, make payments, or delete user
  data.
- Do not send notification content to cloud services.
- Require explicit confirmation for risky actions. High-risk actions may be
  blocked entirely.
- The current default is stricter: every external action requires a
  task-specific spoken confirmation before execution.
- Log external actions without unnecessarily retaining private content.
- Notification history is disabled by default.
- Conversation history is disabled by default; opt-in history is local and
  bounded to a small context window.

## Secrets

Never commit `.env`, credentials, tokens, Wi-Fi configuration, or private
notification content. A value in `.env.example` is illustrative only and is
not a usable secret. Rotate credentials if they have been exposed.

The WebSocket bearer token must be a high-entropy random value of at least 32
characters. An eight-digit number is not a safe long-term access token.
First-run setup displays the strong token once and stores only its SHA-256 hash
on the Pi. Do not print tokens on each service restart or write them to
persistent logs.

## Current limitations

The health endpoint and dashboard are unauthenticated and intended for
loopback-only development. The WebSocket channel requires a bearer token whose
SHA-256 digest is configured on the Pi; it is not enabled until that digest is
set. A WebSocket message handler, BLE provisioning, voice capture, and phone
automation are not implemented yet. Do not expose the development HTTP
endpoints to an untrusted network.

The current BLE envelope primitive requires a trusted out-of-band bootstrap
secret. It is not a complete BLE pairing system; do not use it to provision
real Wi-Fi credentials until the phone/Pi GATT exchange, user confirmation,
and operating-system credential handoff are implemented and tested. A short
pairing code requires a separate authenticated, expiring, and rate-limited
pairing protocol; it must not replace the strong bearer token. The codec's
replay guard is process-local and loses its history on restart; a production
BLE service must rotate/expire bootstrap sessions or persist replay protection.

## Planned permission model

Permission Mode is the default. Low-risk actions may eventually run
automatically. Medium- and high-risk actions require confirmation, and
high-risk actions may be blocked. Every risky action must pass through the
safety manager.
