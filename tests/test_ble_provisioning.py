import base64
import uuid
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.ble.provisioning import (
    ProvisioningAuthenticationError,
    ProvisioningCipher,
    ProvisioningEnvelope,
    WiFiCredentials,
)

BOOTSTRAP_SECRET = b"test-only-bootstrap-secret-with-32-bytes"
PYTHON_CIPHERTEXT = (
    "7gXrauEmCPk8kxvMQ+0Q9T4F6MusY8n9SxolnORqzTatuOjmhz5/T76IHQIxLufe53MToZq4efi1zHECVdCAALWZ"
)


def test_wifi_credentials_validate_ssid_and_redact_password() -> None:
    credentials = WiFiCredentials(ssid="home network", password="test-password")

    assert credentials.password.get_secret_value() == "test-password"
    assert "test-password" not in str(credentials)

    with pytest.raises(ValidationError):
        WiFiCredentials(ssid="x" * 33, password="test-password")
    with pytest.raises(ValidationError):
        WiFiCredentials(ssid="home", password="short")


def test_encrypted_provisioning_round_trip_and_one_time_use() -> None:
    session_id = uuid.uuid4()
    credentials = WiFiCredentials(ssid="test network", password="test-password")
    sender = ProvisioningCipher(BOOTSTRAP_SECRET, session_id)
    receiver = ProvisioningCipher(BOOTSTRAP_SECRET, session_id)

    envelope = sender.seal(credentials)
    decrypted = receiver.open(envelope)

    assert decrypted.ssid == credentials.ssid
    assert decrypted.password.get_secret_value() == "test-password"
    with pytest.raises(ProvisioningAuthenticationError, match="already been used"):
        receiver.open(envelope)
    with pytest.raises(ProvisioningAuthenticationError, match="already been used"):
        sender.seal(credentials)


def test_tampered_ciphertext_is_rejected() -> None:
    session_id = uuid.uuid4()
    envelope = ProvisioningCipher(BOOTSTRAP_SECRET, session_id).seal(
        WiFiCredentials(ssid="test", password="test-password")
    )
    ciphertext = bytearray(base64.b64decode(envelope.ciphertext))
    ciphertext[0] ^= 1
    tampered = ProvisioningEnvelope(
        session_id=session_id,
        nonce=envelope.nonce,
        ciphertext=base64.b64encode(ciphertext).decode("ascii"),
    )

    with pytest.raises(ProvisioningAuthenticationError, match="authentication failed"):
        ProvisioningCipher(BOOTSTRAP_SECRET, session_id).open(tampered)


def test_invalid_envelope_does_not_consume_valid_provisioning_session() -> None:
    session_id = uuid.uuid4()
    envelope = ProvisioningCipher(BOOTSTRAP_SECRET, session_id).seal(
        WiFiCredentials(ssid="test", password="test-password")
    )
    ciphertext = bytearray(base64.b64decode(envelope.ciphertext))
    ciphertext[0] ^= 1
    tampered = ProvisioningEnvelope(
        session_id=session_id,
        nonce=envelope.nonce,
        ciphertext=base64.b64encode(ciphertext).decode("ascii"),
    )
    receiver = ProvisioningCipher(BOOTSTRAP_SECRET, session_id)

    with pytest.raises(ProvisioningAuthenticationError, match="authentication failed"):
        receiver.open(tampered)

    assert receiver.open(envelope).ssid == "test"


def test_invalid_credentials_do_not_consume_sealing_session() -> None:
    session_id = uuid.uuid4()
    sender = ProvisioningCipher(BOOTSTRAP_SECRET, session_id)

    with pytest.raises(ValidationError):
        sender.seal(WiFiCredentials(ssid="test", password="short"))

    envelope = sender.seal(WiFiCredentials(ssid="test", password="test-password"))
    assert envelope.session_id == session_id


def test_envelope_cannot_be_replayed_in_another_session() -> None:
    sender_session = uuid.uuid4()
    envelope = ProvisioningCipher(BOOTSTRAP_SECRET, sender_session).seal(
        WiFiCredentials(ssid="test", password="test-password")
    )
    receiver_session = uuid.uuid4()

    with pytest.raises(ProvisioningAuthenticationError, match="does not match"):
        ProvisioningCipher(BOOTSTRAP_SECRET, receiver_session).open(envelope)


def test_provisioning_rejects_short_bootstrap_secret() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        ProvisioningCipher(b"too-short", uuid.uuid4())


def test_python_envelope_matches_android_interoperability_fixture() -> None:
    session_id = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
    credentials = WiFiCredentials(ssid="test network", password="test-password")

    with patch("app.ble.provisioning.os.urandom", return_value=bytes(range(12))):
        envelope = ProvisioningCipher(BOOTSTRAP_SECRET, session_id).seal(credentials)

    assert envelope.nonce == "AAECAwQFBgcICQoL"
    assert envelope.ciphertext == PYTHON_CIPHERTEXT
