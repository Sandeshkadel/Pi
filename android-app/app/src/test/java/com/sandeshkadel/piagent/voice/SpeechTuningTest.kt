package com.sandeshkadel.piagent.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class SpeechTuningTest {
    @Test
    fun usesNeutralPitchAndSlightlySlowerDefaultRate() {
        val tuning = SpeechTuning()

        assertEquals(SpeechTuning.DEFAULT_PITCH, tuning.pitch)
        assertEquals(SpeechTuning.DEFAULT_RATE, tuning.rate)
    }

    @Test
    fun acceptsValuesAtSupportedBounds() {
        val tuning = SpeechTuning(
            pitch = SpeechTuning.MAX_VALUE,
            rate = SpeechTuning.MIN_VALUE,
        )

        assertEquals(SpeechTuning.MAX_VALUE, tuning.pitch)
        assertEquals(SpeechTuning.MIN_VALUE, tuning.rate)
    }

    @Test
    fun rejectsPitchAndRateOutsideSupportedBounds() {
        assertThrows(IllegalArgumentException::class.java) {
            SpeechTuning(pitch = SpeechTuning.MIN_VALUE - 0.01f)
        }
        assertThrows(IllegalArgumentException::class.java) {
            SpeechTuning(rate = SpeechTuning.MAX_VALUE + 0.01f)
        }
    }
}
