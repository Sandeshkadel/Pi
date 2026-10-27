package com.sandeshkadel.piagent.connection

import org.json.JSONObject
import java.util.Base64

object AudioInputMessageEncoder {
    const val SAMPLE_RATE = 16_000
    const val MAX_AUDIO_BYTES = 48_000
    const val FRAME_BYTES = 3_200
    const val FINAL_SILENCE_FRAMES = 12

    fun encode(sequence: Long, pcm: ByteArray): String {
        require(sequence >= 0) { "Audio sequence must not be negative." }
        require(pcm.isNotEmpty() && pcm.size <= MAX_AUDIO_BYTES && pcm.size % 2 == 0) {
            "Audio must contain complete 16-bit samples within the protocol size limit."
        }
        return JSONObject()
            .put("type", "audio_chunk")
            .put("sequence", sequence)
            .put("format", "pcm_s16le")
            .put("sample_rate", SAMPLE_RATE)
            .put("data", Base64.getEncoder().encodeToString(pcm))
            .toString()
    }

    fun finalSilenceFrame(): ByteArray = ByteArray(FRAME_BYTES)
}
