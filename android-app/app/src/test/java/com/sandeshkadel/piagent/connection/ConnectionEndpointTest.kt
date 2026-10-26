package com.sandeshkadel.piagent.connection

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class ConnectionEndpointTest {
    @Test
    fun acceptsLocalPiAddresses() {
        assertEquals(
            "ws://192.168.0.10:8000/ws/agent",
            ConnectionEndpoint.validate(" ws://192.168.0.10:8000/ws/agent ").toString(),
        )
        assertEquals(
            "wss://piagent.local/ws/agent",
            ConnectionEndpoint.validate("wss://piagent.local/ws/agent").toString(),
        )
    }

    @Test
    fun rejectsPublicOrMalformedAddresses() {
        listOf(
            "ws://example.com/ws/agent",
            "ws://8.8.8.8:8000/ws/agent",
            "ws://192.168.0.10:8000/other",
            "http://192.168.0.10:8000/ws/agent",
            "ws://user:pass@192.168.0.10:8000/ws/agent",
            "ws://192.168.0.10:8000/ws/agent?token=secret",
            "ws://192.168.1.999:8000/ws/agent",
            "ws://192.168.001.010:8000/ws/agent",
            "ws://bad host:8000/ws/agent",
        ).forEach { address ->
            assertThrows(IllegalArgumentException::class.java) {
                ConnectionEndpoint.validate(address)
            }
        }
    }

    @Test
    fun validatesTokenWithoutAcceptingWhitespace() {
        ConnectionEndpoint.validateToken("x".repeat(32))
        assertThrows(IllegalArgumentException::class.java) {
            ConnectionEndpoint.validateToken("short")
        }
        assertThrows(IllegalArgumentException::class.java) {
            ConnectionEndpoint.validateToken("x".repeat(31) + " ")
        }
    }
}
