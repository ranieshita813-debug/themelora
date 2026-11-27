package com.example.remoteterminal

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat

class ShellService : Service() {

    private var server: RemoteShellServer? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        createChannel()
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Remote shell running")
            .setContentText("Listening on port $PORT. Stop it from the app.")
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setOngoing(true)
            .build()
        startForeground(NOTIF_ID, notification)

        if (server == null) {
            try {
                server = RemoteShellServer(
                    token = ServerPrefs.token(this),
                    cwd = filesDir.absolutePath,
                    env = shellEnv(filesDir),
                    port = PORT
                ).also { it.start() }
            } catch (e: Exception) {
                stopSelf()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        server?.stop()
        server = null
        super.onDestroy()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Remote shell", NotificationManager.IMPORTANCE_LOW
            )
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    companion object {
        const val PORT = 8080
        private const val CHANNEL_ID = "remote_shell"
        private const val NOTIF_ID = 1

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, ShellService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, ShellService::class.java))
        }
    }
}
