# Ranchr

Phone/desktop client for coding agents that already run on your PC.

[Herdr](https://herdr.dev) is the herder — the ranch hand that tends the cattle on a machine. Ranchr is the rancher: you, looking over one or more ranches when you’re not in the yard. A small HTTP gateway talks to a live Herdr session over its Unix socket. The PWA shows the herd, chat, tools, and spawn/stop/close. Chat uses harness adapters (Grok today) so you see the conversation, not the TUI chrome. Terminal still has the raw pane.

Remote (login-gated relay) is next. This repo is the local slice.

## Requirements

- Python 3
- [Herdr](https://herdr.dev) running (`herdr` / Omarchy `Super+Ctrl+Return`)
- A coding agent Herdr can detect (Grok, Claude, Codex, OpenCode, …)

## Run

```bash
./run.sh
```

Open http://127.0.0.1:8787/

Optional:

```bash
HERD_PORT=8787 HERD_HOST=127.0.0.1 ./run.sh
```

`sync-theme.sh` copies the current Omarchy palette into `theme.css` when you have Omarchy. Safe to skip elsewhere.

## Layout

| Path | What |
|---|---|
| `gateway.py` | localhost HTTP/SSE ↔ Herdr socket |
| `adapters.py` | harness transcripts (Grok `updates.jsonl`, …) |
| `app/` | PWA |
| `index.html` | early visual mock (Pixel frame) |

## Status

Works on the same machine as Herdr. Phone-on-LAN and a hosted relay are not in this tree yet.
