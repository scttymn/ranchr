#!/usr/bin/env bash
# Rebuild theme.css from the Omarchy theme currently applied on this machine.
# Called by hand, or from a theme-set hook (theme slug arrives as $1 and is ignored).

set -euo pipefail

# Prefer the mock directory even when this script is copied into a theme-set hook.
if [[ -d /home/scttymn/Work/herd-remote-mock ]]; then
  dir=/home/scttymn/Work/herd-remote-mock
else
  dir=$(cd "$(dirname -- "$0")" && pwd)
fi
name_file="$HOME/.local/state/omarchy/current/theme.name"
name="unknown"
[[ -f $name_file ]] && name=$(<"$name_file")

pretty=$(sed -E 's/(^|-)([a-z])/\1\u\2/g; s/-/ /g' <<<"$name")

tmp=$(mktemp)
{
  printf '%s\n' "/* generated $(date -Iseconds) from omarchy-theme-color — ${name} */"
  printf '%s\n' ":root {"
  printf '  --theme-name: "%s";\n' "$pretty"
  printf '  --theme-slug: "%s";\n' "$name"

  omarchy-theme-color --all | while IFS=$'\t' read -r key value; do
    [[ $key =~ ^[a-zA-Z0-9_]+$ ]] || continue
    case $value in
      \#*) ;;
      dark|light) ;;
      rgba\(*|rgb\(*) ;;
      *) continue ;;
    esac
    css=${key//_/-}
    printf '  --omarchy-%s: %s;\n' "$css" "$value"
  done

  cat <<'MAP'
  --bg: var(--omarchy-background);
  --bg-deep: var(--omarchy-darker-background);
  --raised: var(--omarchy-lighter-background);
  --raised-2: color-mix(in srgb, var(--omarchy-lighter-background) 82%, var(--omarchy-foreground) 18%);
  --fg: var(--omarchy-foreground);
  --fg-bright: var(--omarchy-bright-foreground);
  --fg-soft: var(--omarchy-light-foreground);
  --muted: var(--omarchy-muted);
  --frame: var(--omarchy-dark-foreground);
  --accent: var(--omarchy-accent, var(--omarchy-red));
  --accent-bright: var(--omarchy-bright-red);
  --accent-soft: var(--omarchy-bright-magenta);
  --green: var(--omarchy-green);
  --green-bright: var(--omarchy-bright-green);
  --green-glow: var(--omarchy-bright-green);
  --cream: var(--omarchy-yellow);
  --cream-bright: var(--omarchy-bright-yellow);
  --cyan: var(--omarchy-cyan);
  --hairline: color-mix(in srgb, var(--omarchy-foreground) 14%, transparent);
  --glass: color-mix(in srgb, var(--omarchy-lighter-background) 78%, transparent);
MAP
  printf '%s\n' "}"
} >"$tmp"

mv "$tmp" "$dir/theme.css"
