# Raspberry Pi Setup

## Status

Deployment scripts and hardware integrations are not part of the initial
skeleton. Do not install services or expose the API to a network until
authentication and deployment hardening are implemented.

## Development run

Install Python 3.11 or newer and create an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 65536
```

The service currently offers a basic dashboard at `/` and a health endpoint
at `/health`. The authenticated WebSocket channel is `/ws/agent`. The health
endpoint does not verify voice hardware, network connectivity, or an AI model.

For local channel testing, generate a random token using a trusted local
terminal (never paste it into chat or source control), save it in the intended
client's secure storage, compute its SHA-256 digest using the command in
[NETWORK.md](NETWORK.md), and set only that digest as `AGENT_TOKEN_HASH` in
`.env`. Start Uvicorn with `--env-file .env`. The example environment leaves
the hash unset so agent connections are rejected by default.

## Before a network deployment

- Configure non-default authentication and verify authorization behavior.
- Restrict network access and use a firewall.
- Store secrets outside source control and rotate any credential that may have
  been exposed.
- Review the security model in [SECURITY.md](SECURITY.md).
