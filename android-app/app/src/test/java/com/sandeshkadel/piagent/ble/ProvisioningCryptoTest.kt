package com.sandeshkadel.piagent.ble

import java.util.Base64
import java.util.UUID
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class ProvisioningCryptoTest {
    @Test
    fun opensPythonProvisioningEnvelopeFixture() {
        val sessionId = UUID.fromString("00112233-4455-6677-8899-aabbccddeeff")
        val receiver = ProvisioningCrypto(BOOTSTRAP_SECRET, sessionId)

        val credentials = receiver.open(
            ProvisioningEnvelope(
                sessionId = sessionId,
                nonce = "AAECAwQFBgcICQoL",
                ciphertext = PYTHON_CIPHERTEXT,
            ),
        )

        assertEquals("test network", credentials.ssid)
        assertEquals("test-password", credentials.password)
    }

    @Test
    fun sealsEnvelopeThatCanBeParsedBySharedSchema() {
        val sessionId = UUID.randomUUID()
        val sender = ProvisioningCrypto(BOOTSTRAP_SECRET, sessionId)

        val envelope = sender.seal(WifiCredentials("test network", "test-password"))
        val parsed = ProvisioningEnvelope.fromJson(envelope.toJson())

        assertEquals(sessionId, parsed.sessionId)
        assertEquals(12, Base64.getDecoder().decode(parsed.nonce).size)
        assertThrows(IllegalStateException::class.java) {
            sender.seal(WifiCredentials("test", "test-password"))
        }
    }

    @Test
    fun rejectsTamperedEnvelopeAndWrongSession() {
        val sessionId = UUID.fromString("00112233-4455-6677-8899-aabbccddeeff")
        val tamperedCiphertext = Base64.getDecoder().decode(PYTHON_CIPHERTEXT)
            .also { it[0] = (it[0].toInt() xor 1).toByte() }
        val tampered = ProvisioningEnvelope(
            sessionId,
            "AAECAwQFBgcICQoL",
            Base64.getEncoder().encodeToString(tamperedCiphertext),
        )
        assertThrows(IllegalArgumentException::class.java) {
            ProvisioningCrypto(BOOTSTRAP_SECRET, sessionId).open(tampered)
        }

        val foreignSessionEnvelope = tampered.copy(sessionId = UUID.randomUUID())
        assertThrows(IllegalArgumentException::class.java) {
            ProvisioningCrypto(BOOTSTRAP_SECRET, sessionId).open(foreignSessionEnvelope)
        }
    }

    @Test
    fun failedAuthenticationDoesNotConsumeProvisioningSession() {
        val sessionId = UUID.fromString("00112233-4455-6677-8899-aabbccddeeff")
        val receiver = ProvisioningCrypto(BOOTSTRAP_SECRET, sessionId)
        val tamperedCiphertext = Base64.getDecoder().decode(PYTHON_CIPHERTEXT)
            .also { it[0] = (it[0].toInt() xor 1).toByte() }
        val tampered = ProvisioningEnvelope(
            sessionId,
            "AAECAwQFBgcICQoL",
            Base64.getEncoder().encodeToString(tamperedCiphertext),
        )

        assertThrows(IllegalArgumentException::class.java) {
            receiver.open(tampered)
        }

        assertEquals(
            "test network",
            receiver.open(
                ProvisioningEnvelope(
                    sessionId,
                    "AAECAwQFBgcICQoL",
                    PYTHON_CIPHERTEXT,
                ),
            ).ssid,
        )
    }

    @Test
    fun invalidCredentialsDoNotConsumeSealingSession() {
        val sender = ProvisioningCrypto(BOOTSTRAP_SECRET, UUID.randomUUID())
        assertThrows(IllegalArgumentException::class.java) {
            sender.seal(WifiCredentials("test", "short"))
        }

        assertEquals("test network", sender.seal(WifiCredentials("test network", "test-password")).let {
            ProvisioningCrypto(
                BOOTSTRAP_SECRET,
                it.sessionId,
            ).open(it).ssid
        })
    }

    @Test
    fun rejectsInvalidCredentialAndEnvelopeShapes() {
        assertThrows(IllegalArgumentException::class.java) {
            WifiCredentials("x".repeat(33), "test-password").validate()
        }
        assertThrows(IllegalArgumentException::class.java) {
            WifiCredentials("valid", "short").validate()
        }
        assertThrows(IllegalArgumentException::class.java) {
            ProvisioningEnvelope.fromJson(
                """{"session_id":"00112233-4455-6677-8899-aabbccddeeff","nonce":"bad","ciphertext":"bad"}""",
            )
        }
        assertThrows(IllegalArgumentException::class.java) {
            ProvisioningEnvelope.fromJson(
                """{"session_id":"00112233-4455-6677-8899-aabbccddeeff","nonce":"AAECAwQFBgcICQoL","ciphertext":"AA==","extra":true}""",
            )
        }
        assertThrows(IllegalArgumentException::class.java) {
            ProvisioningEnvelope.fromJson(" ".repeat(8_501))
        }
        assertThrows(IllegalArgumentException::class.java) {
            ProvisioningCrypto(ByteArray(31), UUID.randomUUID())
        }
    }

    companion object {
        private val BOOTSTRAP_SECRET = "test-only-bootstrap-secret-with-32-bytes"
            .toByteArray(Charsets.UTF_8)
        private const val PYTHON_CIPHERTEXT =
            "7gXrauEmCPk8kxvMQ+0Q9T4F6MusY8n9SxolnORqzTatuOjmhz5/T76IHQIxLufe53MToZq4efi1zHECVdCAALWZ"
    }
}
