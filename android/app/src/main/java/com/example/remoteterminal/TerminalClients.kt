package com.example.remoteterminal

import android.util.Log
import android.view.KeyEvent
import android.view.MotionEvent
import com.termux.terminal.TerminalSession
import com.termux.terminal.TerminalSessionClient
import com.termux.view.TerminalViewClient

class SessionClient(
    private val onChanged: (TerminalSession) -> Unit,
    private val onFinished: (TerminalSession) -> Unit,
    private val onClipboard: (String) -> Unit,
    private val onPasteRequest: () -> String?
) : TerminalSessionClient {

    override fun onTextChanged(session: TerminalSession) = onChanged(session)
    override fun onTitleChanged(session: TerminalSession) = onChanged(session)
    override fun onSessionFinished(session: TerminalSession) = onFinished(session)
    override fun onCopyTextToClipboard(session: TerminalSession, text: String) = onClipboard(text)
    override fun onPasteTextFromClipboard(session: TerminalSession) {
        onPasteRequest()?.let { session.write(it) }
    }
    override fun onBell(session: TerminalSession) {}
    override fun onColorsChanged(session: TerminalSession) = onChanged(session)
    override fun onTerminalCursorStateChange(enabled: Boolean) {}
    override fun setTerminalShellPid(session: TerminalSession, pid: Int) {}
    override fun getTerminalCursorStyle(): Int? = null

    override fun logError(tag: String, message: String) { Log.e(tag, message) }
    override fun logWarn(tag: String, message: String) { Log.w(tag, message) }
    override fun logInfo(tag: String, message: String) { Log.i(tag, message) }
    override fun logDebug(tag: String, message: String) { Log.d(tag, message) }
    override fun logVerbose(tag: String, message: String) { Log.v(tag, message) }
    override fun logStackTraceWithMessage(tag: String, message: String, e: Exception) { Log.e(tag, message, e) }
    override fun logStackTrace(tag: String, e: Exception) { Log.e(tag, "", e) }
}

class ViewClient(private val vm: TerminalViewModel) : TerminalViewClient {

    override fun onScale(scale: Float): Float {
        vm.adjustFontSize(scale)
        return scale
    }
    override fun onSingleTapUp(e: MotionEvent) {}
    override fun onLongPress(e: MotionEvent): Boolean = false
    override fun shouldBackButtonBeMappedToEscape(): Boolean = false
    override fun shouldEnforceCharBasedInput(): Boolean = true
    override fun shouldUseCtrlSpaceWorkaround(): Boolean = false
    override fun isTerminalViewSelected(): Boolean = true
    override fun copyModeChanged(copyMode: Boolean) {}
    override fun onKeyDown(keyCode: Int, e: KeyEvent, session: TerminalSession): Boolean = false
    override fun onKeyUp(keyCode: Int, e: KeyEvent): Boolean = false
    override fun onCodePoint(codePoint: Int, ctrlDown: Boolean, session: TerminalSession): Boolean = false
    override fun readControlKey(): Boolean = vm.ctrlSticky
    override fun readAltKey(): Boolean = false
    override fun readShiftKey(): Boolean = false
    override fun readFnKey(): Boolean = false

    override fun logError(tag: String, message: String) { Log.e(tag, message) }
    override fun logWarn(tag: String, message: String) { Log.w(tag, message) }
    override fun logInfo(tag: String, message: String) { Log.i(tag, message) }
    override fun logDebug(tag: String, message: String) { Log.d(tag, message) }
    override fun logVerbose(tag: String, message: String) { Log.v(tag, message) }
    override fun logStackTraceWithMessage(tag: String, message: String, e: Exception) { Log.e(tag, message, e) }
    override fun logStackTrace(tag: String, e: Exception) { Log.e(tag, "", e) }
}
