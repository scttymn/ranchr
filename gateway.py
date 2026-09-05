#!/usr/bin/env python3
"""Local Herd POC gateway: Herdr Unix socket -> HTTP/SSE + PWA."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import adapters

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
SOCKET_PATH = os.environ.get(
    "HERDR_SOCKET_PATH", str(Path.home() / ".config/herdr/herdr.sock")
)
HOST = os.environ.get("HERD_HOST", "127.0.0.1")
PORT = int(os.environ.get("HERD_PORT", "8787"))
CALL_LOCK = threading.Lock()
HOST_STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "ranchr/host.json"
THEME_NAME_PATH = Path.home() / ".local/state/omarchy/current/theme.name"
THEME_DIR = Path.home() / ".local/state/omarchy/current/theme"
_THEME_LOCK = threading.Lock()
_THEME_CACHE: dict = {"stamp": None, "css": b"", "slug": ""}

THEME_CSS_MAP = """\
  --bg: var(--omarchy-background);
  --bg-deep: var(--omarchy-darker-background);
  --raised: var(--omarchy-lighter-background);
  --raised-2: color-mix(in srgb, var(--omarchy-lighter-background) 82%, var(--omarchy-foreground) 18%);
  --fg: var(--omarchy-foreground);
  --fg-bright: var(--omarchy-bright-foreground);
  --fg-soft: var(--omarchy-light-foreground);
  --muted: var(--omarchy-muted);
  --frame: var(--omarchy-dark-foreground);
  --accent: var(--omarchy-accent, var(--omarchy-blue));
  --accent-bright: color-mix(in srgb, var(--accent) 70%, white);
  --accent-soft: color-mix(in srgb, var(--accent) 42%, var(--omarchy-bright-foreground));
  --green: var(--omarchy-green);
  --green-bright: var(--omarchy-bright-green);
  --green-glow: var(--omarchy-bright-green);
  --cream: var(--omarchy-yellow);
  --cream-bright: var(--omarchy-bright-yellow);
  --cyan: var(--omarchy-cyan);
  --hairline: color-mix(in srgb, var(--omarchy-foreground) 14%, transparent);
  --glass: color-mix(in srgb, var(--omarchy-lighter-background) 78%, transparent);
"""


def theme_slug() -> str:
    try:
        return THEME_NAME_PATH.read_text().strip()
    except Exception:
        return ""


def _theme_stamp() -> tuple:
    latest = 0.0
    for path in (THEME_NAME_PATH, THEME_DIR):
        try:
            latest = max(latest, path.stat().st_mtime)
        except Exception:
            pass
    return (theme_slug(), latest)


def _pretty_theme(slug: str) -> str:
    return re.sub(r"(^|-)([a-z])", lambda m: (" " if m.group(1) else "") + m.group(2).upper(), slug or "Omarchy")


def _build_theme_css() -> bytes:
    slug = theme_slug() or "omarchy"
    lines = [
        f"/* ranch theme {slug} */",
        ":root {",
        f'  --theme-name: "{_pretty_theme(slug)}";',
        f'  --theme-slug: "{slug}";',
    ]
    try:
        proc = subprocess.run(
            ["omarchy-theme-color", "--all"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        raw = proc.stdout or ""
    except Exception:
        raw = ""
    for line in raw.splitlines():
        if "\t" in line:
            key, value = line.split("\t", 1)
        elif "#" in line:
            key, value = line.split("#", 1)
            value = "#" + value
        else:
            continue
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[a-zA-Z0-9_]+", key):
            continue
        if not (value.startswith("#") or value in {"dark", "light"} or value.startswith("rgb")):
            continue
        lines.append(f"  --omarchy-{key.replace('_', '-')}: {value};")
    lines.append(THEME_CSS_MAP.rstrip())
    lines.append("}")
    lines.append("")
    return ("\n".join(lines)).encode()


def theme_css() -> bytes:
    stamp = _theme_stamp()
    with _THEME_LOCK:
        if _THEME_CACHE["css"] and _THEME_CACHE["stamp"] == stamp:
            return _THEME_CACHE["css"]
        css = _build_theme_css()
        if len(css) < 80:
            fallback = APP / "theme.css"
            if fallback.is_file():
                css = fallback.read_bytes()
        _THEME_CACHE["stamp"] = stamp
        _THEME_CACHE["css"] = css
        _THEME_CACHE["slug"] = stamp[0]
        return css


def public_token() -> str:
    try:
        return str(json.loads(HOST_STATE.read_text()).get("token") or "").strip()
    except Exception:
        return ""

KIND_ALIASES = {
    "claude-code": "claude",
    "open-code": "opencode",
    "github-copilot": "copilot",
    "oh-my-pi": "omp",
}


def herdr_call(method: str, params: dict | None = None, timeout: float = 8.0) -> dict:
    payload = {
        "id": uuid.uuid4().hex[:12],
        "method": method,
        "params": params or {},
    }
    raw = (json.dumps(payload) + "\n").encode()
    with CALL_LOCK:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(SOCKET_PATH)
            sock.sendall(raw)
            buf = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("id") == payload["id"]:
                        return msg
        finally:
            sock.close()
    raise TimeoutError(f"no reply for {method}")


def herdr_ok(method: str, params: dict | None = None, timeout: float = 8.0) -> dict:
    msg = herdr_call(method, params, timeout=timeout)
    if "error" in msg:
        err = msg["error"]
        raise RuntimeError(err.get("message") or err.get("code") or "herdr error")
    return msg.get("result") or {}


def ping() -> dict:
    return herdr_ok("ping")


def home_path(path: str | None) -> str:
    if not path:
        return ""
    home = str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        return "~/" + path[len(home) + 1 :]
    return path


def preview_for(pane_id: str, status: str = "") -> str:
    del status
    try:
        result = herdr_ok(
            "agent.read",
            {"target": pane_id, "source": "visible", "lines": 8},
            timeout=3.0,
        )
        text = ((result.get("read") or {}).get("text") or "").strip()
    except Exception:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    # Skip box-drawing chrome; prefer the last readable line.
    useful = [ln for ln in lines if not set(ln) <= set("─│╭╮╰╯┌┐└┘═║╔╗╚╝━┃┏┓┗┛ ")]
    pick = (useful or lines)[-1]
    return pick[:160]


def agents_from_snapshot() -> tuple[list[dict], dict]:
    snap = (herdr_ok("session.snapshot").get("snapshot")) or {}
    workspaces = {w["workspace_id"]: w for w in snap.get("workspaces") or []}
    agents = []
    for agent in snap.get("agents") or []:
        pane_id = agent.get("pane_id")
        ws = workspaces.get(agent.get("workspace_id") or "", {})
        status = agent.get("agent_status") or "unknown"
        agents.append(
            {
                "id": pane_id,
                "agent": agent.get("agent") or "agent",
                "title": agent.get("terminal_title_stripped")
                or agent.get("agent")
                or "agent",
                "status": status,
                "cwd": agent.get("foreground_cwd") or agent.get("cwd") or "",
                "cwd_pretty": home_path(agent.get("foreground_cwd") or agent.get("cwd")),
                "workspace": ws.get("label") or agent.get("workspace_id") or "",
                "workspace_id": agent.get("workspace_id"),
                "tab_id": agent.get("tab_id"),
                "focused": bool(agent.get("focused")),
                "preview": "",
            }
        )
    return agents, snap


def snapshot_herd() -> dict:
    agents, _snap = agents_from_snapshot()
    for agent in agents:
        if agent.get("id") and agent.get("status") != "working":
            agent["preview"] = preview_for(agent["id"], agent.get("status") or "")
    blocked = sum(1 for a in agents if a["status"] == "blocked")
    host = os.environ.get("HERD_NAME") or os.uname().nodename
    default_agent = ""
    agent_file = Path.home() / ".config/omarchy/defaults/agent"
    if agent_file.is_file():
        default_agent = agent_file.read_text().strip()
    return {
        "host": host,
        "default_agent": default_agent,
        "theme": theme_slug(),
        "theme_rev": f"{theme_slug()}:{int(_theme_stamp()[1])}",
        "herdr": True,
        "blocked": blocked,
        "agents": agents,
    }


def pane_pids(pane_id: str) -> list[int]:
    try:
        info = herdr_ok("pane.process_info", {"pane_id": pane_id}, timeout=4.0)
    except Exception:
        return []
    procs = ((info.get("process_info") or {}).get("foreground_processes")) or []
    pids = []
    for proc in procs:
        pid = proc.get("pid")
        if pid:
            pids.append(int(pid))
    return pids


def read_tty(pane_id: str, status: str) -> str:
    # Alternate-screen TUIs (Grok, etc.) reject deep "recent" reads while working.
    source = "visible" if status == "working" else "recent"
    lines = 40 if source == "visible" else 80
    try:
        result = herdr_ok(
            "agent.read",
            {"target": pane_id, "source": source, "lines": lines},
            timeout=4.0,
        )
        return ((result.get("read") or {}).get("text") or "")
    except Exception:
        if source != "visible":
            try:
                result = herdr_ok(
                    "agent.read",
                    {"target": pane_id, "source": "visible", "lines": 40},
                    timeout=3.0,
                )
                return ((result.get("read") or {}).get("text") or "")
            except Exception:
                return ""
        return ""


def read_session(pane_id: str, lines: int = 80) -> dict:
    del lines  # tty depth depends on agent status, not the caller
    agents, _snap = agents_from_snapshot()
    agent = next((a for a in agents if a["id"] == pane_id), None)
    if not agent:
        raise FileNotFoundError(pane_id)
    conv = adapters.conversation(
        agent.get("agent") or "", agent.get("cwd") or "", pane_pids(pane_id)
    )
    if conv.get("title"):
        agent = {**agent, "title": conv["title"]}
    text = read_tty(pane_id, agent.get("status") or "")
    return {
        "agent": agent,
        "text": text,
        "messages": conv.get("messages") or [],
        "adapter": conv.get("adapter"),
        "note": conv.get("note"),
    }


def default_kind() -> str:
    raw = ""
    agent_file = Path.home() / ".config/omarchy/defaults/agent"
    if agent_file.is_file():
        raw = agent_file.read_text().strip()
    return KIND_ALIASES.get(raw, raw or "codex")


def _extract_ids(obj) -> tuple[str | None, str | None, str | None]:
    pane_id = tab_id = workspace_id = None

    def walk(node):
        nonlocal pane_id, tab_id, workspace_id
        if isinstance(node, dict):
            pane_id = pane_id or node.get("pane_id")
            tab_id = tab_id or node.get("tab_id")
            workspace_id = workspace_id or node.get("workspace_id")
            if not pane_id and isinstance(node.get("root_pane"), dict):
                pane_id = node["root_pane"].get("pane_id")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(obj)
    return pane_id, tab_id, workspace_id


def _workspace_for_cwd(cwd: Path, snap: dict) -> str | None:
    want = str(cwd)
    matches: list[tuple[int, str, str]] = []
    for pane in snap.get("panes") or []:
        pane_cwd = pane.get("foreground_cwd") or pane.get("cwd") or ""
        try:
            if pane_cwd and Path(pane_cwd).resolve() == cwd:
                ws = pane.get("workspace_id")
                if ws:
                    matches.append((0, ws, pane.get("workspace_id") or ""))
        except Exception:
            if pane_cwd == want:
                ws = pane.get("workspace_id")
                if ws:
                    matches.append((0, ws, ws))
    labels = {w.get("workspace_id"): (w.get("label") or "") for w in snap.get("workspaces") or []}
    if matches:
        def rank(item):
            ws = item[1]
            label = labels.get(ws, "")
            # Prefer the original space name (Work) over Work-1563.
            return (0 if label == cwd.name else 1, label)

        matches.sort(key=rank)
        return matches[0][1]
    for ws in snap.get("workspaces") or []:
        if (ws.get("label") or "") == cwd.name:
            return ws.get("workspace_id")
    return None


def spawn_agent(cwd: str, kind: str, prompt: str | None) -> dict:
    kind = KIND_ALIASES.get(kind, kind)
    path = Path(cwd).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"not a directory: {cwd}")
    suffix = uuid.uuid4().hex[:4]
    snap = (herdr_ok("session.snapshot").get("snapshot")) or {}
    workspace_id = _workspace_for_cwd(path, snap)
    if workspace_id:
        created = herdr_ok(
            "tab.create",
            {
                "workspace_id": workspace_id,
                "cwd": str(path),
                "label": f"{kind}-{suffix}",
                "focus": True,
            },
            timeout=15.0,
        )
    else:
        created = herdr_ok(
            "workspace.create",
            {"cwd": str(path), "label": path.name, "focus": True},
            timeout=15.0,
        )
    pane_id, tab_id, ws_id = _extract_ids(created)
    workspace_id = workspace_id or ws_id
    if not pane_id and tab_id:
        snap = (herdr_ok("session.snapshot").get("snapshot")) or {}
        for pane in snap.get("panes") or []:
            if pane.get("tab_id") == tab_id:
                pane_id = pane.get("pane_id")
                workspace_id = workspace_id or pane.get("workspace_id")
                break
    if not pane_id:
        raise RuntimeError(f"no pane after spawn: {json.dumps(created)[:400]}")
    start = {"name": f"{kind}-{suffix}", "kind": kind, "pane_id": pane_id}
    if kind == "grok":
        start["args"] = ["--session-id", str(uuid.uuid4())]
    herdr_ok("agent.start", start, timeout=35.0)
    if prompt:
        try:
            herdr_ok("agent.prompt", {"target": pane_id, "text": prompt}, timeout=10.0)
        except RuntimeError as exc:
            if "agent_blocked" not in str(exc):
                raise
    return {
        "id": pane_id,
        "kind": kind,
        "cwd": str(path),
        "workspace_id": workspace_id,
        "name": start["name"],
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP), **kwargs)

    def log_message(self, fmt, *args):
        sys_stderr = __import__("sys").stderr
        sys_stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        origin = (self.headers.get("Origin") or "").strip()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "86400")
            self.send_header("Vary", "Origin")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def _json(self, code: int, body: dict | list):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _err(self, code: int, message: str, extra: dict | None = None):
        payload = {"error": message}
        if extra:
            payload.update(extra)
        self._json(code, payload)

    def _local_host(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "ranchr":
                return value
        return ""

    def _query_token(self) -> str:
        return (parse_qs(urlparse(self.path).query).get("t") or [""])[0]

    def _bearer_token(self) -> str:
        raw = self.headers.get("Authorization") or ""
        kind, _, value = raw.partition(" ")
        if kind.lower() == "bearer":
            return value.strip()
        return ""

    def _authorized(self) -> bool:
        if self._local_host():
            return True
        tok = public_token()
        if not tok:
            return False
        return tok in {self._query_token(), self._cookie_token(), self._bearer_token()}

    def _deny(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._err(401, "gated")
            return
        body = b"<!doctype html><meta charset=utf-8><title>Ranchr</title><p>This ranch is gated. Open the magic link from the widget or your mail.</p>"
        self.send_response(401)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        tok = public_token()
        qtok = self._query_token()
        if tok and qtok == tok and not path.startswith("/api/"):
            self.send_response(302)
            self.send_header("Set-Cookie", f"ranchr={tok}; Path=/; HttpOnly; SameSite=Lax")
            self.send_header("Location", "/")
            self.end_headers()
            return
        if not self._authorized():
            self._deny()
            return
        if path == "/api/health":
            try:
                info = ping()
                self._json(200, {"ok": True, "herdr": info})
            except Exception as exc:
                self._json(503, {"ok": False, "error": str(exc)})
            return
        if path == "/api/herd":
            try:
                self._json(200, snapshot_herd())
            except Exception as exc:
                self._err(502, str(exc))
            return
        if path.startswith("/api/agents/") and path.endswith("/session"):
            pane_id = unquote(path[len("/api/agents/") : -len("/session")])
            try:
                self._json(200, read_session(pane_id))
            except FileNotFoundError:
                self._err(404, "agent not found")
            except Exception as exc:
                self._err(502, str(exc))
            return
        if path == "/api/theme.css":
            css = theme_css()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(css)))
            self.end_headers()
            self.wfile.write(css)
            return
        if path == "/api/events":
            self._sse()
            return
        if path == "/":
            self.path = "/index.html"
        return SimpleHTTPRequestHandler.do_GET(self)

    def _send_file(self, path: Path, content_type: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = None
        last_theme_rev = None
        try:
            while True:
                try:
                    herd = snapshot_herd()
                    blob = json.dumps(herd)
                except Exception as exc:
                    herd = {"error": str(exc), "agents": []}
                    blob = json.dumps(herd)
                if blob != last:
                    self.wfile.write(b"event: herd\n")
                    self.wfile.write(b"data: " + blob.encode() + b"\n\n")
                    last = blob
                rev = (herd or {}).get("theme_rev") or (herd or {}).get("theme") or ""
                if rev and rev != last_theme_rev:
                    payload = json.dumps({
                        "rev": rev,
                        "theme": herd.get("theme") or "",
                        "css": theme_css().decode("utf-8", "replace"),
                    })
                    self.wfile.write(b"event: theme\n")
                    self.wfile.write(b"data: " + payload.encode() + b"\n\n")
                    last_theme_rev = rev
                self.wfile.flush()
                time.sleep(2)
        except BrokenPipeError:
            return

    def do_POST(self):
        if not self._authorized():
            self._deny()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._err(400, "invalid json")
            return
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path.startswith("/api/agents/") and path.endswith("/prompt"):
                pane_id = unquote(path[len("/api/agents/") : -len("/prompt")])
                text = (body.get("text") or "").strip()
                if not text:
                    self._err(400, "empty prompt")
                    return
                if body.get("interject"):
                    try:
                        herdr_ok("agent.focus", {"target": pane_id}, timeout=3.0)
                    except Exception:
                        pass
                    # Grok send-now = Esc:cancel, then the new prompt — not Ctrl+Enter
                    # into a TUI that didn't queue this text.
                    try:
                        herdr_ok(
                            "agent.send_keys",
                            {"target": pane_id, "keys": ["esc"]},
                            timeout=3.0,
                        )
                        time.sleep(0.2)
                    except Exception:
                        pass
                result = herdr_ok(
                    "agent.prompt",
                    {"target": pane_id, "text": text, "wait": None},
                    timeout=6.0,
                )
                self._json(200, {"ok": True, "result": result, "interject": bool(body.get("interject"))})
                return
            if path.startswith("/api/agents/") and path.endswith("/close"):
                pane_id = unquote(path[len("/api/agents/") : -len("/close")])
                herdr_ok("pane.close", {"pane_id": pane_id}, timeout=8.0)
                self._json(200, {"ok": True, "id": pane_id})
                return
            if path.startswith("/api/agents/") and path.endswith("/cancel"):
                pane_id = unquote(path[len("/api/agents/") : -len("/cancel")])
                try:
                    herdr_ok("agent.focus", {"target": pane_id}, timeout=4.0)
                except Exception:
                    pass
                # Grok: Esc:cancel while working. Canonical key name is esc.
                herdr_ok(
                    "agent.send_keys",
                    {"target": pane_id, "keys": ["esc"]},
                    timeout=4.0,
                )
                self._json(200, {"ok": True})
                return
            if path.startswith("/api/agents/") and path.endswith("/approve"):
                pane_id = unquote(path[len("/api/agents/") : -len("/approve")])
                action = body.get("action") or "once"
                if action == "deny":
                    herdr_ok("agent.send_keys", {"target": pane_id, "keys": ["n", "enter"]})
                elif action == "always":
                    herdr_ok("pane.send_text", {"pane_id": pane_id, "text": "always"})
                    herdr_ok("agent.send_keys", {"target": pane_id, "keys": ["enter"]})
                else:
                    herdr_ok("agent.send_keys", {"target": pane_id, "keys": ["y", "enter"]})
                self._json(200, {"ok": True, "action": action})
                return
            if path == "/api/spawn":
                cwd = body.get("cwd") or str(Path.home() / "Work")
                kind = body.get("kind") or default_kind()
                prompt = (body.get("prompt") or "").strip() or None
                self._json(200, spawn_agent(cwd, kind, prompt))
                return
        except RuntimeError as exc:
            msg = str(exc)
            code = 409 if "blocked" in msg else 502
            self._err(code, msg)
            return
        except Exception as exc:
            self._err(500, str(exc))
            return
        self._err(404, "not found")


def main():
    if not APP.is_dir():
        raise SystemExit(f"missing app dir: {APP}")
    sync = ROOT / "sync-theme.sh"
    if sync.is_file():
        subprocess.call([str(sync)], cwd=str(ROOT))
    theme = ROOT / "theme.css"
    if theme.is_file():
        (APP / "theme.css").write_bytes(theme.read_bytes())
    httpd = ThreadingHTTPServer((HOST, PORT), partial(Handler))
    print(f"herd gateway http://{HOST}:{PORT}  herdr={SOCKET_PATH}", flush=True)
    try:
        ping()
        print("herdr: connected", flush=True)
    except Exception as exc:
        print(f"herdr: not connected ({exc})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)


if __name__ == "__main__":
    main()
