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

Run the one-time setup command on the Pi with its private Wi-Fi address:

```bash
python -m app.setup --host <PI_PRIVATE_IPV4>
```

Add `--start` to start the server immediately after setup. It prints the local
WebSocket address and a cryptographically random token once, and writes only
`AGENT_TOKEN_HASH` to a newly created `.env`. The file is owner-only on POSIX
systems, and setup refuses to overwrite an existing file. On subsequent starts,
the command validates the existing hash and starts the server without printing
the token again.
Save the token in the phone app; the Pi cannot reconstruct it from the hash.
Do not paste the token into chat, source code, shell history, or persistent
logs. An eight-digit value is not accepted as a permanent bearer token because
it can be guessed much more easily than a high-entropy secret.
If the token is lost or exposed, `--rotate` replaces the hash only when `.env`
contains exactly the setup-managed hash line. Use `--rotate --start` to
immediately start the server with the new token; otherwise restart the server
after rotation. The previously issued token is then rejected.

The Android client sends the bearer token in its WebSocket handshake and keeps
it in memory only. Do not expose the current unauthenticated HTTP dashboard to
an untrusted network.

## BLE provisioning status

The backend has strict Wi-Fi credential models and a one-time AES-GCM
provisioning envelope. The envelope uses HKDF-SHA256 with a random session ID
and authenticated additional data; decrypting consumes the session so the same
envelope cannot be replayed. An unauthenticated or tampered envelope does not
consume the session, so a nearby party cannot invalidate a legitimate transfer
by sending garbage first. Failed Wi-Fi credential validation also does not
consume the sender session. Wi-Fi passwords are represented as `SecretStr` and
must never be logged or stored in the agent database.
Receivers must share a `ProvisioningReplayGuard` to reject a replay across
crypto instances. This guard is bounded and process-local; it is not durable
across service restarts. The real BLE service must use a fresh expiring
bootstrap session or durable replay protection before receiving real
credentials. The BLE GATT transport and Wi-Fi connection handoff are still
unimplemented.

The bootstrap secret must be exchanged through a trusted out-of-band channel.
BLE discovery/device names alone do not authenticate a Pi and must not be
treated as a secure key exchange. The Android app has a matching AES-GCM/HKDF envelope codec. A fixed
cross-language test vector checks that it can decrypt a Python-generated
envelope. This verifies the crypto format only; it does not provide the
out-of-band bootstrap secret or complete pairing/transport. The BLE GATT
server/client, user pairing confirmation, and NetworkManager handoff are not
implemented yet. Do not transmit real Wi-Fi credentials until those parts are
implemented and reviewed.
