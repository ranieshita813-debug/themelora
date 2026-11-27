package com.example.remoteterminal

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.font.FontFamily

class MainActivity : ComponentActivity() {

    private val vm: TerminalViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.fillMaxSize()) {
                        RemotePanel()
                        TerminalScreen(vm, Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

@Composable
private fun RemotePanel() {
    val context = LocalContext.current
    var running by remember { mutableStateOf(false) }
    var token by remember { mutableStateOf(ServerPrefs.token(context)) }
    var showToken by remember { mutableStateOf(false) }

    val notifPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) {
        ShellService.start(context)
        running = true
    }

    Column(Modifier.fillMaxWidth().padding(12.dp)) {
        Text(
            text = if (running) "Remote server: running on port ${ShellService.PORT}"
            else "Remote server: stopped",
            style = MaterialTheme.typography.titleMedium
        )
        Text(
            text = "Connect to ws://<phone-ip>:${ShellService.PORT}/shell",
            style = MaterialTheme.typography.bodySmall
        )

        if (showToken) {
            Text(
                text = token,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(vertical = 6.dp)
            )
        }

        Row(Modifier.padding(top = 6.dp)) {
            if (!running) {
                Button(onClick = {
                    if (Build.VERSION.SDK_INT >= 33) {
                        notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        ShellService.start(context)
                        running = true
                    }
                }) { Text("Start") }
            } else {
                Button(onClick = {
                    ShellService.stop(context)
                    running = false
                }) { Text("Stop") }
            }

            OutlinedButton(
                onClick = { showToken = !showToken },
                modifier = Modifier.padding(start = 8.dp)
            ) { Text(if (showToken) "Hide token" else "Show token") }

            OutlinedButton(
                onClick = {
                    token = ServerPrefs.rotate(context)
                    if (running) {
                        ShellService.stop(context)
                        ShellService.start(context)
                    }
                },
                modifier = Modifier.padding(start = 8.dp)
            ) { Text("New token") }
        }
    }
}
