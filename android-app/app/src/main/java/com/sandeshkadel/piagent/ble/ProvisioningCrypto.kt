package com.sandeshkadel.piagent.ble

import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.security.SecureRandom
import java.util.Base64
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import org.json.JSONException
import org.json.JSONObject

class WifiCredentials(val ssid: String, val password: String) {
    override fun toString(): String = "WifiCredentials(ssid=$ssid, password=[REDACTED])"

    internal fun validate(): WifiCredentials {
        val ssidBytes = encodeUtf8(ssid)
        val passwordBytes = encodeUtf8(password)
        require(ssidBytes.isNotEmpty() && ssidBytes.size <= 32 && ssid.none { it.code < 32 }) {
            "SSID must be 1-32 UTF-8 bytes with no control characters."
        }
        val rawPsk = password.length == 64 && password.all {
            it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F'
        }
        require(
            (rawPsk || passwordBytes.size in 8..63) && password.none { it.code < 32 },
        ) {
            "Wi-Fi password must be an 8-63 byte passphrase or 64 hex digits."
        }
        return this
    }
}

data class ProvisioningEnvelope(
    val sessionId: UUID,
    val nonce: String,
    val ciphertext: String,
) {
    fun toJson(): String = JSONObject()
        .put("session_id", sessionId.toString())
        .put("nonce", nonce)
        .put("ciphertext", ciphertext)
        .toString()

    companion object {
        fun fromJson(json: String): ProvisioningEnvelope {
            try {
                require(json.toByteArray(StandardCharsets.UTF_8).size <= MAX_ENVELOPE_JSON_BYTES) {
                    "Provisioning envelope is too large."
                }
                val value = JSONObject(json)
                require(value.keys().asSequence().toSet() == setOf("session_id", "nonce", "ciphertext")) {
                    "Provisioning envelope fields are invalid."
                }
                val sessionId = value.get("session_id") as? String
                    ?: throw IllegalArgumentException("Provisioning session ID is invalid.")
                val nonce = value.get("nonce") as? String
                    ?: throw IllegalArgumentException("Provisioning nonce is invalid.")
                val ciphertext = value.get("ciphertext") as? String
                    ?: throw IllegalArgumentException("Provisioning ciphertext is invalid.")
                val nonceBytes = decodeBase64(nonce)
                val ciphertextBytes = decodeBase64(ciphertext)
                require(nonceBytes.size == NONCE_LENGTH && ciphertextBytes.size in TAG_LENGTH_BYTES..MAX_CIPHERTEXT_BYTES) {
                    "Provisioning envelope size is invalid."
                }
                return ProvisioningEnvelope(UUID.fromString(sessionId), nonce, ciphertext)
            } catch (error: JSONException) {
                throw IllegalArgumentException("Provisioning envelope JSON is invalid.", error)
            } catch (error: IllegalArgumentException) {
                throw IllegalArgumentException("Provisioning envelope is invalid.", error)
            }
        }
    }
}

class ProvisioningCrypto(
    bootstrapSecret: ByteArray,
    private val sessionId: UUID,
) {
    private val sessionBytes = uuidBytes(sessionId)
    private val encryptionKey: ByteArray
    private val consumed = AtomicBoolean(false)

    init {
        require(bootstrapSecret.size >= MIN_BOOTSTRAP_SECRET_BYTES) {
            "Provisioning bootstrap secret must be at least 32 bytes."
        }
        encryptionKey = deriveKey(bootstrapSecret, sessionBytes)
    }

    fun seal(credentials: WifiCredentials): ProvisioningEnvelope {
        checkUnused()
        val validCredentials = credentials.validate()
        val nonce = ByteArray(NONCE_LENGTH).also(SecureRandom()::nextBytes)
        val plaintext = JSONObject()
            .put("ssid", validCredentials.ssid)
            .put("password", validCredentials.password)
            .toString()
            .toByteArray(StandardCharsets.UTF_8)
        val ciphertext = cipher(Cipher.ENCRYPT_MODE, nonce).doFinal(plaintext)
        return ProvisioningEnvelope(
            sessionId = sessionId,
            nonce = Base64.getEncoder().encodeToString(nonce),
            ciphertext = Base64.getEncoder().encodeToString(ciphertext),
        )
    }

    fun open(envelope: ProvisioningEnvelope): WifiCredentials {
        checkUnused()
        require(envelope.sessionId == sessionId) { "Provisioning session does not match." }
        val nonce = decodeBase64(envelope.nonce)
        val encrypted = decodeBase64(envelope.ciphertext)
        require(nonce.size == NONCE_LENGTH && encrypted.size in TAG_LENGTH_BYTES..MAX_CIPHERTEXT_BYTES) {
            "Provisioning envelope size is invalid."
        }

        val plaintext = try {
            cipher(Cipher.DECRYPT_MODE, nonce).doFinal(encrypted)
        } catch (error: AEADBadTagException) {
            throw IllegalArgumentException("Provisioning authentication failed.", error)
        }
        val payload = try {
            JSONObject(decodeUtf8(plaintext))
        } catch (error: JSONException) {
            throw IllegalArgumentException("Authenticated provisioning payload is invalid.", error)
        }
        require(payload.keys().asSequence().toSet() == setOf("ssid", "password")) {
            "Authenticated provisioning payload fields are invalid."
        }
        val ssid = payload.get("ssid") as? String
            ?: throw IllegalArgumentException("Authenticated provisioning SSID is invalid.")
        val password = payload.get("password") as? String
            ?: throw IllegalArgumentException("Authenticated provisioning password is invalid.")
        return WifiCredentials(ssid, password).validate()
    }

    private fun cipher(mode: Int, nonce: ByteArray): Cipher =
        Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(mode, SecretKeySpec(encryptionKey, "AES"), GCMParameterSpec(TAG_LENGTH_BITS, nonce))
            updateAAD(sessionBytes)
        }

    private fun checkUnused() {
        check(consumed.compareAndSet(false, true)) {
            "Provisioning session has already been used."
        }
    }

    private fun deriveKey(secret: ByteArray, salt: ByteArray): ByteArray {
        val extract = Mac.getInstance("HmacSHA256")
        extract.init(SecretKeySpec(salt, "HmacSHA256"))
        val pseudorandomKey = extract.doFinal(secret)
        val expand = Mac.getInstance("HmacSHA256")
        expand.init(SecretKeySpec(pseudorandomKey, "HmacSHA256"))
        expand.update(HKDF_INFO)
        expand.update(1.toByte())
        return expand.doFinal().copyOf(KEY_LENGTH_BYTES)
    }

    companion object {
        private const val MIN_BOOTSTRAP_SECRET_BYTES = 32
        private const val KEY_LENGTH_BYTES = 32
        private const val NONCE_LENGTH = 12
        private const val TAG_LENGTH_BITS = 128
        private const val TAG_LENGTH_BYTES = TAG_LENGTH_BITS / 8
        private const val MAX_CIPHERTEXT_BYTES = 6_144
        private const val MAX_ENVELOPE_JSON_BYTES = 8_500
        private val HKDF_INFO = "piagent-ble-provisioning-v1".toByteArray(StandardCharsets.US_ASCII)

        private fun uuidBytes(uuid: UUID): ByteArray =
            ByteBuffer.allocate(16)
                .putLong(uuid.mostSignificantBits)
                .putLong(uuid.leastSignificantBits)
                .array()

        private fun decodeBase64(value: String): ByteArray = try {
            Base64.getDecoder().decode(value)
        } catch (error: IllegalArgumentException) {
            throw IllegalArgumentException("Provisioning base64 is invalid.", error)
        }

        private fun encodeUtf8(value: String): ByteArray = try {
            val encoded = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(java.nio.CharBuffer.wrap(value))
            ByteArray(encoded.remaining()).also(encoded::get)
        } catch (error: CharacterCodingException) {
            throw IllegalArgumentException("Provisioning text is not valid UTF-8.", error)
        }

        private fun decodeUtf8(value: ByteArray): String = try {
            StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(value))
                .toString()
        } catch (error: CharacterCodingException) {
            throw IllegalArgumentException("Authenticated provisioning payload is not valid UTF-8.", error)
        }
    }
}
