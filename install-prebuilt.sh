#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_DIR="$HOME/.local/share/vader5-driver/sdl"
[[ -f "$ROOT/sdl/libSDL3-64.so.0" && -f "$ROOT/sdl/sdl3_shim64.so" && -f "$ROOT/bin/vader5-rumble" ]] || {
    echo 'Missing prebuilt files. Extract the complete Linux release archive.' >&2; exit 1;
}
mkdir -p "$DRIVER_DIR" "$HOME/.local/bin"
install -m644 "$ROOT/sdl/libSDL3-64.so.0" "$ROOT/sdl/sdl3_shim64.so" "$ROOT/sdl/steam-sdl-loader.so" "$DRIVER_DIR/"
install -m755 "$ROOT/bin/vader5-rumble" "$HOME/.local/bin/vader5-rumble"
exec "$ROOT/install.sh" "$@"
