#!/usr/bin/env bash
# Build against glibc 2.31 in a disposable rootless container.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${SDL_SOURCE_DIR:-$HOME/.cache/vader5/SDL-3.4.4}"
OUTPUT="${OUTPUT_DIR:-$HOME/.local/share/vader5-driver/sdl}"
BIN_OUTPUT="${VADER5_BIN_DIR:-$HOME/.local/bin}"
for tool in git podman; do command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }; done
[[ "$(git -C "$SOURCE" describe --tags --exact-match 2>/dev/null)" == release-3.4.4 ]] || {
    echo 'SDL_SOURCE_DIR must contain SDL release-3.4.4. Run the source checkout step from build.sh first.' >&2; exit 1;
}
[[ "${BUILD_32:-0}" == 0 ]] || { echo 'The portable release builder currently targets x86_64 only.' >&2; exit 1; }
mkdir -p "$OUTPUT" "$BIN_OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"; BIN_OUTPUT="$(cd "$BIN_OUTPUT" && pwd)"
WORK=$(mktemp -d /tmp/vader5-portable.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
git -c advice.detachedHead=false clone --quiet --no-hardlinks "$SOURCE" "$WORK/sdl"
cat > "$WORK/build.sh" <<'INNER'
set -eu
# Use signed archived repositories for this compatibility SDK.
printf '%s\n' 'Acquire::https::CaInfo "/host-ca.crt";' > /etc/apt/apt.conf.d/99vader5-ca
printf '%s\n' 'deb https://archive.debian.org/debian bullseye main' 'deb https://archive.debian.org/debian-security bullseye-security main' > /etc/apt/sources.list
apt-get -o Acquire::Check-Valid-Until=false update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates git gcc g++ cmake ninja-build pkg-config python3 patchelf libusb-1.0-0-dev libudev-dev libdbus-1-dev libx11-dev libxext-dev libxcursor-dev libxi-dev libxfixes-dev libxrandr-dev libxrender-dev libxinerama-dev libxss-dev libxtst-dev libwayland-dev libxkbcommon-dev wayland-protocols libegl1-mesa-dev libasound2-dev libpulse-dev
cd /work
SDL_SOURCE_DIR=/sdl OUTPUT_DIR=/out VADER5_BIN_DIR=/bin-out BUILD_DIR=/tmp/build CC=/usr/bin/gcc ./build.sh
INNER
podman run --rm --security-opt label=disable \
    -v "$ROOT:/work:ro" -v "$WORK/sdl:/sdl:ro" \
    -v "$OUTPUT:/out:rw" -v "$BIN_OUTPUT:/bin-out:rw" \
    -v "$WORK/build.sh:/build.sh:ro" -v "$(readlink -f /etc/ssl/certs/ca-certificates.crt):/host-ca.crt:ro" \
    docker.io/library/debian:bullseye-slim /bin/sh /build.sh
