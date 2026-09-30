#!/usr/bin/env bash
# Install this checkout for the current user; never elevate or load modules.
set -euo pipefail
usage() {
    cat <<'HELP'
Usage: ./install.sh [--prefix ABSOLUTE_PATH] [--dry-run]
Installs into PREFIX/lib/linuxshare-venv and PREFIX/bin (default: ~/.local).
Uses distro Python bindings for GTK via --system-site-packages.
Requires Python >=3.10 with venv/pip; downloads build tools from pip's index.
Refuses existing destinations. Does not install system packages or start capture.
HELP
}
prefix="${HOME}/.local"
dry_run=false
while (($#)); do
    case "$1" in
        --prefix) [[ $# -ge 2 && -n "$2" ]] || { usage >&2; exit 2; }; prefix="$2"; shift 2 ;;
        --dry-run) dry_run=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
[[ "$prefix" = /* && "$prefix" != *$'\n'* ]] || { echo 'Prefix must be absolute without newlines.' >&2; exit 2; }
[[ $EUID -ne 0 ]] || { echo 'Run as your normal user, not root or sudo.' >&2; exit 1; }
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
venv="$prefix/lib/linuxshare-venv"
for target in "$venv" "$prefix/bin/linuxshare-cli" "$prefix/bin/linuxshare-gui" "$prefix/bin/linuxshare-call" "$prefix/bin/linuxshare-call-server"; do
    if [[ -e "$target" || -L "$target" ]]; then
        echo "Refusing to overwrite: $target" >&2
        exit 1
    fi
done
python3 -c 'import sys, venv; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
printf 'Source: %s\nVirtual environment: %s\nLaunchers: %s/bin\n' "$source_dir" "$venv" "$prefix"
if "$dry_run"; then
    echo 'Dry run: no files changed.'
    exit 0
fi
mkdir -p -- "$prefix/lib" "$prefix/bin"
# mkdir refuses pre-existing paths, including symlinks.
mkdir -- "$venv"
echo 'Creating environment; a failed install may leave this directory for inspection.'
python3 -m venv --system-site-packages "$venv"
# Do not install PyGObject from pip: it must match the system GTK libraries.
"$venv/bin/python" -m pip --isolated install "${source_dir}[calls]"
"$venv/bin/linuxshare-cli" --version
ln -s -- "$venv/bin/linuxshare-cli" "$prefix/bin/linuxshare-cli"
ln -s -- "$venv/bin/linuxshare-gui" "$prefix/bin/linuxshare-gui"
for command in linuxshare-call linuxshare-call-server; do
    ln -s -- "$venv/bin/$command" "$prefix/bin/$command"
done
printf '\nInstalled. Add %s/bin to PATH if needed.\n' "$prefix"
cat <<'NOTICE'
Run linuxshare-cli --check before use. See docs/install.md for OS dependencies.
Run linuxshare-call for a local demonstration. See docs/private-calls.md for internet deployment.
NOTICE
