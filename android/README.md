# RemoteTerminal

An Android terminal app with local tabs and an optional remote shell server.

- Real PTY sessions via the Termux terminal engine, with xterm-256color, colors, and resize
- Extra-keys bar with sticky CTRL
- Foreground service hosting a WebSocket shell on port 8080
- Token authentication sent as the first WebSocket frame
- `web/index.html`, a browser client using xterm.js

## Requirements

- Android Studio Koala or newer
- JDK 17
- Android device or emulator, API 26 (Android 8.0) or newer

## Build

1. Unzip and open the `RemoteTerminal` folder in Android Studio.
2. Let Gradle sync. Android Studio creates the Gradle wrapper automatically. From the command line, you can also run `gradle wrapper` if you have Gradle installed.
3. Run the `app` configuration on a device.

## Use the remote server

1. Open the app and tap **Start**. Allow notifications when prompted.
2. Tap **Show token** and copy the token.
3. Find the phone's Wi-Fi IP address in Android settings.
4. Open `web/index.html` in a browser on a device on the same network. Enter `ws://<phone-ip>:8080/shell` and the token.

Non-browser clients work too. Connect to `/shell`, send `{"type":"auth","token":"..."}` as the first text frame, then send keystrokes as binary frames and resize as `{"type":"resize","rows":30,"cols":100}`.

## Before you build: verify these against your Termux version

The Termux library API changes between releases. These spots are the most likely to need adjustment:

- `RemotePty.kt`: the signatures of `JNI.createSubprocess(...)` and `JNI.setPtyWindowSize(...)`. Check `JNI.java` in the Termux source for your pinned tag.
- `TerminalClients.kt`: the `TerminalSessionClient` and `TerminalViewClient` interfaces. The compiler reports missing or extra overrides. Add or remove them to match.
- `build.gradle.kts`: the Termux version tag and JitPack coordinates. Check the termux-app releases page.

## Security

- Anyone who has the token and can reach port 8080 gets a shell as the app's user. Treat the token like a password.
- The server listens on all interfaces, so it's reachable from your local network. Use Tailscale or a firewall rule instead of port forwarding on your router. Don't expose it to the internet.
- Plain `ws://` is unencrypted. Use it only on a trusted network, or put the server behind Tailscale, which encrypts traffic. For wider access, add TLS.
- Tap **New token** to invalidate the old token. This restarts the server if it's running.
- The app sandbox limits what the shell can reach. Without root, it can't read other apps' data or most of the system.

## Licensing

The Termux terminal libraries are GPLv3. If you distribute this app, it must comply with GPLv3 and make its source available.

## Project layout

```
app/src/main/java/com/example/remoteterminal/
  MainActivity.kt         UI: server control panel and local terminal
  TerminalScreen.kt       Tabs, terminal view, extra-keys bar
  TerminalViewModel.kt    Local session management
  TerminalClients.kt      Termux callbacks
  RemotePty.kt            PTY wrapper and shell environment
  RemoteShellServer.kt    Ktor WebSocket server with auth
  ShellService.kt         Foreground service that hosts the server
  ServerPrefs.kt          Token generation and storage
web/index.html            Browser client
```
