package com.sandeshkadel.piagent.connection

import org.json.JSONException
import org.json.JSONObject

data class SpeakMessage(val text: String, val interrupt: Boolean)

object AgentServerMessageParser {
    fun parseSpeak(payload: String): SpeakMessage? {
        val message = try {
            JSONObject(payload)
        } catch (_: JSONException) {
            return null
        }
        if (message.opt("type") != "speak") return null

        val text = message.opt("text") as? String ?: return null
        val interrupt = message.opt("interrupt") as? Boolean ?: return null
        if (text.isBlank() || text.length > 2_000) return null

        return SpeakMessage(text, interrupt)
    }
}
