package com.example.remoteterminal

import io.ktor.server.cio.CIO
import io.ktor.server.engine.EmbeddedServer
import io.ktor.server.engine.embeddedServer
import io.ktor.server.routing.routing
import io.ktor.server.websocket.DefaultWebSocketServerSession
import io.ktor.server.websocket.WebSockets
import io.ktor.server.websocket.webSocket
import io.ktor.websocket.CloseReason
import io.ktor.websocket.Frame
import io.ktor.websocket.close
import io.ktor.websocket.readText
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.security.MessageDigest

/**
 * Protocol:
 *  1. Client connects to ws://host:port/shell
 *  2. First frame must be text: {"type":"auth","token":"..."} within 5 seconds
 *  3. Binary frames are keystrokes; text frames {"type":"resize","rows":N,"cols":N} resize the PTY
 *  4. Server sends binary frames with terminal output
 */
class RemoteShellServer(
    private val token: String,
    private val cwd: String,
    private val env: Array<String>,
    private val port: Int,
    private val host: String = "0.0.0.0"
) {
    private var server: EmbeddedServer<*, *>? = null

    fun start() {
        server = embeddedServer(CIO, port = port, host = host) {
            install(WebSockets) {
                pingPeriodMillis = 20_000
                timeoutMillis = 60_000
                maxFrameSize = 64L * 1024L
            }
            routing {
                webSocket("/shell") { handleSession() }
            }
        }.start(wait = false)
    }

    fun stop() {
        server?.stop(500, 2000)
        server = null
    }

    private suspend fun DefaultWebSocketServerSession.handleSession() {
        val first = withTimeoutOrNull(5_000) { incoming.receive() } as? Frame.Text
        val authorized = first?.let { frame ->
            runCatching { JSONObject(frame.readText()).optString("token") }.getOrNull()
        }?.let { given ->
            // Constant-time comparison
            MessageDigest.isEqual(given.toByteArray(), token.toByteArray())
        } == true

        if (!authorized) {
            close(CloseReason(CloseReason.Codes.VIOLATED_POLICY, "unauthorized"))
            return
        }

        val pty = RemotePty(cwd, env)
        val pump = launch(Dispatchers.IO) {
            try {
                val buf = ByteArray(4096)
                while (true) {
                    val n = pty.input.read(buf)
                    if (n <= 0) break
                    send(Frame.Binary(true, buf.copyOf(n)))
                }
            } catch (_: Exception) {
                // PTY closed, session ending
            }
        }

        try {
            for (frame in incoming) {
                when (frame) {
                    is Frame.Binary -> withContext(Dispatchers.IO) {
                        pty.output.write(frame.readBytes())
                        pty.output.flush()
                    }
                    is Frame.Text -> handleControl(frame.readText(), pty)
                    else -> Unit
                }
            }
        } finally {
            pump.cancel()
            pty.close()
        }
    }

    private fun handleControl(json: String, pty: RemotePty) {
        runCatching {
            val obj = JSONObject(json)
            if (obj.optString("type") == "resize") {
                pty.resize(obj.getInt("rows"), obj.getInt("cols"))
            }
        }
    }
}
