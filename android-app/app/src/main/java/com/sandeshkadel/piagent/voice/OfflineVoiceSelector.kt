package com.sandeshkadel.piagent.voice

data class OfflineVoice(
    val name: String,
    val languageTag: String,
    val requiresNetwork: Boolean,
    val quality: Int,
    val latency: Int,
)

object OfflineVoiceSelector {
    fun select(voices: Iterable<OfflineVoice>, languageTag: String): OfflineVoice? {
        val language = languageTag.substringBefore('-').lowercase()
        if (language.isBlank()) return null
        return voices
            .asSequence()
            .filter { !it.requiresNetwork && it.languageTag.substringBefore('-').equals(language, true) }
            .sortedWith(
                compareByDescending<OfflineVoice> { it.quality }
                    .thenBy { it.latency }
                    .thenBy { it.name },
            )
            .firstOrNull()
    }
}
