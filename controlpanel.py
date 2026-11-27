"""Read-only web control panel for the Malora workbench.

Serves a local HTML dashboard over ``http://127.0.0.1:<port>`` that reflects
live session state.  Intentionally read-only: only GET endpoints (status page
and JSON status API).  No remote build or execute capability, so there is no
remote code execution surface.  Uses only the Python standard library.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional

from malora.session import Session

_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765

_panel: Optional["_ControlPanel"] = None


def panel_url() -> Optional[str]:
    """URL of the running control panel, if any."""
    return _panel.url if _panel is not None else None


def stop_panel() -> None:
    """Stop the running control panel, if any."""
    global _panel
    if _panel is not None:
        _panel.stop()
        _panel = None


def serve(session: Session, port: int = _DEFAULT_PORT) -> str:
    """Start (or return) the read-only control panel URL for *session*."""
    global _panel
    if _panel is not None:
        return _panel.url
    _panel = _ControlPanel(session)
    try:
        url = _panel.start(port)
    except OSError:
        url = _panel.start(0)
    return url


class _ControlPanel:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.server: Optional[ThreadingHTTPServer] = None
        self.url: Optional[str] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, port: int) -> str:
        server = ThreadingHTTPServer((_HOST, port), _make_handler(self))
        host, actual_port = server.server_address
        self.url = f"http://{host}:{actual_port}"
        self.server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="malora-cp", daemon=True
        )
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def snapshot(self) -> Dict[str, object]:
        s = self.session
        return {
            "arch": s.arch,
            "output": s.output,
            "apk": s.apk,
            "installable": s.installable,
            "exit_stub": s.exit_stub,
            "strip": s.strip,
            "format": s.fmt or "auto",
            "badchars": "".join(f"{b:02x}" for b in s.badchars) or "none",
            "last_output": s.last_output or "none",
        }


def _make_handler(panel: _ControlPanel) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MaloraCP/1.0"

        def log_message(self, fmt, *args):  # silence default request logging
            return

        def _send_json(self, code: int, body: Dict[str, object]) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path == "/":
                self._send_html()
            elif self.path == "/api/session":
                self._send_json(200, panel.snapshot())
            else:
                self._send_json(404, {"error": "not found"})

        def _send_html(self) -> None:
            raw = _PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


_PAGE = """<!DOCTYPE html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Malora Control Panel</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    background: #0b0c0c; color: #ececec; font-size: 13px;
  }
  .bar { padding: 12px 16px; border-bottom: 1px solid #1f1f1f; }
  .bar h1 { margin: 0; font-size: 15px; letter-spacing: 0.06em; color: #b8b8b8; }
  .url { font-size: 11px; color: #6f6f6f; margin: 0 16px 12px; word-break: break-all; }
  .url b { color: #b8b8b8; }
  .grid { display: grid; gap: 16px; padding: 0 16px 24px; }
  .card { border: 1px solid #1f1f1f; background: #111313; border-radius: 8px; }
  .card header { padding: 10px 14px; border-bottom: 1px solid #1f1f1f; }
  .card h2 { margin: 0; font-size: 12px; letter-spacing: 0.08em; color: #8f8f8f;
             text-transform: uppercase; }
  .kv { padding: 10px 14px; font-size: 12px; line-height: 1.45; }
  .kv div { display: grid; grid-template-columns: 140px 1fr; gap: 8px 16px; }
  .kv b { color: #a8a8a8; }
  .kv span { color: #d4d4d4; }
  .muted { color: #6f6f6f; }
</style>
<div class="bar"><h1>Malora Control Panel</h1></div>
<p class="url">Open: <b id="url"></b>  <span class="muted">(read-only status)</span></p>
<div class="grid">
  <div class="card">
    <header><h2>Session</h2></header>
    <div class="kv" id="session">
      <div><b>Architecture</b><span id="s-arch">-</span></div>
      <div><b>Output</b><span id="s-output">-</span></div>
      <div><b>APK mode</b><span id="s-apk">-</span></div>
      <div><b>Installable</b><span id="s-installable">-</span></div>
      <div><b>Exit stub</b><span id="s-stub">-</span></div>
      <div><b>Strip</b><span id="s-strip">-</span></div>
      <div><b>Format</b><span id="s-format">-</span></div>
      <div><b>Bad bytes</b><span id="s-badchars">-</span></div>
      <div><b>Last output</b><span id="s-last">-</span></div>
    </div>
  </div>
</div>
<script>
  const base = window.location.origin;
  document.getElementById('url').textContent = base;

  async function refresh() {
    try {
      const r = await fetch(base + '/api/session');
      const s = await r.json();
      for (const [k, v] of Object.entries(s)) {
        const el = document.getElementById('s-' + k);
        if (el) el.textContent = v === 'none' ? 'none' : v;
      }
    } catch (e) {
      // ignore transient fetch errors while server is starting
    }
  }
  refresh();
  setInterval(refresh, 3000);
</script>
"""


class _ControlPanel:  # noqa: F811  (kept for import compatibility; real class above)
    pass
