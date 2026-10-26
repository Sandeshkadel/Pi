"""Authenticated WebSocket agent channel."""

import json
import logging
import os
from collections.abc import Awaitable, Callable
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.security import is_valid_token_hash, verify_token
from app.server.schemas import (
    INCOMING_MESSAGE_ADAPTER,
    INCOMING_MESSAGE_TYPES,
    Heartbeat,
    HeartbeatAck,
    IncomingMessage,
    MessageAccepted,
    ProtocolError,
)

logger = logging.getLogger(__name__)
MAX_WEBSOCKET_MESSAGE_BYTES = 65_536
MessageHandler = Callable[[WebSocket, IncomingMessage], Awaitable[bool]]
MessageHandlerFactory = Callable[[], MessageHandler]


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        return None
    return token


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json(
        ProtocolError(type="error", code=code, message=message).model_dump(mode="json")
    )


def create_websocket_router(
    token_hash: str | None,
    message_handler_factory: MessageHandlerFactory | None,
) -> APIRouter:
    """Create an agent channel bound to immutable auth and handler settings."""
    if token_hash is not None and not is_valid_token_hash(token_hash):
        raise ValueError("AGENT_TOKEN_HASH must be a lowercase SHA-256 hex digest.")

    router = APIRouter()

    @router.websocket("/ws/agent")
    async def agent_channel(websocket: WebSocket) -> None:
        if token_hash is None:
            logger.error("WebSocket rejected because agent authentication is not configured.")
            await websocket.close(code=1011, reason="Agent authentication is not configured.")
            return

        token = _bearer_token(websocket.headers.get("authorization"))
        if token is None or not verify_token(token, token_hash):
            logger.warning("WebSocket authentication rejected.")
            await websocket.close(code=1008, reason="Invalid credentials.")
            return

        await websocket.accept()
        logger.info("Authenticated agent WebSocket connected.")
        message_handler = (
            message_handler_factory() if message_handler_factory is not None else None
        )
        while True:
            try:
                raw_message = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("Agent WebSocket disconnected.")
                return

            if len(raw_message.encode("utf-8")) > MAX_WEBSOCKET_MESSAGE_BYTES:
                await _send_error(websocket, "payload_too_large", "Message exceeds the size limit.")
                await websocket.close(code=1009, reason="Message exceeds the size limit.")
                return

            try:
                payload: Any = json.loads(raw_message)
            except (JSONDecodeError, RecursionError):
                await _send_error(websocket, "invalid_json", "Message must contain valid JSON.")
                continue

            if not isinstance(payload, dict):
                await _send_error(websocket, "invalid_message", "Message must be a JSON object.")
                continue

            message_type = payload.get("type")
            if not isinstance(message_type, str) or message_type not in INCOMING_MESSAGE_TYPES:
                await _send_error(
                    websocket,
                    "unknown_message_type",
                    "Message type is not supported.",
                )
                continue

            try:
                message = INCOMING_MESSAGE_ADAPTER.validate_json(raw_message)
            except ValidationError:
                await _send_error(
                    websocket,
                    "invalid_payload",
                    "Message payload failed validation.",
                )
                continue

            if isinstance(message, Heartbeat):
                response = HeartbeatAck(type="heartbeat_ack", sequence=message.sequence)
                await websocket.send_json(response.model_dump(mode="json"))
                continue

            if message_handler is None:
                await _send_error(
                    websocket,
                    "agent_not_ready",
                    "The agent message handler is not configured.",
                )
                continue

            handled = await message_handler(websocket, message)
            if not handled:
                await _send_error(
                    websocket,
                    "agent_not_ready",
                    "The agent does not handle this message yet.",
                )
                continue
            accepted = MessageAccepted(type="accepted", message_type=message.type)
            await websocket.send_json(accepted.model_dump(mode="json"))

    return router


def create_agent_router(
    message_handler_factory: MessageHandlerFactory | None = None,
    token_hash: str | None = None,
) -> APIRouter:
    """Resolve configured authentication and create the channel router."""
    configured_hash = (
        token_hash if token_hash is not None else os.getenv("AGENT_TOKEN_HASH") or None
    )
    return create_websocket_router(configured_hash, message_handler_factory)
