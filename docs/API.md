# API

## Health

`GET /health` returns HTTP 200 when the FastAPI process is available:

```json
{
  "status": "ok",
  "service": "piagent"
}
```

This is a process health check only; it does not verify hardware, models, or
network integrations.

## Dashboard

`GET /` returns the local development dashboard.

## WebSocket

`/ws/agent` accepts WebSocket connections with an `Authorization: Bearer
<token>` handshake header. The Pi verifies the token against
`AGENT_TOKEN_HASH`. See [NETWORK.md](NETWORK.md) for token setup and message
contracts.

Heartbeat request:

```json
{"type":"heartbeat","sequence":17}
```

Response:

```json
{"type":"heartbeat_ack","sequence":17}
```

Explicit phone-microphone sessions use bounded start/stop controls around
`audio_chunk` messages:

```json
{"type":"voice_control","action":"start"}
{"type":"audio_chunk","sequence":0,"format":"pcm_s16le","sample_rate":16000,"data":"..."}
{"type":"voice_control","action":"stop"}
```

The audio `data` value must be valid base64-encoded PCM; see
[NETWORK.md](NETWORK.md) for the frame and model-configuration limits.

Unknown message types, invalid JSON, oversized frames, invalid payloads, and
messages received before the agent handler is configured produce explicit
`error` messages. A syntactically valid command is not proof that an action
was executed.
