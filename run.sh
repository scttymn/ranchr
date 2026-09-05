#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
chmod +x gateway.py
exec python3 gateway.py
