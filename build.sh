#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDL_TAG=release-3.4.4
SDL_SOURCE_DIR="${SDL_SOURCE_DIR:-$HOME/.cache/vader5/SDL-3.4.4}"
BUILD_DIR="${BUILD_DIR:-$HOME/.cache/vader5/build}"
OUTPUT_DIR="${OUTPUT_DIR:-$HOME/.local/share/vader5-driver/sdl}"
VADER5_BIN_DIR="${VADER5_BIN_DIR:-$HOME/.local/bin}"

for tool in git cmake ninja cc pkg-config patchelf python3; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
pkg-config --exists libusb-1.0 || { echo 'Install libusb1 development files' >&2; exit 1; }

if [[ ! -d "$SDL_SOURCE_DIR/.git" ]]; then
    git clone --depth 1 --branch "$SDL_TAG" https://github.com/libsdl-org/SDL.git "$SDL_SOURCE_DIR"
fi
[[ "$(git -C "$SDL_SOURCE_DIR" describe --tags --exact-match 2>/dev/null)" == "$SDL_TAG" ]] || {
    echo "Expected SDL tag $SDL_TAG in $SDL_SOURCE_DIR" >&2; exit 1;
}

mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"
install -m 0644 "$ROOT/60-vader5-sdl.rules" "$OUTPUT_DIR/60-vader5-sdl.rules"
install -m 0644 "$ROOT/tools/configure-steam.py" "$OUTPUT_DIR/configure-steam.py"
install -m 0644 "$ROOT/tools/discover-bluetooth.py" "$OUTPUT_DIR/discover-bluetooth.py"
RUN_BUILD=$(mktemp -d "$BUILD_DIR/run.XXXXXX")
SOURCE_BUILD="$RUN_BUILD/source"
trap 'rm -rf "$RUN_BUILD"' EXIT
git clone --quiet --shared "$SDL_SOURCE_DIR" "$SOURCE_BUILD"
git -C "$SOURCE_BUILD" checkout --quiet "$SDL_TAG"
git -C "$SOURCE_BUILD" apply "$ROOT/patches/sdl-flydigi-vader5-linux.patch"
python3 "$ROOT/tools/prepare-sdl.py" "$SOURCE_BUILD" --platform linux

cmake -S "$SOURCE_BUILD" -B "$RUN_BUILD/steam64" -G Ninja \
    -DCMAKE_C_COMPILER="${CC:-/usr/bin/gcc}" -DSDL_CCACHE=OFF \
    -DCMAKE_BUILD_TYPE=MinSizeRel -DBUILD_SHARED_LIBS=ON -DSDL_TESTS=OFF
cmake --build "$RUN_BUILD/steam64" --parallel "$(nproc)"
install -m 0644 "$RUN_BUILD/steam64/libSDL3.so.0" "$OUTPUT_DIR/libSDL3-64.so.0"
build_shim() {
    local bits="$1" library="$OUTPUT_DIR/libSDL3-$1.so.0"
    cc -shared -fPIC -m"$bits" \
        -Wl,--version-script="$ROOT/src/sdl3-shim.map" \
        -Wl,-soname,sdl3_shim.so \
        -o "$OUTPUT_DIR/sdl3_shim${bits}.so" "$ROOT/src/sdl3-shim.c" \
        -L"$OUTPUT_DIR" -Wl,-rpath,'$ORIGIN' -l:"$(basename "$library")"
    patchelf --set-rpath '$ORIGIN' "$library"
    patchelf --remove-needed sdl3_shim.so "$library" 2>/dev/null || true
    patchelf --add-needed sdl3_shim.so "$library"
}
build_shim 64
cc -O2 -Wall -Wextra -Werror -shared -fPIC "$ROOT/src/steam-sdl-loader.c" \
    -o "$OUTPUT_DIR/steam-sdl-loader.so" -ldl

cc -O2 -Wall -Wextra -Werror "$ROOT/src/vader5-rumble.c" -o "$RUN_BUILD/vader5-rumble" $(pkg-config --cflags --libs libusb-1.0)
install -Dm 0755 "$RUN_BUILD/vader5-rumble" "$VADER5_BIN_DIR/vader5-rumble"

if [[ "${BUILD_32:-0}" == 1 ]]; then
    cmake -S "$SOURCE_BUILD" -B "$RUN_BUILD/steam32" -G Ninja \
        -DCMAKE_C_COMPILER="${CC:-/usr/bin/gcc}" -DSDL_CCACHE=OFF \
        -DCMAKE_BUILD_TYPE=MinSizeRel -DBUILD_SHARED_LIBS=ON -DSDL_TESTS=OFF \
        -DCMAKE_C_FLAGS=-m32 -DCMAKE_SHARED_LINKER_FLAGS=-m32
    cmake --build "$RUN_BUILD/steam32" --parallel "$(nproc)"
    install -m 0644 "$RUN_BUILD/steam32/libSDL3.so.0" "$OUTPUT_DIR/libSDL3-32.so.0"
    build_shim 32
    touch "$OUTPUT_DIR/32-bit-build.enabled"
else
    rm -f "$OUTPUT_DIR/32-bit-build.enabled"
fi

echo "Built SDL and rumble bridge. Run ./install.sh to install rules and patch Steam."
