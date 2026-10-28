#!/bin/sh
# Install or upgrade relevo. Usage: install.sh [--dry-run] [--force] [--prefix DIR] [--no-settings] [--no-claude-md] [--pin-backup]
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$here/relevo_install.py" install "$@"
