package com.sandeshkadel.piagent.connection

import java.net.URI
import java.net.URISyntaxException
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONException
import org.json.JSONObject

data class ConnectionState(
    val label: String,
    val detail: String,
    val isConnecting: Boolean = false,
    val isConnected: Boolean = false,
) {
    companion object {
        val Disconnected = ConnectionState(
            label = "Not connected",
            detail = "Connect to your Pi to check the authenticated local channel.",
        )
    }
}

object ConnectionEndpoint {
    fun validate(value: String): URI {
        val uri = try {
            URI(value.trim())
        } catch (_: URISyntaxException) {
            throw IllegalArgumentException("Enter a valid local WebSocket address.")
        }
        val scheme = uri.scheme?.lowercase()
        val host = uri.host?.lowercase()
        require(scheme == "ws" || scheme == "wss") {
            "Address must start with ws:// or wss://."
        }
        require(host != null && isLocalHost(host)) {
            "Use the Pi's private-network address or its .local name."
        }
        require(uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null) {
            "Address must not contain credentials, query parameters, or fragments."
        }
        require(uri.rawPath == "/ws/agent") {
            "Address must end with /ws/agent."
        }
        require(uri.port == -1 || uri.port in 1..65535) {
            "Address port is invalid."
        }
        return uri
    }

    fun validateToken(token: String) {
        require(token.length in 32..512 && token.none { it.isWhitespace() || it.isISOControl() }) {
            "Enter the agent token (32-512 characters, no spaces)."
        }
    }

    private fun isLocalHost(host: String): Boolean {
        if (host == "localhost" || host == "127.0.0.1") return true
        if (host.endsWith(".local")) {
            return host.length <= 253 && host.split('.').all { label ->
                label.isNotEmpty() && label.length <= 63 &&
                    label.first().isAsciiLetterOrDigit() && label.last().isAsciiLetterOrDigit() &&
                    label.all { it.isAsciiLetterOrDigit() || it == '-' }
            }
        }

        val octets = host.split('.')
        if (
            octets.size != 4 ||
            octets.any {
                it.isEmpty() || it.length > 3 ||
                    (it.length > 1 && it.startsWith('0')) || it.any(Char::isDigit).not()
            }
        ) {
            return false
        }
        val address = octets.map {
            it.toIntOrNull()?.takeIf { number -> number in 0..255 } ?: return false
        }
        val first = address[0]
        val second = address[1]
        return first == 10 ||
            first == 127 ||
            (first == 172 && second in 16..31) ||
            (first == 192 && second == 168) ||
            (first == 169 && second == 254)
    }

    private fun Char.isAsciiLetterOrDigit(): Boolean =
        this in 'a'..'z' || this in '0'..'9'
}

class AgentConnectionClient(
    private val onStateChanged: (ConnectionState) -> Unit,
    private val onSpeechReceived: (SpeakMessage) -> Unit = {},
) {
    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .build()
    private val heartbeatExecutor = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "piagent-heartbeat").apply { isDaemon = true }
    }
    private val heartbeatSequence = AtomicLong(0)
    private var socket: WebSocket? = null
    private var heartbeat: ScheduledFuture<*>? = null

    @Synchronized
    fun connect(address: String, token: String) {
        require(socket == null) { "Disconnect before starting another connection." }
        val endpoint = ConnectionEndpoint.validate(address)
        ConnectionEndpoint.validateToken(token)
        onStateChanged(
            ConnectionState(
                label = "Connecting",
                detail = "Opening an authenticated connection to the Pi.",
                isConnecting = true,
            ),
        )

        val request = Request.Builder()
            .url(endpoint.toASCIIString())
            .header("Authorization", "Bearer $token")
            .build()
        socket = client.newWebSocket(request, listener)
    }

    @Synchronized
    fun disconnect() {
        heartbeat?.cancel(false)
        heartbeat = null
        val activeSocket = socket
        socket = null
        activeSocket?.close(1000, "User disconnected")
        onStateChanged(ConnectionState.Disconnected)
    }

    @Synchronized
    fun close() {
        disconnect()
        heartbeatExecutor.shutdownNow()
        client.dispatcher.executorService.shutdownNow()
        client.connectionPool.evictAll()
    }

    @Synchronized
    private fun release(webSocket: WebSocket): Boolean {
        if (socket === webSocket) {
            socket = null
            heartbeat?.cancel(false)
            heartbeat = null
            return true
        }
        return false
    }

    @Synchronized
    private fun handleOpen(webSocket: WebSocket) {
        if (socket !== webSocket) return
        onStateChanged(
            ConnectionState(
                label = "Connected",
                detail = "Authenticated. Checking the Pi heartbeat.",
                isConnected = true,
            ),
        )
        heartbeat?.cancel(false)
        heartbeatSequence.set(0)
        heartbeat = heartbeatExecutor.scheduleAtFixedRate(
            {
                val sequence = heartbeatSequence.incrementAndGet()
                val sent = webSocket.send(
                    JSONObject()
                        .put("type", "heartbeat")
                        .put("sequence", sequence)
                        .toString(),
                )
                if (!sent) handleHeartbeatFailure(webSocket)
            },
            0,
            10,
            TimeUnit.SECONDS,
        )
    }

    @Synchronized
    private fun handleHeartbeatFailure(webSocket: WebSocket) {
        if (!release(webSocket)) return
        webSocket.cancel()
        onStateChanged(
            ConnectionState(
                label = "Disconnected",
                detail = "The Pi connection stopped responding.",
            ),
        )
    }

    @Synchronized
    private fun handleMessage(webSocket: WebSocket, text: String) {
        if (socket !== webSocket) return
        val message = try {
            JSONObject(text)
        } catch (error: JSONException) {
            onStateChanged(
                ConnectionState(
                    label = "Connected",
                    detail = "Pi is connected but returned an invalid heartbeat response.",
                    isConnected = true,
                ),
            )
            return
        }
        val acknowledged = message.optString("type") == "heartbeat_ack" &&
            message.optLong("sequence", -1) in 1..heartbeatSequence.get()
        when (message.optString("type")) {
            "heartbeat_ack" -> {
                if (acknowledged) {
                    onStateChanged(
                        ConnectionState(
                            label = "Connected",
                            detail = "Authenticated; Pi heartbeat is healthy.",
                            isConnected = true,
                        ),
                    )
                }
            }
            "speak" -> {
                val speech = AgentServerMessageParser.parseSpeak(text)
                if (speech == null) {
                    onStateChanged(
                        ConnectionState(
                            label = "Connected",
                            detail = "Pi sent an invalid speech response.",
                            isConnected = true,
                        ),
                    )
                } else {
                    onSpeechReceived(speech)
                }
            }
        }
    }

    @Synchronized
    private fun handleClosing(webSocket: WebSocket, code: Int) {
        if (!release(webSocket)) return
        webSocket.close(code, null)
        onStateChanged(
            ConnectionState(
                label = "Disconnected",
                detail = if (code == 1008) {
                    "Pi rejected the token or connection policy."
                } else {
                    "The Pi closed the connection."
                },
            ),
        )
    }

    @Synchronized
    private fun handleFailure(webSocket: WebSocket, response: Response?) {
        if (!release(webSocket)) return
        val detail = if (response?.code == 403 || response?.code == 401) {
            "Authentication failed. Check the Pi address and agent token."
        } else {
            "Could not reach the Pi. Check that it is online on this network."
        }
        onStateChanged(ConnectionState(label = "Connection failed", detail = detail))
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            handleOpen(webSocket)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            handleMessage(webSocket, text)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            handleClosing(webSocket, code)
        }

        override fun onFailure(webSocket: WebSocket, error: Throwable, response: Response?) {
            handleFailure(webSocket, response)
        }
    }
}
