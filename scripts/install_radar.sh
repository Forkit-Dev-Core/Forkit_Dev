#!/bin/sh
# Account-free bootstrap; run from the source checkout or supplied local kit.
# An extracted offline bundle replaces the two constants below at build time.
FORKIT_REQUIRED_MINOR=''
FORKIT_INSTALLER='install_radar.py'
FORKIT_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 1
for FORKIT_PYTHON in python3 python3.13 python3.12 python3.11 python3.10; do
    command -v "$FORKIT_PYTHON" >/dev/null 2>&1 || continue
    if "$FORKIT_PYTHON" -I -c 'import sys; expected=sys.argv[1]; actual="%s.%s" % sys.version_info[:2]; sys.exit(not ((3,10)<=sys.version_info[:2]<=(3,13) and (not expected or actual==expected)))' "$FORKIT_REQUIRED_MINOR" >/dev/null 2>&1; then
        exec "$FORKIT_PYTHON" -I "$FORKIT_SCRIPT_DIR/$FORKIT_INSTALLER" "$@"
    fi
done
printf '%s\n' "A compatible Python with venv/pip is required."
if [ -n "$FORKIT_REQUIRED_MINOR" ]; then
    printf 'This offline kit needs Python %s on the platform printed in README.txt.\n' "$FORKIT_REQUIRED_MINOR"
else
    printf '%s\n' 'Use Python 3.10–3.13. See the beta guide for prerequisites.'
fi
printf '%s\n' 'Nothing installed. No account, download or shell-profile change was attempted.'
exit 1
