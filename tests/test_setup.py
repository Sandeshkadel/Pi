import hashlib
import ipaddress
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.security import verify_token
from app.main import create_app
from app.setup import configure_connection, main, validate_pi_host


def test_setup_prints_local_address_and_strong_token_but_stores_only_hash(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"

    assert main(["--host", "192.168.50.2", "--env-file", str(env_file)]) == 0
    output = capsys.readouterr().out
    token_line = next(line for line in output.splitlines() if line.startswith("Access token "))
    token = token_line.rsplit(": ", maxsplit=1)[1]
    stored_hash = env_file.read_text(encoding="utf-8").strip().split("=", maxsplit=1)[1]

    assert "WebSocket address: ws://192.168.50.2:8000/ws/agent" in output
    assert len(token) >= 32
    assert verify_token(token, stored_hash)
    assert token not in env_file.read_text(encoding="utf-8")
    assert stored_hash == hashlib.sha256(token.encode()).hexdigest()
    assert "8-digit" in output


def test_setup_credentials_authenticate_the_agent_websocket(
    tmp_path: Path,
) -> None:
    _, token = configure_connection(tmp_path / ".env", "192.168.50.2", 8000)
    token_hash = (tmp_path / ".env").read_text(encoding="utf-8").strip().split("=", 1)[1]

    with TestClient(create_app(token_hash=token_hash)) as client:
        with client.websocket_connect(
            "/ws/agent",
            headers={"Authorization": f"Bearer {token}"},
        ) as websocket:
            websocket.send_json({"type": "heartbeat", "sequence": 1})
            assert websocket.receive_json() == {
                "type": "heartbeat_ack",
                "sequence": 1,
            }


def test_setup_refuses_to_overwrite_existing_environment_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AGENT_TOKEN_HASH=keep-this-value\n", encoding="utf-8")

    with pytest.raises(SystemExit) as result:
        main(["--host", "192.168.50.2", "--env-file", str(env_file)])

    assert result.value.code == 2
    assert "already exists" in capsys.readouterr().err
    assert env_file.read_text(encoding="utf-8") == "AGENT_TOKEN_HASH=keep-this-value\n"


def test_token_rotation_revokes_old_token_without_showing_it_again(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    _, original_token = configure_connection(env_file, "10.20.30.40", 8000)

    _, replacement_token = configure_connection(
        env_file,
        "10.20.30.40",
        8000,
        rotate=True,
    )
    replacement_hash = env_file.read_text(encoding="utf-8").strip().split("=", maxsplit=1)[1]

    assert replacement_token != original_token
    assert not verify_token(original_token, replacement_hash)
    assert verify_token(replacement_token, replacement_hash)


def test_setup_rotation_reports_that_the_server_must_restart(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = tmp_path / ".env"
    configure_connection(env_file, "10.20.30.40", 8000)

    assert main(
        [
            "--host",
            "10.20.30.40",
            "--env-file",
            str(env_file),
            "--rotate",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "previous token is revoked" in output
    assert "restart the PiAgent service" in output


def test_token_rotation_refuses_env_files_with_other_settings(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AGENT_TOKEN_HASH=" + "a" * 64 + "\nOTHER_SETTING=value\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="token-only"):
        configure_connection(env_file, "10.20.30.40", 8000, rotate=True)

    assert env_file.read_text(encoding="utf-8").endswith("OTHER_SETTING=value\n")


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "8.8.8.8", "172.32.0.1", "192.168.1.1/24", "::1", "piagent.local"],
)
def test_setup_rejects_non_private_ipv4_hosts(host: str) -> None:
    with pytest.raises(ValueError, match="private IPv4"):
        validate_pi_host(host)


def test_setup_accepts_private_ipv4_and_rejects_invalid_port(tmp_path: Path) -> None:
    assert validate_pi_host("10.20.30.40") == "10.20.30.40"
    with pytest.raises(ValueError, match="Port"):
        configure_connection(tmp_path / ".env", "10.20.30.40", 0)
    assert not (tmp_path / ".env").exists()


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX file permission bits are not enforced on Windows.",
)
def test_setup_environment_file_is_owner_only(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    configure_connection(env_file, "10.20.30.40", 8000)
    assert ipaddress.ip_address("10.20.30.40").is_private
    assert env_file.stat().st_mode & 0o777 == 0o600
