# Network

## HTTP

`GET /health` and `GET /` are unauthenticated development endpoints. Bind the
development server to loopback (`127.0.0.1`) and do not expose it to an
untrusted network. Network deployment must restrict access to these endpoints
or add suitable authentication.

## Authenticated WebSocket channel

`/ws/agent` requires an `Authorization: Bearer <token>` header. The Pi reads
only `AGENT_TOKEN_HASH`, a lowercase SHA-256 hex digest, from its environment.
Tokens must contain at least 32 characters. The channel rejects missing or
invalid credentials before accepting the connection; it never accepts tokens
in URLs or logs message content.

Pydantic validates supported client messages: `audio_chunk`, `notification`,
`command`, `action_result`, and `heartbeat`. Server messages include
`listening`, `speak`, `permission_request`, `automation_task`,
`heartbeat_ack`, `accepted`, and `error`. Extra fields are rejected. Audio and
JSON payload sizes are bounded. Unknown types and invalid payloads receive a
protocol error; heartbeat requests receive an acknowledgement with the same
sequence number.

This phase establishes the validated transport only. Until an agent message
handler is connected, valid non-heartbeat messages receive an explicit
`agent_not_ready` error and are not claimed as processed.

### Development token setup

Generate a random token locally and store it only in the intended client-side
secure storage. Do not paste it into chat, source code, or logs. Compute the
hash in a terminal without putting the token in shell history:

```bash
python -c "import hashlib,getpass; print(hashlib.sha256(getpass.getpass('Agent token: ').encode()).hexdigest())"
```

Put only the digest in `.env` as `AGENT_TOKEN_HASH`. Keep `.env` private and
rotate both sides if the token is exposed.

The Android client must send the bearer token in its WebSocket handshake and
store it in platform-protected storage when client authentication is
implemented. Do not expose the current unauthenticated HTTP dashboard to an
untrusted network.

## BLE provisioning status

The backend has strict Wi-Fi credential models and a one-time AES-GCM
provisioning envelope. The envelope uses HKDF-SHA256 with a random session ID
and authenticated additional data; decrypting consumes the session so the same
envelope cannot be replayed. Wi-Fi passwords are represented as `SecretStr`
and must never be logged or stored in the agent database.

The bootstrap secret must be exchanged through a trusted out-of-band channel.
BLE discovery/device names alone do not authenticate a Pi and must not be
treated as a secure key exchange. The Android app has a matching AES-GCM/HKDF envelope codec. A fixed
cross-language test vector checks that it can decrypt a Python-generated
envelope. This verifies the crypto format only; it does not provide the
out-of-band bootstrap secret or complete pairing/transport. The BLE GATT
server/client, user pairing confirmation, and NetworkManager handoff are not
implemented yet. Do not transmit real Wi-Fi credentials until those parts are
implemented and reviewed.
