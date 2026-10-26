# Raspberry Pi Setup

## Status

Deployment scripts, boot-time services, and hardware integrations are not
implemented. The documented LAN connection command is for a trusted,
isolated-network smoke test only; it is not a production deployment.

## Development prerequisites

Install Python 3.11 or newer and create an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
```

## Create the phone connection details

Connect the Pi to the same trusted Wi-Fi network as the phone, then run setup
with the Pi's private Wi-Fi address:

```bash
python -m app.setup --host <PI_PRIVATE_IPV4> --start
```

For example, replace the placeholder with the Pi's actual address in a private
range such as `192.168.x.x`. The command creates a new private `.env`, prints
the WebSocket address and a high-entropy token once, and writes only the
token's SHA-256 hash to the Pi. Run this initial command interactively in a
private terminal; do not redirect its output or start first-run setup under
systemd, because the one-time token is printed to stdout. Enter the printed
address and token in the Android app. The app keeps the token in memory only;
if you need to re-enter it later, keep the one-time token in a secure password
manager. It cannot be recovered from the Pi's hash. Setup refuses to overwrite an existing `.env`;
do not copy `.env.example` to `.env` before running it. If the token is lost
or exposed, rotate it with
`python -m app.setup --host <PI_PRIVATE_IPV4> --rotate --start`, then replace
the token in the phone app. Rotation is limited to the token-only `.env`
created by this command; it refuses to replace custom environment files. On
subsequent starts, run the same `--start` command: it prints the address but
never redisplays the token.

The long-term token is intentionally not eight digits. An eight-digit bearer
token can be guessed and must not authenticate a network connection.

## Run the development service manually

To test only on the Pi itself without the setup launcher, run the service
bound to loopback:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 65536 --env-file .env
```

This loopback-only service cannot connect to a phone over Wi-Fi. For a
connection smoke test on a trusted, isolated Wi-Fi network, bind to the Pi's
private address:

```bash
python -m uvicorn app.main:app --host <PI_PRIVATE_IPV4> --port 8000 --ws-max-size 65536 --env-file .env
```

This exposes unauthenticated dashboard and health routes to that LAN, and
`ws://` does not encrypt the bearer token. Use only on a trusted, isolated
network with firewall restrictions. A production deployment requires TLS and
additional HTTP-route hardening; do not expose this development service to a
public or untrusted network.

The service currently offers a basic dashboard at `/`, a health endpoint at
`/health`, and an authenticated WebSocket at `/ws/agent`. Health reports HTTP
availability only; it does not verify voice hardware, network connectivity,
or an AI model.

## Current integration status

Ollama, speech recognition, speech synthesis, systemd boot startup, BLE
pairing, and phone permission-backed features are not installed or configured
by this setup. Do not treat PiAgent as a ready offline voice agent until these
integrations are implemented and tested on the Pi and intended Android phone.

## Before a network deployment

- Configure non-default authentication and verify authorization behavior.
- Restrict network access and use a firewall.
- Store secrets outside source control and rotate any credential that may have
  been exposed.
- Review the security model in [SECURITY.md](SECURITY.md).
