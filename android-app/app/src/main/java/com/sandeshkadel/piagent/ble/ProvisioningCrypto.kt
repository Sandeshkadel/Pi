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

private const val PROVISIONING_NONCE_LENGTH = 12
private const val PROVISIONING_TAG_LENGTH_BITS = 128
private const val PROVISIONING_TAG_LENGTH_BYTES = PROVISIONING_TAG_LENGTH_BITS / 8
private const val PROVISIONING_MAX_CIPHERTEXT_BYTES = 6_144
private const val PROVISIONING_MAX_ENVELOPE_JSON_BYTES = 8_500
private val PROVISIONING_HKDF_INFO =
    "piagent-ble-provisioning-v1".toByteArray(StandardCharsets.US_ASCII)

private fun decodeProvisioningBase64(value: String): ByteArray = try {
    Base64.getDecoder().decode(value).also { decoded ->
        require(Base64.getEncoder().encodeToString(decoded) == value) {
            "Provisioning base64 is not canonical."
        }
    }
} catch (error: IllegalArgumentException) {
    throw IllegalArgumentException("Provisioning base64 is invalid.", error)
}

private fun encodeProvisioningUtf8(value: String): ByteArray = try {
    val encoded = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .encode(java.nio.CharBuffer.wrap(value))
    ByteArray(encoded.remaining()).also(encoded::get)
} catch (error: CharacterCodingException) {
    throw IllegalArgumentException("Provisioning text is not valid UTF-8.", error)
}

private fun decodeProvisioningUtf8(value: ByteArray): String = try {
    StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(value))
        .toString()
} catch (error: CharacterCodingException) {
    throw IllegalArgumentException("Authenticated provisioning payload is not valid UTF-8.", error)
}

class WifiCredentials(val ssid: String, val password: String) {
    override fun toString(): String = "WifiCredentials(ssid=$ssid, password=[REDACTED])"

    internal fun validate(): WifiCredentials {
        val ssidBytes = encodeProvisioningUtf8(ssid)
        val passwordBytes = encodeProvisioningUtf8(password)
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
                require(
                    json.toByteArray(StandardCharsets.UTF_8).size <=
                        PROVISIONING_MAX_ENVELOPE_JSON_BYTES,
                ) {
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
                val nonceBytes = decodeProvisioningBase64(nonce)
                val ciphertextBytes = decodeProvisioningBase64(ciphertext)
                require(
                    nonceBytes.size == PROVISIONING_NONCE_LENGTH &&
                        ciphertextBytes.size in
                        PROVISIONING_TAG_LENGTH_BYTES..PROVISIONING_MAX_CIPHERTEXT_BYTES,
                ) {
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

    @Synchronized
    fun seal(credentials: WifiCredentials): ProvisioningEnvelope {
        checkUnused()
        val validCredentials = credentials.validate()
        val nonce = ByteArray(PROVISIONING_NONCE_LENGTH).also(SecureRandom()::nextBytes)
        val plaintext = JSONObject()
            .put("ssid", validCredentials.ssid)
            .put("password", validCredentials.password)
            .toString()
            .toByteArray(StandardCharsets.UTF_8)
        val ciphertext = cipher(Cipher.ENCRYPT_MODE, nonce).doFinal(plaintext)
        consumed.set(true)
        return ProvisioningEnvelope(
            sessionId = sessionId,
            nonce = Base64.getEncoder().encodeToString(nonce),
            ciphertext = Base64.getEncoder().encodeToString(ciphertext),
        )
    }

    @Synchronized
    fun open(envelope: ProvisioningEnvelope): WifiCredentials {
        checkUnused()
        require(envelope.sessionId == sessionId) { "Provisioning session does not match." }
        val nonce = decodeProvisioningBase64(envelope.nonce)
        val encrypted = decodeProvisioningBase64(envelope.ciphertext)
        require(
            nonce.size == PROVISIONING_NONCE_LENGTH &&
                encrypted.size in PROVISIONING_TAG_LENGTH_BYTES..PROVISIONING_MAX_CIPHERTEXT_BYTES,
        ) {
            "Provisioning envelope size is invalid."
        }

        val plaintext = try {
            cipher(Cipher.DECRYPT_MODE, nonce).doFinal(encrypted)
        } catch (error: AEADBadTagException) {
            throw IllegalArgumentException("Provisioning authentication failed.", error)
        }
        consumed.set(true)
        val payload = try {
            JSONObject(decodeProvisioningUtf8(plaintext))
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
            init(
                mode,
                SecretKeySpec(encryptionKey, "AES"),
                GCMParameterSpec(PROVISIONING_TAG_LENGTH_BITS, nonce),
            )
            updateAAD(sessionBytes)
        }

    private fun checkUnused() {
            check(!consumed.get()) {
            "Provisioning session has already been used."
        }
    }

    private fun deriveKey(secret: ByteArray, salt: ByteArray): ByteArray {
        val extract = Mac.getInstance("HmacSHA256")
        extract.init(SecretKeySpec(salt, "HmacSHA256"))
        val pseudorandomKey = extract.doFinal(secret)
        val expand = Mac.getInstance("HmacSHA256")
        expand.init(SecretKeySpec(pseudorandomKey, "HmacSHA256"))
        expand.update(PROVISIONING_HKDF_INFO)
        expand.update(1.toByte())
        return expand.doFinal().copyOf(KEY_LENGTH_BYTES)
    }

    companion object {
        private const val MIN_BOOTSTRAP_SECRET_BYTES = 32
        private const val KEY_LENGTH_BYTES = 32

        private fun uuidBytes(uuid: UUID): ByteArray =
            ByteBuffer.allocate(16)
                .putLong(uuid.mostSignificantBits)
                .putLong(uuid.leastSignificantBits)
                .array()

    }
}
