#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - <<'PY'
import sys,gi,cairo
if sys.version_info < (3,11): raise SystemExit('Python 3.11 or newer is required')
for name,version in [('Gtk','4.0'),('Adw','1'),('Rsvg','2.0')]: gi.require_version(name,version)
from gi.repository import Gtk,Adw,Rsvg
if not hasattr(Adw,'AlertDialog'): raise SystemExit('libadwaita 1.5 or newer is required')
if Gtk.get_minor_version() < 10: raise SystemExit('GTK 4.10 or newer is required')
PY
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/vader5-control"
if [[ -d "$APP_DIR" ]]; then
    BACKUP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/vader5-control-backups/$(date +%Y%m%d-%H%M%S)-$$"
    mkdir -p "$BACKUP_DIR"
    cp -a "$APP_DIR" "$BACKUP_DIR/app"
    for path in "$HOME/.local/bin/vader5-control" "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.AltMugen.Vader5Control.desktop"; do
        if [[ -f "$path" ]]; then cp -a "$path" "$BACKUP_DIR/"; fi
    done
    printf 'Backup: %s\n' "$BACKUP_DIR"
fi
mkdir -p "$APP_DIR/assets" "$APP_DIR/helpers" "$HOME/.local/bin" "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
install -m644 "$ROOT/app.py" "$ROOT/backend.py" "$ROOT/bluetooth_setup.py" "$ROOT/device.py" "$ROOT/hid_windows.py" "$ROOT/platform_windows.py" "$ROOT/protocol.py" "$ROOT/input_settings.py" "$ROOT/input_page.py" "$ROOT/hardware_settings.py" "$ROOT/motors.py" "$ROOT/lighting.py" "$ROOT/rgb_editor.py" "$ROOT/color_picker.py" "$ROOT/style.css" "$APP_DIR/"
install -m644 "$ROOT/assets/overview.svg" "$ROOT/assets/lighting.svg" "$APP_DIR/assets/"
install -m644 "$ROOT/assets/lighting-presets.json" "$ROOT/assets/vader5-control.png" "$APP_DIR/assets/"
python3 - "$ROOT/assets/vader5-control.png" "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" "$APP_DIR/assets/icons/hicolor" <<'PYICONS'
import sys
from pathlib import Path
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf
image = GdkPixbuf.Pixbuf.new_from_file(sys.argv[1])
for base in sys.argv[2:]:
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        target = Path(base) / f'{size}x{size}' / 'apps'
        target.mkdir(parents=True, exist_ok=True)
        icon = image.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        icon.savev(str(target / 'io.github.AltMugen.Vader5Control.png'), 'png', [], [])
PYICONS
install -m755 "$ROOT/askpass.py" "$APP_DIR/askpass.py"
install -m755 "$ROOT/helpers/sudo" "$APP_DIR/helpers/sudo"
# Fixed launcher paths are passed as arguments, with no shell evaluation of user input.
printf '#!/bin/sh\nexec python3 "%s/app.py" "$@"\n' "$APP_DIR" > "$HOME/.local/bin/vader5-control"
chmod 755 "$HOME/.local/bin/vader5-control"
cat > "${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.github.AltMugen.Vader5Control.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Vader5 Control
Comment=Flydigi Vader 5 Pro settings
Exec="$HOME/.local/bin/vader5-control"
Icon=io.github.AltMugen.Vader5Control
Terminal=false
StartupWMClass=io.github.AltMugen.Vader5Control
Categories=Settings;HardwareSettings;
DESKTOP
if command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -q -t -f "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" || true
fi
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
fi
printf 'Installed Vader5 Control. Run vader5-control.\n'
