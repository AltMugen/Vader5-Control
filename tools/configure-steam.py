#!/usr/bin/env python3
"""Install the per-user Steam launcher; migrate only verified old SDL patches."""
from pathlib import Path
import hashlib
import os
import re
import shlex
import shutil
import sys

if len(sys.argv) != 3:
    raise SystemExit('Usage: configure-steam.py DRIVER_DIR STEAM_DIR')
driver, steam = (Path(p).resolve() for p in sys.argv[1:])
home = Path.home()
for name in ('libSDL3-64.so.0', 'sdl3_shim64.so', 'steam-sdl-loader.so'):
    if not (driver / name).is_file():
        raise SystemExit(f'Missing driver file: {driver / name}. Rebuild SDL first.')
backup = driver / 'launcher-backups'
backup.mkdir(exist_ok=True)

def save_once(path, name):
    target = backup / name
    if not target.exists() and not target.with_suffix(target.suffix + '.absent').exists():
        if path.is_file():
            shutil.copy2(path, target)
        else:
            target.with_suffix(target.suffix + '.absent').touch()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

# Do not restore a stale backup over a library from a newer Steam update.
for folder in ('steamrt64', 'ubuntu12_64', 'ubuntu12_32'):
    target = steam / folder / 'libSDL3.so.0'
    original = driver / 'originals' / folder / 'libSDL3.so.0'
    receipt = driver / f'{folder}.last-patch.sha256'
    if target.is_file() and original.is_file() and receipt.is_file() and sha(target) == receipt.read_text().strip():
        shutil.copy2(original, target)
    shim = steam / folder / 'sdl3_shim.so'
    stock_shim = original.parent / 'sdl3_shim.so'
    own_shim = driver / ('sdl3_shim32.so' if folder == 'ubuntu12_32' else 'sdl3_shim64.so')
    if shim.is_file() and stock_shim.is_file() and own_shim.is_file() and sha(shim) == sha(own_shim):
        if os.access(shim, os.W_OK):
            shutil.copy2(stock_shim, shim)

private = driver / 'steam64'
private.mkdir(exist_ok=True)
for name, source in (('libSDL3.so.0', '../libSDL3-64.so.0'), ('sdl3_shim.so', '../sdl3_shim64.so')):
    link = private / name
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        raise SystemExit(f'Unexpected file: {link}')
    link.symlink_to(source)
launcher = home / '.local/bin/steam'
launcher.parent.mkdir(parents=True, exist_ok=True)
save_once(launcher, 'steam-launcher')
launcher.write_text('''#!/usr/bin/env bash
# Vader5 Steam launcher.
set -euo pipefail
export VADER5_STEAM_ROOT=%s
export VADER5_PRIVATE_SDL=%s
loader=%s
export LD_PRELOAD="${LD_PRELOAD:+$LD_PRELOAD:}$loader"
exec /usr/bin/steam "$@"
''' % tuple(shlex.quote(str(p)) for p in (steam, private / 'libSDL3.so.0', driver / 'steam-sdl-loader.so')))
launcher.chmod(0o755)
applications = Path(os.environ.get('XDG_DATA_HOME', str(home / '.local/share'))) / 'applications'
desktop = applications / 'steam.desktop'
sources = [desktop] + [Path(p) / 'applications/steam.desktop' for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')]
source = next((p for p in sources if p.is_file()), None)
if source:
    save_once(desktop, 'steam.desktop')
    text = source.read_text()
    # Preserve existing env assignments (e.g. extest), URLs and desktop actions.
    quoted_launcher = '"' + str(launcher).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '"'
    lines = []
    for line in text.splitlines():
        if line.startswith('Exec='):
            line = 'Exec=' + re.sub(r'(?<!\S)(?:/usr/bin/steam|steam)(?=\s|$)', lambda m: quoted_launcher, line[5:])
        lines.append(line)
    applications.mkdir(parents=True, exist_ok=True)
    desktop.write_text('\n'.join(lines) + '\n')
