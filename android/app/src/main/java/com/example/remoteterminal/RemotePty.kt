package com.example.remoteterminal

import android.os.ParcelFileDescriptor
import android.os.Process
import com.termux.terminal.JNI
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream

/** Environment for every shell, local or remote. */
fun shellEnv(home: File): Array<String> = arrayOf(
    "TERM=xterm-256color",
    "HOME=${home.absolutePath}",
    "PATH=/system/bin:/system/xbin:${home.absolutePath}/bin",
    "PREFIX=${home.absolutePath}",
    "LANG=en_US.UTF-8",
    "COLORTERM=truecolor"
)

/**
 * A pseudo-terminal bound to a shell process.
 * Bytes written to [output] go to the shell's stdin; bytes read from [input] are its terminal output.
 */
class RemotePty(
    cwd: String,
    env: Array<String>,
    rows: Int = 40,
    cols: Int = 120
) {
    private val pid = IntArray(1)
    private val fd: Int = JNI.createSubprocess(
        "/system/bin/sh", cwd, arrayOf("-l"), env, pid, rows, cols
    )
    private val pfd = ParcelFileDescriptor.adoptFd(fd)

    val input = FileInputStream(pfd.fileDescriptor)
    val output = FileOutputStream(pfd.fileDescriptor)

    fun resize(rows: Int, cols: Int) {
        JNI.setPtyWindowSize(fd, rows, cols, 0, 0)
    }

    fun close() {
        runCatching { pfd.close() }
        runCatching { Process.killProcess(pid[0]) }
    }
}
