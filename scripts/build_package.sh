#!/bin/sh
# Builds the KiCad PCM plugin zip into dist/ (install it via Plugin and Content Manager >
# "Install from File..."). Extra arguments pass straight to build_package.py:
#
#   scripts/build_package.sh
#   scripts/build_package.sh --list
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Try each interpreter rather than trust the name: on Windows, python3 can be a Store stub that fails.
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
        exec "$candidate" "$here/build_package.py" "$@"
    fi
done
echo "Python 3.9 or newer was not found on PATH." >&2
exit 1
