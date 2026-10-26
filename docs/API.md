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

Unknown message types, invalid JSON, oversized frames, invalid payloads, and
messages received before the agent handler is configured produce explicit
`error` messages. A syntactically valid command is not proof that an action
was executed.
