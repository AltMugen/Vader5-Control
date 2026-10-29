#!/usr/bin/env bash
# Cross build Windows x64 preview on Linux with MinGW-w64.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDL_SOURCE_DIR="${SDL_SOURCE_DIR:-$HOME/.cache/vader5/SDL-3.4.4}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT/dist/windows-x64}"
[[ "$(git -C "$SDL_SOURCE_DIR" describe --tags --exact-match)" == release-3.4.4 ]] || exit 1
WORK=$(mktemp -d /tmp/vader5-windows.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/source" "$OUTPUT_DIR"
git -C "$SDL_SOURCE_DIR" archive release-3.4.4 | tar -x -C "$WORK/source"
git -C "$WORK/source" apply "$ROOT/patches/sdl-flydigi-vader5-linux.patch"
python3 "$ROOT/tools/prepare-sdl.py" "$WORK/source" --platform windows
cmake -S "$WORK/source" -B "$WORK/build" -G Ninja \
    -DCMAKE_SYSTEM_NAME=Windows -DCMAKE_C_COMPILER=/usr/bin/x86_64-w64-mingw32-gcc \
    -DCMAKE_CXX_COMPILER=/usr/bin/x86_64-w64-mingw32-g++ \
    -DCMAKE_RC_COMPILER=/usr/bin/x86_64-w64-mingw32-windres \
    -DCMAKE_BUILD_TYPE=MinSizeRel -DSDL_CCACHE=OFF -DSDL_TESTS=OFF \
    -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_UNIX_CONSOLE_BUILD=ON
cmake --build "$WORK/build" --parallel "${JOBS:-8}"
install -m644 "$WORK/build/SDL3.dll" "$OUTPUT_DIR/SDL3.dll"
/usr/bin/x86_64-w64-mingw32-strip --strip-unneeded "$OUTPUT_DIR/SDL3.dll"
cp "$ROOT/windows/Install.ps1" "$ROOT/windows/README.md" "$OUTPUT_DIR/"
cp "$WORK/source/LICENSE.txt" "$OUTPUT_DIR/SDL-LICENSE.txt"
python3 - "$ROOT/gui/assets/vader5-control.png" "$WORK/app.ico" <<'PYICON'
import sys
from PIL import Image
Image.open(sys.argv[1]).save(sys.argv[2], sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
PYICON
printf '1 ICON "%s"\n' "$WORK/app.ico" > "$WORK/app.rc"
/usr/bin/x86_64-w64-mingw32-windres "$WORK/app.rc" "$WORK/app-resource.o"
/usr/bin/x86_64-w64-mingw32-gcc -Os -municode -mwindows -static-libgcc \
    "$ROOT/windows/launcher.c" "$WORK/app-resource.o" -luser32 -o "$OUTPUT_DIR/Vader5Control.exe"
echo "Windows x64 preview: $OUTPUT_DIR"
