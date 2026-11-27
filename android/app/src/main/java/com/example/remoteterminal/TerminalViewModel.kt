package com.example.remoteterminal

import android.app.Application
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import com.termux.terminal.TerminalSession
import com.termux.view.TerminalView
import java.io.File

class TerminalViewModel(app: Application) : AndroidViewModel(app) {

    val sessions = mutableStateListOf<TerminalSession>()
    var currentIndex by mutableIntStateOf(0)
    var ctrlSticky by mutableStateOf(false)
    var fontSizePx by mutableIntStateOf(28)

    val current: TerminalSession? get() = sessions.getOrNull(currentIndex)
    var view: TerminalView? = null

    private val home: File = app.filesDir.apply { mkdirs() }
    private val clipboard = app.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    private val env = shellEnv(home)

    val viewClient = ViewClient(this)

    private val sessionClient = SessionClient(
        onChanged = { view?.onScreenUpdated() },
        onFinished = { finished ->
            sessions.remove(finished)
            if (sessions.isEmpty()) newSession()
            currentIndex = currentIndex.coerceIn(0, sessions.lastIndex)
        },
        onClipboard = { text ->
            clipboard.setPrimaryClip(ClipData.newPlainText("terminal", text))
        },
        onPasteRequest = {
            clipboard.primaryClip?.getItemAt(0)?.coerceToText(app)?.toString()
        }
    )

    init {
        newSession()
    }

    fun newSession() {
        val s = TerminalSession(
            "/system/bin/sh", home.absolutePath, arrayOf("-l"), env, 4000, sessionClient
        )
        sessions.add(s)
        currentIndex = sessions.lastIndex
    }

    fun closeSession(index: Int) {
        val s = sessions.getOrNull(index) ?: return
        s.finishIfRunning()
        sessions.removeAt(index)
        if (sessions.isEmpty()) newSession()
        currentIndex = currentIndex.coerceIn(0, sessions.lastIndex)
    }

    fun sendKey(seq: String) {
        current?.write(seq)
        ctrlSticky = false
    }

    fun adjustFontSize(scale: Float) {
        fontSizePx = (fontSizePx * scale).toInt().coerceIn(12, 60)
        view?.setTextSize(fontSizePx)
    }

    override fun onCleared() {
        sessions.forEach { it.finishIfRunning() }
    }
}
