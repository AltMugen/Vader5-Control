#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVER_DIR="$HOME/.local/share/vader5-driver/sdl"
[[ -f "$DRIVER_DIR/libSDL3-64.so.0" && -x "$HOME/.local/bin/vader5-rumble" ]] || {
    echo 'Run ./build.sh first.' >&2; exit 1;
}

for tool in curl wget tar; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done

if [[ "${SKIP_PADCTL:-0}" != 1 ]]; then
    echo 'Installing Padctl...'
    PADCTL_TMP="$(mktemp -d)"
    trap 'rm -rf "$PADCTL_TMP"' EXIT
    PADCTL_URL="$(curl -fsSL https://api.github.com/repos/BANANASJIM/padctl/releases/latest \
        | grep -o 'https://[^" ]*x86_64-linux-musl.tar.gz' \
        | head -n 1)"
    [[ -n "$PADCTL_URL" ]] || { echo 'Could not find the latest Padctl Linux release.' >&2; exit 1; }
    wget -q --show-progress -O "$PADCTL_TMP/padctl.tar.gz" "$PADCTL_URL"
    tar -xzf "$PADCTL_TMP/padctl.tar.gz" -C "$PADCTL_TMP"
    PADCTL_BIN="$(find "$PADCTL_TMP" -type f -name padctl -print -quit)"
    [[ -n "$PADCTL_BIN" ]] || { echo 'Padctl binary was not found in the release archive.' >&2; exit 1; }
    sudo install -Dm 0755 "$PADCTL_BIN" /usr/bin/padctl
fi

install -Dm 0755 "$ROOT/vader5" "$HOME/.local/bin/vader5"
install -Dm 0644 "$ROOT/tools/configure-steam.py" "$DRIVER_DIR/configure-steam.py"
install -Dm 0644 "$ROOT/tools/discover-bluetooth.py" "$DRIVER_DIR/discover-bluetooth.py"
install -Dm 0644 "$ROOT/60-vader5-sdl.rules" "$DRIVER_DIR/60-vader5-sdl.rules"
install -Dm 0644 "$ROOT/systemd/vader5-rumble.service" "$HOME/.config/systemd/user/vader5-rumble.service"
sudo install -m 0644 "$ROOT/60-vader5-sdl.rules" /etc/udev/rules.d/60-vader5-sdl.rules
sudo udevadm control --reload-rules
systemctl --user daemon-reload
"$HOME/.local/bin/vader5" update
"$HOME/.local/bin/vader5" native
