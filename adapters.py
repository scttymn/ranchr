"""Harness adapters: structured chat, never raw TUI chrome."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote


def conversation(kind: str, cwd: str, pids: list[int]) -> dict:
    kind = (kind or "").lower()
    if kind in {"grok", "grok-build"}:
        found = grok_conversation(cwd, pids)
        if found:
            return found
    if kind in {"claude", "claude-code"}:
        found = claude_conversation(cwd, pids)
        if found:
            return found
    if kind in {"codex", "openai", "openai-codex"}:
        found = codex_conversation(cwd, pids)
        if found:
            return found
        return {
            "adapter": "codex",
            "title": None,
            "messages": [],
            "note": "Waiting for Codex to write this session. Send a message and it will show up here.",
        }
    return {
        "adapter": None,
        "title": None,
        "messages": [],
        "note": f"No chat adapter for {kind or 'this harness'} yet. You can still Send and Stop through Herdr.",
    }


def grok_conversation(cwd: str, pids: list[int]) -> dict | None:
    session_dir = _grok_session_dir(cwd, pids)
    if not session_dir:
        return None
    updates = session_dir / "updates.jsonl"
    if not updates.is_file():
        return None
    title = None
    summary = session_dir / "summary.json"
    if summary.is_file():
        try:
            meta = json.loads(summary.read_text())
            title = meta.get("generated_title") or meta.get("session_summary")
        except json.JSONDecodeError:
            title = None
    messages = _coalesce_grok_updates(updates)
    return {
        "adapter": "grok",
        "title": title,
        "messages": messages,
        "note": None,
        "session_id": session_dir.name,
    }


def claude_conversation(cwd: str, pids: list[int]) -> dict | None:
    path = _claude_jsonl(cwd, pids)
    if not path:
        return None
    messages = _coalesce_claude(path)
    if not messages:
        return None
    return {
        "adapter": "claude",
        "title": None,
        "messages": messages,
        "note": None,
        "session_id": path.stem,
    }


def _codex_home() -> Path:
    return Path.home() / ".codex"


_CODEX_ROLLOUT = re.compile(
    r"^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-"
    r"([0-9a-fA-F-]{36})\.jsonl(?:\.zst)?$"
)
_CODEX_INJECTED = re.compile(r"^<[a-z][A-Za-z0-9_.-]*(?:\s|/?>)")


def _same_cwd(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except Exception:
        return os.path.normpath(left) == os.path.normpath(right)


def _codex_pid_floor(pids: list[int]) -> float | None:
    pidset = {int(p) for p in pids if p}
    starts = [t for t in (_pid_start_epoch(p) for p in pidset) if t]
    if starts:
        return min(starts) - 30
    return None


def _codex_from_sqlite(cwd: str) -> list[Path]:
    db = _codex_home() / "state_5.sqlite"
    if not db.is_file():
        return []
    try:
        import sqlite3

        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT rollout_path, source, cwd, COALESCE(updated_at_ms, recency_at_ms, updated_at * 1000) AS recency "
            "FROM threads WHERE archived IS NOT 1 AND source IN ('cli', 'vscode')"
        ).fetchall()
        con.close()
    except Exception:
        return []
    found: list[tuple[float, Path]] = []
    for path, source, stored_cwd, recency in rows:
        if source not in {"cli", "vscode"}:
            continue
        if not _same_cwd(stored_cwd or "", cwd):
            continue
        rollout = Path(path).expanduser() if path else None
        if not rollout or not rollout.is_file():
            continue
        stamp = (recency or 0) / 1000 if recency else rollout.stat().st_mtime
        found.append((stamp, rollout))
    found.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in found]


def _codex_from_files(cwd: str) -> list[Path]:
    root = _codex_home() / "sessions"
    if not root.is_dir():
        return []
    found: list[tuple[float, Path]] = []
    for path in root.rglob("rollout-*.jsonl"):
        if not _CODEX_ROLLOUT.match(path.name):
            continue
        try:
            first = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
            meta = json.loads(first[0]) if first else {}
        except Exception:
            continue
        payload = meta.get("payload") if isinstance(meta, dict) else {}
        if not isinstance(payload, dict):
            continue
        if payload.get("source") not in {"cli", "vscode"}:
            continue
        if not _same_cwd(payload.get("cwd") or "", cwd):
            continue
        found.append((path.stat().st_mtime, path))
    found.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in found]


def _codex_jsonl(cwd: str, pids: list[int]) -> Path | None:
    if not cwd:
        return None
    paths = _codex_from_sqlite(cwd) or _codex_from_files(cwd)
    if not paths:
        return None
    newest = paths[0]
    floor = _codex_pid_floor(pids)
    if floor is not None:
        if newest.stat().st_mtime < floor:
            return None
        return newest
    if time.time() - newest.stat().st_mtime < 86400:
        return newest
    return None


def _codex_blocks(content) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [part for part in content if isinstance(part, dict)]
    if isinstance(content, dict):
        return [content]
    return []


def _codex_injected(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    if s.startswith("<environment_context"):
        return True
    return bool(_CODEX_INJECTED.match(s))


def _codex_text(content) -> str:
    parts = []
    for block in _codex_blocks(content):
        kind = block.get("type")
        if kind in {"reasoning", "thinking", "encrypted_content"}:
            continue
        if kind not in {"input_text", "output_text", "text", None}:
            continue
        text = (block.get("text") or "").strip()
        if text and not _codex_injected(text):
            parts.append(text)
    return "\n".join(parts).strip()


def _codex_cmd(raw) -> str:
    if isinstance(raw, dict):
        cmd = raw.get("cmd") or raw.get("command") or ""
        if isinstance(cmd, list):
            cmd = " ".join(str(part) for part in cmd)
        return str(cmd or "").replace("\n", " ").strip()
    if not isinstance(raw, str):
        return ""
    match = re.search(r'\bcmd\s*:\s*"((?:\\.|[^"\\])*)"', raw)
    if match:
        return match.group(1).replace("\\n", " ").replace('\\"', '"').strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    return _codex_cmd(parsed)


def _codex_tool_label(payload: dict) -> str:
    kind = payload.get("type") or ""
    name = payload.get("name") or kind or "tool"
    action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
    cmd = _codex_cmd(
        payload.get("arguments")
        or payload.get("input")
        or action
        or ""
    )
    if name in {"exec", "local_shell", "local_shell_call"} or kind == "local_shell_call":
        return f"Bash · {cmd[:72]}" if cmd else "Bash"
    if cmd:
        label = f"{name} · {cmd[:72]}"
        return label
    return str(name)


def _coalesce_codex(path: Path) -> list[dict]:
    messages: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "response_item":
            continue
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        item = payload.get("type")
        if item == "message":
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            text = _codex_text(payload.get("content"))
            if not text:
                continue
            messages.append({"role": "user" if role == "user" else "agent", "text": text})
            continue
        if item in {"function_call", "local_shell_call", "custom_tool_call"}:
            messages.append({"role": "tool", "text": _codex_tool_label(payload)})
    return messages


def codex_conversation(cwd: str, pids: list[int]) -> dict | None:
    path = _codex_jsonl(cwd, pids)
    if not path:
        return None
    messages = _coalesce_codex(path)
    if not messages:
        return None
    title = next((m["text"].splitlines()[0][:80] for m in messages if m["role"] == "user"), None)
    return {
        "adapter": "codex",
        "title": title,
        "messages": messages,
        "note": None,
        "session_id": path.stem,
    }


def _claude_project_dir(cwd: str) -> Path | None:
    if not cwd:
        return None
    try:
        resolved = str(Path(cwd).expanduser().resolve())
    except Exception:
        resolved = cwd
    root = Path.home() / ".claude" / "projects" / resolved.replace("/", "-")
    return root if root.is_dir() else None


def _claude_jsonl(cwd: str, pids: list[int]) -> Path | None:
    root = _claude_project_dir(cwd)
    if not root:
        return None
    files = [p for p in root.glob("*.jsonl") if p.is_file()]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    newest = files[0]
    pidset = {int(p) for p in pids if p}
    starts = [t for t in (_pid_start_epoch(p) for p in pidset) if t]
    if starts:
        if newest.stat().st_mtime < min(starts) - 30:
            return None
        return newest
    if time.time() - newest.stat().st_mtime < 86400:
        return newest
    return None


def _claude_tool_label(part: dict) -> str:
    name = part.get("name") or "tool"
    inp = part.get("input") if isinstance(part.get("input"), dict) else {}
    skill = inp.get("skill")
    if name == "Skill" and skill:
        return f"Skill · {skill}"
    if name == "Bash":
        cmd = (inp.get("command") or "").replace("\n", " ").strip()
        return f"Bash · {cmd[:72]}" if cmd else "Bash"
    detail = (
        inp.get("file_path")
        or inp.get("target_file")
        or inp.get("query")
        or inp.get("pattern")
        or inp.get("url")
        or ""
    )
    if isinstance(detail, str) and len(detail) > 72:
        detail = detail[:69] + "…"
    if detail:
        return f"{name} · {detail}"
    return name


def _claude_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            text = (part.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _coalesce_claude(path: Path) -> list[dict]:
    messages: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("isSidechain"):
            continue
        kind = obj.get("type")
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        if kind == "user":
            human = (obj.get("origin") or {}).get("kind") == "human" or obj.get("promptSource") == "typed"
            if not human:
                continue
            text = _claude_text(msg.get("content"))
            if text:
                messages.append({"role": "user", "text": text})
            continue
        if kind == "assistant":
            text = _claude_text(msg.get("content"))
            tools = []
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "tool_use":
                        tools.append({"role": "tool", "text": _claude_tool_label(part)})
            if text:
                messages.append({"role": "agent", "text": text})
            messages.extend(tools)
    return messages


def _grok_home() -> Path:
    return Path.home() / ".grok"


def _pid_start_epoch(pid: int) -> float | None:
    try:
        hz = os.sysconf("SC_CLK_TCK")
        raw = Path(f"/proc/{pid}/stat").read_text()
        starttime = int(raw[raw.rfind(")") + 2 :].split()[19])
        btime = None
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "):
                btime = int(line.split()[1])
                break
        if btime is None:
            return None
        return btime + (starttime / float(hz))
    except Exception:
        return None


def _grok_session_dir(cwd: str, pids: list[int]) -> Path | None:
    home = _grok_home()
    pidset = {int(p) for p in pids if p}
    active = home / "active_sessions.json"
    if active.is_file():
        try:
            sessions = json.loads(active.read_text())
        except json.JSONDecodeError:
            sessions = []
        for item in sessions:
            if item.get("pid") in pidset:
                encoded = quote(item.get("cwd") or cwd or "", safe="")
                path = home / "sessions" / encoded / item["session_id"]
                if path.is_dir():
                    return path
    if not cwd:
        return None
    encoded = quote(cwd, safe="")
    root = home / "sessions" / encoded
    if not root.is_dir():
        return None
    candidates = [
        p for p in root.iterdir() if p.is_dir() and (p / "updates.jsonl").is_file()
    ]
    if not candidates:
        return None
    starts = [t for t in (_pid_start_epoch(p) for p in pidset) if t]
    floor = min(starts) - 5 if starts else time.time() - 90
    fresh = [p for p in candidates if (p / "updates.jsonl").stat().st_mtime >= floor]
    pool = fresh or []
    if not pool:
        # Do not attach a stale cwd transcript to a new pane.
        return None
    pool.sort(key=lambda p: (p / "updates.jsonl").stat().st_mtime, reverse=True)
    return pool[0]


def _tool_label(update: dict, fallback: str = "tool") -> str:
    title = (update.get("title") or fallback or "tool").strip().rstrip(":")
    raw_in = update.get("rawInput") if isinstance(update.get("rawInput"), dict) else {}
    raw_out = update.get("rawOutput") if isinstance(update.get("rawOutput"), dict) else {}
    action = raw_out.get("action") if isinstance(raw_out.get("action"), dict) else {}
    detail = (
        raw_in.get("target_file")
        or raw_in.get("command")
        or raw_in.get("query")
        or raw_in.get("path")
        or action.get("query")
        or action.get("url")
        or ""
    )
    if isinstance(detail, str):
        detail = detail.strip()
    else:
        detail = ""
    if detail and detail.lower() not in title.lower():
        return f"{title} · {detail}"
    return title or "tool"


def _coalesce_grok_updates(path: Path) -> list[dict]:
    messages: list[dict] = []
    current: dict | None = None
    tools: dict[str, dict] = {}

    def flush():
        nonlocal current
        if current and (current.get("text") or "").strip():
            current["text"] = current["text"].strip()
            messages.append(current)
        current = None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        update = ((obj.get("params") or {}).get("update")) or {}
        kind = update.get("sessionUpdate")
        if kind == "user_message_chunk":
            text = _chunk_text(update)
            if current is None or current.get("role") != "user":
                flush()
                current = {"role": "user", "text": text}
            else:
                current["text"] += text
        elif kind == "agent_message_chunk":
            text = _strip_system_blocks(_chunk_text(update))
            if not text:
                continue
            if current is None or current.get("role") != "agent":
                flush()
                current = {"role": "agent", "text": text}
            else:
                current["text"] += text
        elif kind == "tool_call":
            flush()
            tid = update.get("toolCallId") or ""
            msg = {"role": "tool", "text": _tool_label(update)}
            messages.append(msg)
            if tid:
                tools[tid] = msg
        elif kind == "tool_call_update":
            tid = update.get("toolCallId") or ""
            msg = tools.get(tid)
            label = _tool_label(update, (msg or {}).get("text") or "tool")
            if msg:
                msg["text"] = label
            elif label:
                flush()
                extra = {"role": "tool", "text": label}
                messages.append(extra)
                if tid:
                    tools[tid] = extra
        elif kind in {"turn_completed", "hook_execution"}:
            flush()
        # skip thoughts, plans, etc.
    flush()
    return messages


def _strip_system_blocks(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(
        r"<system-reminder>[\s\S]*?</system-reminder>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _codex_hook_fields(blob: str) -> list[str]:
    fields = []
    for key in ("Event", "Source", "Command", "Mode", "Timeout", "Trust"):
        match = re.search(rf"(?im)^\s*{key}\s+(.+)$", blob)
        if match:
            fields.append(f"{key}: {match.group(1).strip()}")
    return fields


def _parse_codex_hooks(blob: str) -> dict | None:
    low = blob.lower()
    details = _codex_hook_fields(blob)
    match = re.search(r"(\d+)\s+hooks? needs? review", blob, re.I)
    if "to toggle" in low:
        return {
            "kind": "keys",
            "title": "Hooks",
            "prompt": "Hook trusted. Continue to start the session.",
            "options": [
                {"label": "Continue", "keys": ["esc"]},
                {"label": "Toggle", "keys": ["space"]},
            ],
        }
    if "trust all" in low:
        if match and match.group(1) == "1":
            prompt = "1 hook needs review before it can run."
        elif match:
            prompt = f"{match.group(1)} hooks need review before they can run."
        else:
            prompt = "A hook needs review before it can run."
        return {
            "kind": "keys",
            "title": "Hooks",
            "prompt": prompt,
            "options": [
                {"label": "Trust all", "keys": ["t"]},
                {"label": "Review hooks", "keys": ["enter"]},
                {"label": "Close", "keys": ["esc"]},
            ],
        }
    if re.search(r"\bt to trust\b", low):
        prompt = "\n".join(details) if details else "Review this hook."
        return {
            "kind": "keys",
            "title": "Hook review",
            "prompt": prompt,
            "options": [
                {"label": "Trust this hook", "keys": ["t"]},
                {"label": "Back", "keys": ["esc"]},
            ],
        }
    return None


_LEGEND_KEYS = {
    "enter": "enter",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
    "space": "space",
    "tab": "tab",
    "backspace": "backspace",
}


def _legend_key(token: str) -> str | None:
    name = (token or "").strip().lower()
    if name in _LEGEND_KEYS:
        return _LEGEND_KEYS[name]
    if len(name) == 1 and name.isalnum():
        return name
    return None


def _title_case_action(text: str) -> str:
    label = re.sub(r"\s+", " ", (text or "").strip()).rstrip(".")
    if not label:
        return ""
    return label[0].upper() + label[1:]


def _parse_key_legend(blob: str) -> dict | None:
    """Turn a TUI footer like 'Press t to trust; esc to close' into buttons."""
    lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
    legend = ""
    for ln in reversed(lines):
        low = ln.lower()
        if " to " in low and (
            low.startswith("press ")
            or "esc to " in low
            or "enter to " in low
            or re.search(r"\b[a-z] to ", low)
        ):
            legend = ln
            break
    if not legend:
        return None
    body = re.sub(r"(?i)^press\s+", "", legend).strip()
    options = []
    seen = set()
    for part in [p.strip() for p in re.split(r"[;|]", body) if p.strip()]:
        matched = re.match(
            r"(?i)^(space|enter|return|esc|escape|tab|backspace|[a-z0-9])"
            r"(?:\s+or\s+(space|enter|esc|escape|[a-z0-9]))?"
            r"\s+to\s+(.+)$",
            part,
        )
        if not matched:
            continue
        key = _legend_key(matched.group(1))
        if not key or key in seen:
            continue
        seen.add(key)
        label = _title_case_action(matched.group(3))
        options.append({"label": label or key, "keys": [key]})
    if not options:
        return None
    return {
        "kind": "keys",
        "title": "",
        "prompt": legend,
        "options": options,
    }


def parse_tui_question(text: str) -> dict | None:
    """Pull a TUI poll (Codex hooks, Claude AskUserQuestion, etc.) out of pane text."""
    if not text:
        return None
    blob = text.replace("\r", "")
    hooks = _parse_codex_hooks(blob)
    if hooks:
        return hooks
    legend = _parse_key_legend(blob)
    if legend:
        return legend
    if "Enter to select" not in blob and "to navigate" not in blob:
        return None
    lines = [ln.rstrip() for ln in blob.splitlines()]
    title = ""
    for ln in lines:
        if "☐" in ln or "☑" in ln:
            title = re.sub(r"^[☐☑\s]+", "", ln).strip()
            break
    prompt = ""
    options: list[dict] = []
    cursor = 1
    i = 0
    while i < len(lines):
        ln = lines[i]
        marked = re.match(r"^\s*(❯)?\s*(\d+)\.\s+(.*)$", ln)
        if marked:
            n = int(marked.group(2))
            if marked.group(1):
                cursor = n
            label = marked.group(3).strip()
            desc = ""
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if re.match(r"^\s*(❯)?\s*\d+\.\s+", nxt):
                    break
                if "──" in nxt or "Enter to select" in nxt:
                    break
                if nxt.strip():
                    desc = (desc + " " + nxt.strip()).strip()
                j += 1
            options.append({
                "n": n,
                "label": label,
                "description": desc,
                "input": bool(re.match(r"(?i)^type something\b", label)),
            })
            i = j
            continue
        if ln.strip().endswith("?") and not options:
            prompt = ln.strip()
        i += 1
    if len(options) < 2:
        return None
    return {
        "kind": "choice",
        "title": title,
        "prompt": prompt,
        "cursor": cursor,
        "options": options,
    }


def _chunk_text(update: dict) -> str:
    content = update.get("content")
    if isinstance(content, dict):
        return content.get("text") or ""
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return ""
