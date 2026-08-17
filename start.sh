#!/usr/bin/env sh
# Arena/host-compatible launcher. The platform may provide PORT dynamically.
set -eu
exec python3 -u app.py
