# Ranchr

Phone/desktop client for coding agents that already run on your PC.

[Herdr](https://herdr.dev) is the herder — the ranch hand that tends the cattle on a machine. Ranchr is the rancher: you, looking over one or more ranches when you’re not in the yard. A small HTTP gateway talks to a live Herdr session over its Unix socket. The PWA shows the herd, chat, tools, and spawn/stop/close. Chat uses harness adapters (Grok today) so you see the conversation, not the TUI chrome. Terminal still has the raw pane.

The phone app is a PWA on GitHub Pages. Your PC still runs the gateway and agents. A magic link ties the two together.

## Requirements

- Python 3
- [Herdr](https://herdr.dev) running (`herdr` / Omarchy `Super+Ctrl+Return`)
- A coding agent Herdr can detect (Grok, Claude, Codex, OpenCode, …)
- `cloudflared` and `qrencode` (the widget can install these)

## Run

Local only:

```bash
./run.sh
```

Open http://127.0.0.1:8787/ on this machine.

The installable app lives at **https://scttymn.github.io/ranchr/**. On a phone, open that URL once and add it to the home screen. It talks to this PC only after you start the host.

Host tunnel (magic link + QR):

```bash
./bin/ranchr host on     # gateway + trycloudflare URL + QR
./bin/ranchr host status
./bin/ranchr host notify # mail via HEY or SMTP if configured
./bin/ranchr host off
```

The magic link is `https://scttymn.github.io/ranchr/?host=<tunnel>&t=<token>`. The token is the credential. Scan the QR or tap the mail; the PWA stores the ranch and does not need a password.

Override the app URL if you fork:

```bash
./bin/ranchr config set app_url https://you.github.io/ranchr
```

Omarchy widget (toggle, QR, notify settings):

```bash
omarchy plugin add https://github.com/scttymn/ranchr.git --enable
```

The first time the widget loads, it checks for **cloudflared** and **qrencode**. If either is missing, the panel opens and offers **Install missing tools…**, which runs `omarchy pkg add cloudflared qrencode` in a floating terminal.

Notify is **none** (QR only), **hey**, or **smtp**, set in the widget. The mail is the credential: tap `/?t=…` and a cookie is set. No Ranchr password.

Optional:

```bash
HERD_PORT=8787 HERD_HOST=127.0.0.1 ./run.sh
```

The PWA pulls live colors from the ranch (`/api/theme.css`). Change the Omarchy theme on this PC and the phone follows. Until it connects, the fallback palette is Omarchy’s default **Tokyo Night**.

## Layout

| Path | What |
|---|---|
| `gateway.py` | localhost HTTP/SSE ↔ Herdr socket |
| `adapters.py` | harness transcripts (Grok `updates.jsonl`, …) |
| `app/` | PWA |
| `index.html` | early visual mock (Pixel frame) |

## Status

Local PWA against live Herdr works. Phone: install https://scttymn.github.io/ranchr/ , start the host from the Omarchy widget, open the magic link.
