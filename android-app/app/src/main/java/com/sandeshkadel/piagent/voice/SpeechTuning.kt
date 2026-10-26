package com.sandeshkadel.piagent.voice

data class SpeechTuning(
    val pitch: Float = DEFAULT_PITCH,
    val rate: Float = DEFAULT_RATE,
) {
    init {
        require(pitch in MIN_VALUE..MAX_VALUE) {
            "Speech pitch must be between $MIN_VALUE and $MAX_VALUE."
        }
        require(rate in MIN_VALUE..MAX_VALUE) {
            "Speech rate must be between $MIN_VALUE and $MAX_VALUE."
        }
    }

    companion object {
        const val MIN_VALUE = 0.8f
        const val MAX_VALUE = 1.2f
        const val DEFAULT_PITCH = 1.0f
        const val DEFAULT_RATE = 0.95f
    }
}
