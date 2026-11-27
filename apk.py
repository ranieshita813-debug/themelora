"""Genuinely installable Android APK packaging.

malora now produces real installable APKs by default. The APK contains:

* a real ``classes.dex`` (compiled with ``javac`` then ``d8``/``r8`` from the
  embedded Java source) defining ``com.malora.app.MainActivity``, a launcher
  activity;
* the aarch64 payload ELF stored uncompressed as ``assets/payload``;
* an ``AndroidManifest.xml`` declaring MainActivity as the launcher activity.

On launch, MainActivity extracts ``assets/payload`` into the app's private
``files/`` directory, marks it executable, and runs it directly (no shell).
The payload runs inside Android's application sandbox as the app's UID -- a
stronger boundary than executing shellcode on the host.

Building a real APK requires the Android SDK (build-tools with ``d8``/``r8``,
``apksigner`` and ``zipalign`` plus a platform ``android.jar``) and a JDK
(``javac``, ``keytool``). Set ``ANDROID_SDK_ROOT`` (or ``ANDROID_HOME``) and
keep those tools on ``PATH``. When the toolchain is unavailable, pass
``installable=False`` to get the legacy non-installable placeholder instead.

A real installable APK must be signed; malora generates an ephemeral
self-signed keystore for each build and signs with ``apksigner`` (a caller
supplied keystore may be passed via ``keystore``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from typing import List, Optional, Tuple

from malora.build import build_elf
from malora.constants import DEFAULT_BASE
from malora.errors import MaloraError

PACKAGE_NAME = "com.malora.app"
ASSET_ENTRY = "assets/payload"
DEX_ENTRY = "classes.dex"

MAIN_ACTIVITY_JAVA = r"""package com.malora.app;

import android.app.Activity;
import android.content.res.AssetManager;
import android.os.Bundle;
import android.widget.TextView;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        TextView view = new TextView(this);
        view.setText("malora: preparing payload...");
        setContentView(view);
        try {
            File payload = new File(getFilesDir(), "payload");
            extractAsset("payload", payload);
            payload.setExecutable(true, false);
            Process process =
                Runtime.getRuntime().exec(new String[] { payload.getAbsolutePath() });
            int code = process.waitFor();
            view.setText("malora: payload exited with " + code);
        } catch (Throwable t) {
            view.setText("malora: error: " + t);
        }
    }

    private void extractAsset(String name, File dst) throws IOException {
        AssetManager assets = getAssets();
        InputStream in = null;
        OutputStream out = null;
        try {
            in = assets.open(name);
            out = new FileOutputStream(dst);
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
        } finally {
            if (in != null) {
                in.close();
            }
            if (out != null) {
                out.close();
            }
        }
    }
}
"""

PLACEHOLDER_WARNING = (
    "classes.dex is a placeholder; the APK is a packaging test and will not install as-is"
)

DEFAULT_MIN_SDK = 21
DEFAULT_TARGET_SDK = 34

KEY_ALIAS = "malora"
KEYSTORE_PASS = "android"
KEY_PASS = "android"


@dataclass(frozen=True)
class ApkResult:
    path: str
    size: int
    warnings: Tuple[str, ...] = ()


def apk_name(output: str) -> str:
    """Return output with a .apk extension."""
    return output if output.endswith(".apk") else output + ".apk"


# ---------------------------------------------------------------------------
# Android toolchain location
# ---------------------------------------------------------------------------


_DEFAULT_SDK_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "android-sdk")


def _android_sdk_root() -> str:
    root = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not root:
        root = _DEFAULT_SDK_ROOT
    if not os.path.isdir(root):
        raise MaloraError(
            "installable APKs require ANDROID_SDK_ROOT (or ANDROID_HOME) to point at the Android SDK"
        )
    return root


def _build_tools_dir(sdk_root: str) -> str:
    bt = os.path.join(sdk_root, "build-tools")
    if not os.path.isdir(bt):
        raise MaloraError(
            f"no build-tools directory under {sdk_root}; install Android SDK build-tools"
        )
    versions = sorted(
        (d for d in os.listdir(bt) if os.path.isdir(os.path.join(bt, d))),
        reverse=True,
    )
    if not versions:
        raise MaloraError(f"no build-tools versions found under {bt}")
    return os.path.join(bt, versions[0])


def _locate_tool(tool: str, sdk_root: str) -> Optional[str]:
    """Return the path of a build-tools/JDK tool, or None if not found."""
    bt = _build_tools_dir(sdk_root)
    candidates = [os.path.join(bt, tool), os.path.join(bt, "bin", tool)]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which(tool)


def _require_tool(tool: str, sdk_root: str) -> str:
    path = _locate_tool(tool, sdk_root)
    if path is None:
        raise MaloraError(
            f"required tool '{tool}' not found; install Android SDK build-tools / JDK and "
            f"set ANDROID_SDK_ROOT"
        )
    return path


def _android_jar(sdk_root: str, target_sdk: int) -> str:
    """Return a platform android.jar, preferring the requested target."""
    exact = os.path.join(sdk_root, "platforms", f"android-{target_sdk}", "android.jar")
    if os.path.isfile(exact):
        return exact
    platforms = os.path.join(sdk_root, "platforms")
    candidates: List[str] = []
    if os.path.isdir(platforms):
        for name in os.listdir(platforms):
            jar = os.path.join(platforms, name, "android.jar")
            if os.path.isfile(jar):
                candidates.append(jar)
    if candidates:
        return sorted(candidates)[-1]
    raise MaloraError(
        f"no platform android.jar found under {sdk_root}/platforms; "
        f"install an Android platform or set target_sdk to an installed one"
    )


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _run(cmd: List[str], what: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)  # type: ignore[name-defined]
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise MaloraError(f"{what} failed:\n{detail}")


# ---------------------------------------------------------------------------
# Build steps
# ---------------------------------------------------------------------------


def _vendored_tool(tool: str) -> Optional[str]:
    """Return the path to a vendored build-tools jar/tool, or None."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "vendor", "android-sdk", "build-tools", "37.0.0", tool),
        os.path.join(here, "vendor", "android-sdk", "build-tools", "bin", tool),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _run_d8(args: List[str], what: str) -> None:
    """Run the vendored d8/r8 compiler via the system ``java``."""
    d8_jar = _vendored_tool("d8.jar") or _vendored_tool("r8.jar")
    if d8_jar is None:
        raise MaloraError("vendored d8.jar/r8.jar not found; reinstall malora")
    java = shutil.which("java")
    if java is None:
        raise MaloraError("required tool 'java' not found on PATH; install a JDK")
    main = "com.android.tools.r8.D8" if d8_jar.endswith("d8.jar") else "com.android.tools.r8.R8"
    _run([java, "-cp", d8_jar, main, *args], what)


def _run_apksigner(args: List[str], what: str) -> None:
    """Run the vendored apksigner via the system ``java``."""
    apksigner_jar = _vendored_tool("apksigner.jar")
    if apksigner_jar is None:
        raise MaloraError("vendored apksigner.jar not found; reinstall malora")
    java = shutil.which("java")
    if java is None:
        raise MaloraError("required tool 'java' not found on PATH; install a JDK")
    _run([java, "-jar", apksigner_jar, *args], what)


def _compile_dex(
    java_source: str, out_dir: str, sdk_root: str, target_sdk: int
) -> str:
    """Compile MainActivity.java into classes.dex using javac + d8/r8.

    Uses the d8.jar vendored with malora (``vendor/android-sdk``), so no
    separately installed Android SDK build-tools are required.
    """
    android_jar = _android_jar(sdk_root, target_sdk)
    classes_dir = os.path.join(out_dir, "classes")
    os.makedirs(classes_dir, exist_ok=True)
    java_file = os.path.join(out_dir, "com", "malora", "app", "MainActivity.java")
    os.makedirs(os.path.dirname(java_file), exist_ok=True)
    with open(java_file, "w") as fh:
        fh.write(java_source)

    javac = shutil.which("javac")
    if javac is None:
        raise MaloraError("required tool 'javac' not found on PATH; install a JDK")
    # JDK 9+ pairs --release with an explicit classpath instead of -bootclasspath,
    # which newer JDKs reject when combined with the default release. Use Java 8
    # source level (the Android baseline) with android.jar on the classpath.
    _run(
        [javac, "--release", "8", "-cp", android_jar, "-d", classes_dir, java_file],
        "javac",
    )

    class_file = os.path.join(classes_dir, "com", "malora", "app", "MainActivity.class")

    d8_jar = _vendored_tool("d8.jar") or _vendored_tool("r8.jar")
    if d8_jar is None:
        raise MaloraError("vendored d8.jar/r8.jar not found; reinstall malora")

    dex_out = os.path.join(out_dir, "dex")
    os.makedirs(dex_out, exist_ok=True)
    _run_d8(["--output", dex_out, "--lib", android_jar, class_file], "d8/r8")

    dex = os.path.join(dex_out, "classes.dex")
    if not os.path.isfile(dex):
        raise MaloraError("d8/r8 did not produce classes.dex")
    return dex


def _sign_apk(
    unsigned_apk: str,
    signed_apk: str,
    sdk_root: str,
    keystore: Optional[str],
    min_sdk: int = DEFAULT_MIN_SDK,
) -> None:
    """zipalign (optional) then sign the APK with apksigner.

    Uses the apksigner.jar vendored with malora (``vendor/android-sdk``), so no
    separately installed Android SDK build-tools are required.
    """
    apksigner_jar = _vendored_tool("apksigner.jar")
    if apksigner_jar is None:
        raise MaloraError("vendored apksigner.jar not found; reinstall malora")
    keytool = shutil.which("keytool")
    if keytool is None:
        raise MaloraError("required tool 'keytool' not found on PATH; install a JDK")

    aligned = unsigned_apk
    zipalign = _locate_tool("zipalign", sdk_root)
    if zipalign is not None:
        aligned = signed_apk + ".aligned"
        proc = subprocess.run(
            [zipalign, "-p", "4", unsigned_apk, aligned],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            # zipalign failure is not fatal; fall back to signing unaligned.
            aligned = unsigned_apk

    own_keystore = False
    if keystore is None:
        keystore = tempfile.mktemp(suffix=".jks")
        own_keystore = True
        try:
            _run(
                [
                    keytool,
                    "-genkeypair",
                    "-alias",
                    KEY_ALIAS,
                    "-keystore",
                    keystore,
                    "-storepass",
                    KEYSTORE_PASS,
                    "-keypass",
                    KEY_PASS,
                    "-dname",
                    "CN=malora",
                    "-keyalg",
                    "RSA",
                    "-keysize",
                    "2048",
                    "-validity",
                    "10000",
                ],
                "keytool",
            )
        except BaseException:
            os.remove(keystore)
            raise

    try:
        _run_apksigner(
            [
                "sign",
                "--ks",
                keystore,
                "--ks-pass",
                f"pass:{KEYSTORE_PASS}",
                "--key-pass",
                f"pass:{KEY_PASS}",
                "--ks-key-alias",
                KEY_ALIAS,
                "--min-sdk-version",
                str(min_sdk),
                "--v2-signing-enabled",
                "true",
                "--v3-signing-enabled",
                "true",
                "--out",
                signed_apk,
                aligned,
            ],
            "apksigner",
        )
    finally:
        if own_keystore:
            try:
                os.remove(keystore)
            except OSError:
                pass
        if aligned != unsigned_apk and os.path.exists(aligned):
            try:
                os.remove(aligned)
            except OSError:
                pass


def _write_manifest(workdir: str, min_sdk: int, target_sdk: int) -> str:
    """Write the AndroidManifest.xml to the workdir and return its path."""
    manifest = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<manifest xmlns:android="http://schemas.android.com/apk/res/android"\n'
        f'    package="{PACKAGE_NAME}"\n'
        f'    android:versionCode="1"\n'
        f'    android:versionName="1.0">\n'
        f'    <uses-sdk android:minSdkVersion="{min_sdk}" android:targetSdkVersion="{target_sdk}" />\n'
        f'    <application android:label="malora Payload" android:allowBackup="true" android:theme="@android:style/Theme.Material.Light">\n'
        f'        <activity android:name="com.malora.app.MainActivity" android:exported="true" android:theme="@android:style/Theme.Material.Light">\n'
        f'            <intent-filter>\n'
        f'                <action android:name="android.intent.action.MAIN" />\n'
        f'                <category android:name="android.intent.category.LAUNCHER" />\n'
        f'            </intent-filter>\n'
        f'        </activity>\n'
        f'    </application>\n'
        f'</manifest>\n'
    )
    path = os.path.join(workdir, "AndroidManifest.xml")
    with open(path, "w") as fh:
        fh.write(manifest)
    return path


def _compile_resources(
    manifest_path: str,
    sdk_root: str,
    target_sdk: int,
    out_dir: str,
    min_sdk: int = DEFAULT_MIN_SDK,
) -> str:
    """Compile resources with aapt2 and return the path to the linked unsigned APK.

    Uses aapt2 link to produce a properly structured APK with compiled
    binary XML and resources.arsc instead of hand-written raw XML.
    """
    android_jar = _android_jar(sdk_root, target_sdk)
    os.makedirs(out_dir, exist_ok=True)
    linked_apk = os.path.join(out_dir, "unsigned.apk")

    _run(
        [
            "aapt2",
            "link",
            "-o",
            linked_apk,
            "--manifest",
            manifest_path,
            "-I",
            android_jar,
            "--min-sdk-version",
            str(min_sdk),
        ],
        "aapt2 link",
    )
    return linked_apk


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_apk(
    shellcode: bytes,
    output: str,
    *,
    arch: str = "aarch64",
    add_exit_stub: bool = True,
    installable: bool = True,
    keystore: Optional[str] = None,
    target_sdk: int = DEFAULT_TARGET_SDK,
    min_sdk: int = DEFAULT_MIN_SDK,
) -> ApkResult:
    """Package shellcode as an Android APK.

    When ``installable`` is true (the default) the APK is built from real
    tooling (javac, d8/r8, apksigner), signed, and installable on an Android
    device. Requires ANDROID_SDK_ROOT and a JDK on PATH.

    When ``installable`` is false, a legacy placeholder APK is produced that
    cannot be installed; this is useful for layout tests without the SDK.
    """
    if arch != "aarch64":
        raise MaloraError("APK packaging targets aarch64 only; use --arch aarch64")

    path = apk_name(output)
    workdir = tempfile.mkdtemp(prefix="malora_apk_")
    try:
        if installable:
            sdk_root = _android_sdk_root()

            payload = build_elf(
                shellcode,
                os.path.join(workdir, "payload"),
                arch="aarch64",
                base=DEFAULT_BASE,
                add_exit_stub=add_exit_stub,
            )
            with open(payload.path, "rb") as fh:
                payload_bytes = fh.read()

            dex = _compile_dex(
                MAIN_ACTIVITY_JAVA,
                os.path.join(workdir, "java"),
                sdk_root,
                target_sdk,
            )

            manifest_path = _write_manifest(workdir, min_sdk, target_sdk)

            resources_dir = os.path.join(workdir, "res")
            unsigned = _compile_resources(
                manifest_path, sdk_root, target_sdk, resources_dir,
                min_sdk=min_sdk,
            )

            # Add classes.dex and assets/payload into the linked APK.
            signed_unsigned = os.path.join(workdir, "with_dex.apk")
            with zipfile.ZipFile(unsigned, "r") as zin:
                with zipfile.ZipFile(signed_unsigned, "w", zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        zout.writestr(item, zin.read(item.filename))
                    with open(dex, "rb") as fh:
                        zout.writestr(DEX_ENTRY, fh.read())
                    zout.writestr(ASSET_ENTRY, payload_bytes, compress_type=zipfile.ZIP_STORED)

            _sign_apk(signed_unsigned, path, sdk_root, keystore, min_sdk=min_sdk)
            warnings: Tuple[str, ...] = ()
        else:
            # Legacy placeholder: not installable. Kept for layout tests and
            # environments without the Android SDK.
            payload = build_elf(
                shellcode,
                os.path.join(workdir, "payload"),
                arch="aarch64",
                base=DEFAULT_BASE,
                add_exit_stub=add_exit_stub,
            )
            with open(payload.path, "rb") as fh:
                payload_bytes = fh.read()
            placeholder_dex = b"dex\n035\x00" + bytes(104)
            manifest_path = _write_manifest(workdir, min_sdk, target_sdk)
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(manifest_path, "AndroidManifest.xml")
                zf.writestr(DEX_ENTRY, placeholder_dex)
                zf.writestr(ASSET_ENTRY, payload_bytes, compress_type=zipfile.ZIP_STORED)
            warnings = (PLACEHOLDER_WARNING,)
    except BaseException:
        if os.path.exists(path):
            os.remove(path)
        raise
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return ApkResult(path=path, size=os.path.getsize(path), warnings=warnings)
