package com.example.remoteterminal

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.termux.view.TerminalView

@Composable
fun TerminalScreen(vm: TerminalViewModel, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().imePadding()) {
        TabBar(vm)

        AndroidView(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            factory = { ctx ->
                TerminalView(ctx, null).apply {
                    setTextSize(vm.fontSizePx)
                    setTerminalViewClient(vm.viewClient)
                    vm.view = this
                    isFocusable = true
                    isFocusableInTouchMode = true
                    requestFocus()
                }
            },
            update = { view ->
                val session = vm.current
                if (session != null && view.currentSession !== session) {
                    view.attachSession(session)
                }
            }
        )

        ExtraKeysBar(vm)
    }
}

@Composable
private fun TabBar(vm: TerminalViewModel) {
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        vm.sessions.forEachIndexed { i, _ ->
            FilterChip(
                selected = i == vm.currentIndex,
                onClick = { vm.currentIndex = i },
                label = { Text("tab ${i + 1}") },
                trailingIcon = {
                    Text(
                        "×",
                        Modifier.padding(start = 6.dp).clickable { vm.closeSession(i) }
                    )
                },
                modifier = Modifier.padding(end = 4.dp)
            )
        }
        IconButton(onClick = { vm.newSession() }) { Text("+") }
    }
}

@Composable
private fun ExtraKeysBar(vm: TerminalViewModel) {
    val keys = listOf(
        "ESC" to "\u001b",
        "TAB" to "\t",
        "↑" to "\u001b[A",
        "↓" to "\u001b[B",
        "←" to "\u001b[D",
        "→" to "\u001b[C",
        "-" to "-",
        "/" to "/",
        "|" to "|",
        "~" to "~",
        "^C" to "\u0003",
        "^D" to "\u0004",
        "^Z" to "\u001a"
    )

    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        FilledTonalButton(
            onClick = { vm.ctrlSticky = !vm.ctrlSticky },
            colors = if (vm.ctrlSticky) ButtonDefaults.filledTonalButtonColors(
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary
            ) else ButtonDefaults.filledTonalButtonColors()
        ) { Text("CTRL") }

        keys.forEach { (label, seq) ->
            OutlinedButton(
                onClick = { vm.sendKey(seq) },
                modifier = Modifier.padding(horizontal = 2.dp),
                contentPadding = PaddingValues(horizontal = 10.dp)
            ) { Text(label) }
        }
    }
}
