package com.sandeshkadel.piagent.connection

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AgentServerMessageParserTest {
    @Test
    fun parsesValidSpeakMessage() {
        val message = AgentServerMessageParser.parseSpeak(
            """{"type":"speak","text":"Hello there.","interrupt":true}""",
        )

        assertEquals(SpeakMessage("Hello there.", true), message)
    }

    @Test
    fun rejectsInvalidOrUnsupportedSpeechPayloads() {
        assertNull(AgentServerMessageParser.parseSpeak("{"))
        assertNull(AgentServerMessageParser.parseSpeak("""{"type":"listening"}"""))
        assertNull(
            AgentServerMessageParser.parseSpeak(
                """{"type":"speak","text":"Hello","interrupt":"true"}""",
            ),
        )
        assertNull(
            AgentServerMessageParser.parseSpeak(
                """{"type":"speak","text":" ","interrupt":false}""",
            ),
        )
    }

    @Test
    fun rejectsSpeechLongerThanProtocolLimit() {
        val tooLongText = "x".repeat(2_001)
        val payload = """{"type":"speak","text":"$tooLongText","interrupt":false}"""

        assertNull(AgentServerMessageParser.parseSpeak(payload))
    }

    @Test
    fun preservesQueueAndInterruptInstruction() {
        val interrupt = AgentServerMessageParser.parseSpeak(
            """{"type":"speak","text":"Stop and listen.","interrupt":true}""",
        )
        val queued = AgentServerMessageParser.parseSpeak(
            """{"type":"speak","text":"Next response.","interrupt":false}""",
        )

        assertTrue(interrupt!!.interrupt)
        assertFalse(queued!!.interrupt)
    }
}
