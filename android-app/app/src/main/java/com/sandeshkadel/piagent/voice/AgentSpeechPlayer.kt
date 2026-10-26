package com.sandeshkadel.piagent.voice

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import java.util.Locale
import java.util.UUID

data class SpeechOutputState(
    val detail: String,
    val voiceName: String? = null,
    val ready: Boolean = false,
) {
    companion object {
        val Initializing = SpeechOutputState("Preparing offline speech.")
    }
}

class AgentSpeechPlayer(
    context: Context,
    private val onStateChanged: (SpeechOutputState) -> Unit,
) {
    private val mainHandler = Handler(Looper.getMainLooper())
    private var textToSpeech: TextToSpeech? = null
    private var selectedVoice: Voice? = null
    private var initialized = false
    private var tuning = SpeechTuning()
    private val pendingSpeech = ArrayDeque<Pair<String, Boolean>>()

    init {
        textToSpeech = TextToSpeech(context) { status ->
            mainHandler.post { finishInitialization(status) }
        }
    }

    fun speak(text: String, interrupt: Boolean) {
        mainHandler.post {
            if (text.isBlank() || text.length > 2_000) {
                onStateChanged(SpeechOutputState("Pi sent text that cannot be spoken."))
                return@post
            }
            val activeVoice = selectedVoice
            val engine = textToSpeech
            if (!initialized) {
                if (interrupt) pendingSpeech.clear()
                if (pendingSpeech.size == MAX_PENDING_SPEECH) pendingSpeech.removeFirst()
                pendingSpeech.addLast(text to interrupt)
                onStateChanged(SpeechOutputState("Offline speech is preparing; response queued."))
                return@post
            }
            if (engine == null || activeVoice == null) {
                onStateChanged(
                    SpeechOutputState(
                        "No offline voice is available. Install an offline voice in Android " +
                            "Text-to-speech settings.",
                    ),
                )
                return@post
            }
            speakNow(engine, text, interrupt)
        }
    }

    fun close() {
        mainHandler.post {
            pendingSpeech.clear()
            textToSpeech?.stop()
            textToSpeech?.shutdown()
            textToSpeech = null
            selectedVoice = null
            initialized = false
        }
    }

    fun stop() {
        mainHandler.post {
            pendingSpeech.clear()
            textToSpeech?.stop()
        }
    }

    fun setTuning(nextTuning: SpeechTuning) {
        mainHandler.post {
            tuning = nextTuning
            val engine = textToSpeech
            if (initialized && engine != null && selectedVoice != null) {
                val applied = applyTuning(engine)
                onStateChanged(
                    SpeechOutputState(
                        detail = if (applied) {
                            "Voice settings applied to the offline phone voice."
                        } else {
                            "The offline speech engine rejected the voice settings; " +
                                "it may use its defaults."
                        },
                        voiceName = selectedVoice?.name,
                        ready = true,
                    ),
                )
            }
        }
    }

    private fun finishInitialization(status: Int) {
        val engine = textToSpeech ?: return
        if (status != TextToSpeech.SUCCESS) {
            initialized = true
            onStateChanged(
                SpeechOutputState(
                    "Offline speech could not initialize. Check the Android text-to-speech engine.",
                ),
            )
            return
        }

        installProgressListener(engine)
        val installedVoices = engine.voices.orEmpty()
        val preferredLanguage = Locale.getDefault().toLanguageTag()
        val descriptors = installedVoices.map { it.toOfflineVoice() }
        val choice = OfflineVoiceSelector.select(descriptors, preferredLanguage)
            ?: OfflineVoiceSelector.select(descriptors, Locale.ENGLISH.toLanguageTag())

        initialized = true
        val voice = choice?.let { selected ->
            installedVoices.firstOrNull { it.name == selected.name }
        }
        if (choice == null || voice == null) {
            pendingSpeech.clear()
            onStateChanged(
                SpeechOutputState(
                    "No offline voice is available for ${Locale.getDefault().displayLanguage}. " +
                        "Install one in Android Text-to-speech settings.",
                ),
            )
            return
        }

        selectedVoice = voice
        engine.voice = voice
        val tuningApplied = applyTuning(engine)
        onStateChanged(
            SpeechOutputState(
                detail = buildString {
                    append(
                        "Using the best-quality installed offline voice for " +
                            "${Locale.forLanguageTag(choice.languageTag).displayLanguage}.",
                    )
                    if (!tuningApplied) {
                        append(" The engine rejected the pitch or rate setting; it may use defaults.")
                    }
                },
                voiceName = choice.name,
                ready = true,
            ),
        )
        while (pendingSpeech.isNotEmpty()) {
            val (text, interrupt) = pendingSpeech.removeFirst()
            speakNow(engine, text, interrupt)
        }
    }

    private fun speakNow(engine: TextToSpeech, text: String, interrupt: Boolean) {
        val queueMode = if (interrupt) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD
        val result = engine.speak(text, queueMode, null, UUID.randomUUID().toString())
        if (result != TextToSpeech.SUCCESS) {
            onStateChanged(SpeechOutputState("The offline speech engine failed to speak."))
        }
    }

    private fun applyTuning(engine: TextToSpeech): Boolean {
        val pitchResult = engine.setPitch(tuning.pitch)
        val rateResult = engine.setSpeechRate(tuning.rate)
        return pitchResult == TextToSpeech.SUCCESS && rateResult == TextToSpeech.SUCCESS
    }

    private fun installProgressListener(engine: TextToSpeech) {
        engine.setOnUtteranceProgressListener(
            object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {
                    updateSpeechState("Speaking with the offline phone voice.", ready = true)
                }

                override fun onDone(utteranceId: String?) {
                    updateSpeechState("Finished speaking with the offline phone voice.", ready = true)
                }

                override fun onError(utteranceId: String?) {
                    updateSpeechState("Offline speech synthesis failed.", ready = false)
                }

                override fun onError(utteranceId: String?, errorCode: Int) {
                    updateSpeechState(
                        "Offline speech synthesis failed (engine error $errorCode).",
                        ready = false,
                    )
                }

                override fun onStop(utteranceId: String?, interrupted: Boolean) {
                    if (!interrupted) {
                        updateSpeechState("Offline speech was stopped by the engine.", ready = true)
                    }
                }
            },
        )
    }

    private fun updateSpeechState(detail: String, ready: Boolean) {
        mainHandler.post {
            onStateChanged(
                SpeechOutputState(
                    detail = detail,
                    voiceName = selectedVoice?.name,
                    ready = ready,
                ),
            )
        }
    }

    private fun Voice.toOfflineVoice() = OfflineVoice(
        name = name,
        languageTag = locale.toLanguageTag(),
        requiresNetwork = isNetworkConnectionRequired,
        quality = quality,
        latency = latency,
    )

    private companion object {
        const val MAX_PENDING_SPEECH = 4
    }
}
