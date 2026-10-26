import json

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from app.core.security import hash_token
from app.main import create_app
from app.server.schemas import IncomingMessage
from app.server.websocket import MessageHandler

TEST_TOKEN = "test-token-with-at-least-thirty-two-characters"


def _client(
    handler: MessageHandler | None = None,
) -> TestClient:
    factory = (lambda: handler) if handler is not None else None
    return TestClient(
        create_app(
            message_handler_factory=factory,
            token_hash=hash_token(TEST_TOKEN),
        )
    )


def _headers(token: str = TEST_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_websocket_rejects_invalid_token() -> None:
    with _client() as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/agent", headers=_headers("x" * 40)):
                pytest.fail("An invalid token must not establish a WebSocket.")


def test_websocket_rejects_missing_token() -> None:
    with _client() as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/agent"):
                pytest.fail("A missing token must not establish a WebSocket.")


def test_unknown_message_type_returns_protocol_error() -> None:
    with _client() as client:
        with client.websocket_connect("/ws/agent", headers=_headers()) as websocket:
            websocket.send_text('{"type":"made_up"}')
            response = websocket.receive_json()

    assert response == {
        "type": "error",
        "code": "unknown_message_type",
        "message": "Message type is not supported.",
    }


def test_non_string_message_type_returns_error_without_crashing() -> None:
    with _client() as client:
        with client.websocket_connect("/ws/agent", headers=_headers()) as websocket:
            websocket.send_text('{"type":[]}')
            response = websocket.receive_json()
            websocket.send_text('{"type":"heartbeat","sequence":1}')
            heartbeat = websocket.receive_json()

    assert response["code"] == "unknown_message_type"
    assert heartbeat == {"type": "heartbeat_ack", "sequence": 1}


def test_invalid_json_returns_protocol_error() -> None:
    with _client() as client:
        with client.websocket_connect("/ws/agent", headers=_headers()) as websocket:
            websocket.send_text("{")
            response = websocket.receive_json()

    assert response["type"] == "error"
    assert response["code"] == "invalid_json"


def test_heartbeat_returns_matching_acknowledgement() -> None:
    with _client() as client:
        with client.websocket_connect("/ws/agent", headers=_headers()) as websocket:
            websocket.send_text('{"type":"heartbeat","sequence":17}')
            response = websocket.receive_json()

    assert response == {"type": "heartbeat_ack", "sequence": 17}


def test_valid_command_is_validated_then_dispatched() -> None:
    received: list[IncomingMessage] = []

    async def handler(websocket: WebSocket, message: IncomingMessage) -> bool:
        received.append(message)
        return True

    with _client(handler) as client:
        with client.websocket_connect("/ws/agent", headers=_headers()) as websocket:
            websocket.send_text(
                json.dumps({"type": "command", "text": "Open YouTube", "source": "voice"})
            )
            response = websocket.receive_json()

    assert response == {"type": "accepted", "message_type": "command"}
    assert len(received) == 1
    assert received[0].type == "command"


def test_valid_message_is_not_reported_as_accepted_without_handler() -> None:
    with _client() as client:
        with client.websocket_connect("/ws/agent", headers=_headers()) as websocket:
            websocket.send_text(
                json.dumps({"type": "command", "text": "Open YouTube", "source": "voice"})
            )
            response = websocket.receive_json()

    assert response["type"] == "error"
    assert response["code"] == "agent_not_ready"


def test_malformed_payload_returns_validation_error() -> None:
    with _client() as client:
        with client.websocket_connect("/ws/agent", headers=_headers()) as websocket:
            websocket.send_text('{"type":"command","text":"","source":"voice"}')
            response = websocket.receive_json()

    assert response["type"] == "error"
    assert response["code"] == "invalid_payload"


def test_invalid_configured_token_hash_fails_fast() -> None:
    with pytest.raises(ValueError, match="AGENT_TOKEN_HASH"):
        create_app(token_hash="not-a-sha256-hash")


def test_blank_environment_hash_disables_websocket_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TOKEN_HASH", "")
    client = TestClient(create_app())

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/agent", headers=_headers()):
            pytest.fail("An unset token hash must not allow a connection.")
