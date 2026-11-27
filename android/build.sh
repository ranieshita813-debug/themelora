#!/usr/bin/env bash
# Build RemoteTerminal.apk without Gradle, using Android SDK command-line tools.
# Needs: JDK 17+, Android SDK with build-tools and platforms;android-34, and zip.
set -euo pipefail

: "${ANDROID_HOME:?Set ANDROID_HOME to your Android SDK folder}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
OUT="$ROOT/build"
BT="$(ls -d "$ANDROID_HOME"/build-tools/*/ | sort -V | tail -n 1)"
PLATFORM="$ANDROID_HOME/platforms/android-34/android.jar"
AAPT2="${BT}aapt2"
D8="${BT}d8"
ZIPALIGN="${BT}zipalign"
APKSIGNER="${BT}apksigner"

[ -f "$PLATFORM" ] || { echo "Missing $PLATFORM. Run: sdkmanager 'platforms;android-34'"; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT/classes" "$OUT/dex"

echo "==> 1/5 Linking manifest"
"$AAPT2" link -o "$OUT/app.apk" \
  --manifest "$ROOT/AndroidManifest.xml" \
  -I "$PLATFORM" \
  --min-sdk-version 26 --target-sdk-version 34

echo "==> 2/5 Compiling Java"
mapfile -t SOURCES < <(find "$ROOT/src" -name '*.java')
javac -Xlint:-options -source 8 -target 8 -cp "$PLATFORM" -d "$OUT/classes" "${SOURCES[@]}"

echo "==> 3/5 Converting to DEX"
mapfile -t CLASSES < <(find "$OUT/classes" -name '*.class')
"$D8" --release --min-api 26 --lib "$PLATFORM" --output "$OUT/dex" "${CLASSES[@]}"

echo "==> 4/5 Packaging and aligning"
cp "$OUT/dex/classes.dex" "$OUT/classes.dex"
(cd "$OUT" && zip -q app.apk classes.dex)
"$ZIPALIGN" -f -p 4 "$OUT/app.apk" "$OUT/aligned.apk"

echo "==> 5/5 Signing with a debug key"
KS="$ROOT/debug.keystore"
if [ ! -f "$KS" ]; then
  keytool -genkeypair -keystore "$KS" -storepass android -keypass android \
    -alias debug -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Debug" >/dev/null
fi
"$APKSIGNER" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android \
  --ks-key-alias debug --out "$ROOT/RemoteTerminal.apk" "$OUT/aligned.apk"

echo
echo "Built: $ROOT/RemoteTerminal.apk"
echo "Install: adb install -r RemoteTerminal.apk"
