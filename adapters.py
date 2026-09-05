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
    return {
        "adapter": None,
        "title": None,
        "messages": [],
        "note": f"No chat adapter for {kind or 'this harness'} yet. Terminal still has the raw TUI.",
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


def _grok_home() -> Path:
    return Path.home() / ".grok"


def _pid_start_epoch(pid: int) -> float | None:
    try:
        hz = os.sysconf(os.SC_CLK_TCK)
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
