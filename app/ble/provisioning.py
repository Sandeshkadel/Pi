"""Validated, one-time authenticated encryption for BLE Wi-Fi provisioning."""

import base64
import binascii
import json
import os
import threading
import time
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ProvisioningAuthenticationError(ValueError):
    """Raised when the provisioning envelope is invalid, replayed, or unauthenticated."""


class ProvisioningPayloadError(ValueError):
    """Raised when authenticated provisioning content fails schema validation."""


class ProvisioningReplayGuard:
    """Bounded process-local replay guard shared by all receivers in a service."""

    def __init__(self, max_sessions: int = 4096, ttl_seconds: float = 3600) -> None:
        if max_sessions < 1 or ttl_seconds <= 0:
            raise ValueError("Replay guard limits must be positive.")
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds
        self._consumed: dict[UUID, float] = {}
        self._lock = threading.Lock()

    def consume(self, session_id: UUID) -> None:
        """Record an authenticated session exactly once, failing closed at capacity."""
        now = time.monotonic()
        with self._lock:
            self._consumed = {
                identifier: consumed_at
                for identifier, consumed_at in self._consumed.items()
                if now - consumed_at < self._ttl_seconds
            }
            if session_id in self._consumed:
                raise ProvisioningAuthenticationError(
                    "Provisioning session has already been used."
                )
            if len(self._consumed) >= self._max_sessions:
                raise ProvisioningAuthenticationError(
                    "Provisioning replay guard is full; restart provisioning service."
                )
            self._consumed[session_id] = now


class StrictProvisioningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WiFiCredentials(StrictProvisioningModel):
    ssid: str = Field(min_length=1, max_length=32)
    password: SecretStr

    @field_validator("ssid")
    @classmethod
    def validate_ssid(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 32 or any(ord(character) < 32 for character in value):
            raise ValueError("SSID must be at most 32 UTF-8 bytes with no control characters.")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        is_raw_psk = len(password) == 64 and all(
            character in "0123456789abcdefABCDEF" for character in password
        )
        if not is_raw_psk and not 8 <= len(password.encode("utf-8")) <= 63:
            raise ValueError("Wi-Fi password must be an 8-63 byte passphrase or 64 hex digits.")
        if any(ord(character) < 32 for character in password):
            raise ValueError("Wi-Fi password must not contain control characters.")
        return value


class ProvisioningEnvelope(StrictProvisioningModel):
    session_id: UUID
    nonce: str = Field(min_length=16, max_length=16)
    ciphertext: str = Field(min_length=24, max_length=8_192)

    @field_validator("nonce")
    @classmethod
    def validate_nonce(cls, value: str) -> str:
        try:
            nonce = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Nonce must be valid base64.") from error
        if len(nonce) != 12:
            raise ValueError("AES-GCM nonce must contain exactly 12 bytes.")
        return value

    @field_validator("ciphertext")
    @classmethod
    def validate_ciphertext(cls, value: str) -> str:
        try:
            ciphertext = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("Ciphertext must be valid base64.") from error
        if len(ciphertext) < 16:
            raise ValueError("Ciphertext is missing the AES-GCM authentication tag.")
        return value


class ProvisioningCipher:
    """Use a one-time out-of-band bootstrap secret for one BLE provisioning session.

    The bootstrap secret must be exchanged through a trusted out-of-band channel.
    BLE discovery or a device name alone does not authenticate the Pi.
    """

    def __init__(
        self,
        bootstrap_secret: bytes,
        session_id: UUID,
        replay_guard: ProvisioningReplayGuard | None = None,
    ) -> None:
        if len(bootstrap_secret) < 32:
            raise ValueError("Provisioning bootstrap secret must be at least 32 bytes.")
        self._session_id = session_id
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=session_id.bytes,
            info=b"piagent-ble-provisioning-v1",
        ).derive(bootstrap_secret)
        self._cipher = AESGCM(key)
        self._consumed = False
        self._lock = threading.Lock()
        self._replay_guard = replay_guard

    def seal(self, credentials: WiFiCredentials) -> ProvisioningEnvelope:
        """Encrypt credentials once; callers must not log the returned envelope."""
        with self._lock:
            self._ensure_unused()
            plaintext = json.dumps(
                {
                    "ssid": credentials.ssid,
                    "password": credentials.password.get_secret_value(),
                },
                separators=(",", ":"),
            ).encode("utf-8")
            nonce = os.urandom(12)
            ciphertext = self._cipher.encrypt(nonce, plaintext, self._session_id.bytes)
            envelope = ProvisioningEnvelope(
                session_id=self._session_id,
                nonce=base64.b64encode(nonce).decode("ascii"),
                ciphertext=base64.b64encode(ciphertext).decode("ascii"),
            )
            self._consumed = True
            return envelope

    def open(self, envelope: ProvisioningEnvelope) -> WiFiCredentials:
        """Authenticate and decrypt one envelope, then permanently consume the session."""
        with self._lock:
            self._ensure_unused()
            if self._replay_guard is None:
                raise ProvisioningAuthenticationError(
                    "A shared provisioning replay guard is required."
                )
            if envelope.session_id != self._session_id:
                raise ProvisioningAuthenticationError("Provisioning session does not match.")

            nonce = base64.b64decode(envelope.nonce, validate=True)
            ciphertext = base64.b64decode(envelope.ciphertext, validate=True)
            try:
                plaintext = self._cipher.decrypt(nonce, ciphertext, self._session_id.bytes)
            except InvalidTag as error:
                raise ProvisioningAuthenticationError(
                    "Provisioning authentication failed."
                ) from error
            self._replay_guard.consume(self._session_id)
            self._consumed = True

            try:
                return WiFiCredentials.model_validate_json(plaintext)
            except (json.JSONDecodeError, ValueError) as error:
                raise ProvisioningPayloadError(
                    "Authenticated provisioning payload is invalid."
                ) from error

    def _ensure_unused(self) -> None:
        if self._consumed:
            raise ProvisioningAuthenticationError("Provisioning session has already been used.")
