package com.sandeshkadel.piagent.voice

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class OfflineVoiceSelectorTest {
    @Test
    fun prefersHighestQualityOfflineVoiceForRequestedLanguage() {
        val voices = listOf(
            OfflineVoice("online", "en-US", true, 500, 10),
            OfflineVoice("fast", "en-US", false, 300, 100),
            OfflineVoice("quality", "en-US", false, 500, 100),
            OfflineVoice("other-language", "fr-FR", false, 500, 1),
        )

        assertEquals(
            "quality",
            OfflineVoiceSelector.select(voices, "en-US")?.name,
        )
    }

    @Test
    fun usesLatencyAsTieBreakerAndRejectsMissingLanguage() {
        val voices = listOf(
            OfflineVoice("slow", "en-GB", false, 400, 200),
            OfflineVoice("fast", "en-US", false, 400, 100),
        )

        assertEquals("fast", OfflineVoiceSelector.select(voices, "en")?.name)
        assertNull(OfflineVoiceSelector.select(voices, ""))
    }

    @Test
    fun doesNotSelectNetworkVoices() {
        val voices = listOf(OfflineVoice("cloud", "en-US", true, 500, 1))

        assertNull(OfflineVoiceSelector.select(voices, "en-US"))
    }
}
