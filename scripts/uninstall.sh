#!/bin/sh
# Remove what install.sh added. Usage: uninstall.sh [--dry-run] [--prefix DIR]
set -eu
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$here/relevo_install.py" uninstall "$@"
