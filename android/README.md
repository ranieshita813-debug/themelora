# RemoteTerminal (no Gradle)

Builds an Android APK with the Android SDK command-line tools only.
No Gradle, no Ktor, no Termux libraries.

## Build
1. Install JDK 17+ and the Android SDK command-line tools.
2. Install the packages: `sdkmanager "platforms;android-34" "build-tools;34.0.0"`
3. Set `ANDROID_HOME` to the SDK folder.
4. Run `./build.sh` (on Windows, use Git Bash or WSL).
5. Install: `adb install -r RemoteTerminal.apk`

## Features
- Start/stop the remote server from the app (foreground service).
- WebSocket shell at `ws://PHONE_IP:8080/shell`, with token auth as the first frame.
- Browser file list and image view at `http://PHONE_IP:8080/files?token=TOKEN`.
- Open `web/index.html` in a browser to get a terminal.

## Limits
- No PTY: `vim`, `top`, and other full-screen programs won't work correctly.
- No terminal resize.
- Plain HTTP and WS are unencrypted. Use only on trusted networks or over Tailscale.
