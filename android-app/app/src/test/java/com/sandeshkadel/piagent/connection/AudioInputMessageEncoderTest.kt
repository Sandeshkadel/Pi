package com.sandeshkadel.piagent.connection

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class AudioInputMessageEncoderTest {
    @Test
    fun encodesMonoPcmAudioWithProtocolFields() {
        val pcm = byteArrayOf(0, 1, 2, 3)

        val message = JSONObject(AudioInputMessageEncoder.encode(7, pcm))

        assertEquals("audio_chunk", message.getString("type"))
        assertEquals(7, message.getLong("sequence"))
        assertEquals("pcm_s16le", message.getString("format"))
        assertEquals(16_000, message.getInt("sample_rate"))
        assertArrayEquals(pcm, java.util.Base64.getDecoder().decode(message.getString("data")))
    }

    @Test
    fun rejectsInvalidSequenceEmptyOddAndOversizedAudio() {
        assertThrows(IllegalArgumentException::class.java) {
            AudioInputMessageEncoder.encode(-1, byteArrayOf(0, 1))
        }
        assertThrows(IllegalArgumentException::class.java) {
            AudioInputMessageEncoder.encode(0, byteArrayOf())
        }
        assertThrows(IllegalArgumentException::class.java) {
            AudioInputMessageEncoder.encode(0, byteArrayOf(1))
        }
        assertThrows(IllegalArgumentException::class.java) {
            AudioInputMessageEncoder.encode(
                0,
                ByteArray(AudioInputMessageEncoder.MAX_AUDIO_BYTES + 2),
            )
        }
    }

    @Test
    fun encodesExplicitVoiceSessionStartAndStop() {
        val start = JSONObject(
            AudioInputMessageEncoder.encodeVoiceControl(VoiceControlAction.START),
        )
        val stop = JSONObject(
            AudioInputMessageEncoder.encodeVoiceControl(VoiceControlAction.STOP),
        )

        assertEquals("voice_control", start.getString("type"))
        assertEquals("start", start.getString("action"))
        assertEquals("voice_control", stop.getString("type"))
        assertEquals("stop", stop.getString("action"))
    }
}
