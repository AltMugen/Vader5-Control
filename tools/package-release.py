"""Prepare local release archives. Does not commit, tag or publish."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import zipfile
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from windows.runtime_bundle import prune_runtime
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--version', default='0.1')
parser.add_argument('--linux-dir', type=Path, default=root / 'dist/linux-x86_64')
parser.add_argument('--windows-dir', type=Path, default=root / 'dist/Vader5Control-Windows-x64')
parser.add_argument('--output-dir', type=Path, default=root / 'dist/release-candidate')
args = parser.parse_args()
version = args.version
if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,2}', version):
    raise SystemExit('Version must contain numeric components')
linux_name = f'Vader5Control-{version}-linux-x86_64'
windows_name = f'Vader5Control-{version}-windows_experimental-x64'
source_name = f'Vader5Control-{version}-source'
dist = args.output_dir.resolve()
if dist.exists():
    raise SystemExit('Output already exists; choose a new --output-dir')
for path in (args.windows_dir / 'Vader5Control.exe', args.windows_dir / 'ucrt64/bin/pythonw.exe',
             args.windows_dir / 'app/SDL3.dll', args.linux_dir / 'sdl/libSDL3-64.so.0'):
    if not path.is_file():raise SystemExit(f'Missing runtime file: {path}')
dist.mkdir(parents=True)
linux = dist / 'linux-x86_64'
windows = dist / 'Vader5Control-Windows-x64'
shutil.copytree(args.linux_dir, linux)
shutil.copytree(args.windows_dir, windows,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for path in (linux / 'sdl/libSDL3-64.so.0', linux / 'sdl/sdl3_shim64.so',
             linux / 'sdl/steam-sdl-loader.so',
             linux / 'bin/vader5-rumble', windows / 'app/SDL3.dll'):
    if not path.is_file():
        raise SystemExit(f'Missing binary: {path}')
# Release binaries target glibc 2.31 or earlier.
versions = subprocess.check_output(['readelf', '--version-info', str(linux / 'sdl/libSDL3-64.so.0')], text=True)
for glibc_version in re.findall(r'GLIBC_(\d+\.\d+)', versions):
    if tuple(map(int, glibc_version.split('.'))) > (2, 31):
        raise SystemExit('Build the Linux release with tools/build-linux-portable.sh first')
for name in ('install.sh', 'install-prebuilt.sh', 'vader5', '60-vader5-sdl.rules', 'README.md'):
    shutil.copy2(root / name, linux / name)
(linux / 'tools').mkdir(exist_ok=True)
shutil.copy2(root / 'tools/configure-steam.py', linux / 'tools/configure-steam.py')
shutil.copy2(root / 'tools/configure-steam.py', linux / 'sdl/configure-steam.py')
shutil.copy2(root / 'tools/discover-bluetooth.py', linux / 'tools/discover-bluetooth.py')
shutil.copy2(root / 'tools/discover-bluetooth.py', linux / 'sdl/discover-bluetooth.py')
shutil.copytree(root / 'systemd', linux / 'systemd', dirs_exist_ok=True)
shutil.copytree(root / 'gui', linux / 'gui', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'tests'))
shutil.rmtree(linux / 'release-notes', ignore_errors=True)
(linux / 'release-notes').mkdir()
for note in (f'v{version}-linux.md', f'v{version}-windows-experimental.md'):
    shutil.copy2(root / 'release-notes' / note, linux / 'release-notes' / note)
shutil.rmtree(linux / 'docs', ignore_errors=True)
(linux / 'windows').mkdir(exist_ok=True)
shutil.copy2(root / 'windows/README.md', linux / 'windows/README.md')
shutil.copytree(root / 'gui', windows / 'app', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'tests', 'helpers'))
for name in ('Install.ps1', 'Run-Patch.ps1', 'Bluetooth.ps1'):
    shutil.copy2(root / 'windows' / name, windows / 'app' / name)
shutil.copy2(root / 'windows/README.md', windows / 'README.md')
shutil.copy2(root / 'windows/Launch.cmd', windows / 'Launch.cmd')
shutil.copy2(root / 'windows/Diagnose-Startup.cmd', windows / 'Diagnose-Startup.cmd')
(windows / 'RELEASE-NOTES.md').write_text((root / f'release-notes/v{version}-windows-experimental.md').read_text().replace('../windows/README.md', 'README.md'))
license_file = Path(os.environ.get('SDL_SOURCE_DIR', str(Path.home() / '.cache/vader5/SDL-3.4.4'))) / 'LICENSE.txt'
for folder in (linux, windows):
    shutil.copy2(license_file, folder / 'SDL-LICENSE.txt')
shutil.copy2(root / f'release-notes/v{version}-linux.md', linux / 'RELEASE-NOTES.md')
prune_runtime(windows)
assets = []
with tarfile.open(dist / (linux_name + '.tar.gz'), 'w:gz') as archive:
    archive.add(linux, arcname=linux_name)
assets.append(dist / (linux_name + '.tar.gz'))
with zipfile.ZipFile(dist / (windows_name + '.zip'), 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(windows.rglob('*')):
        if path.is_file():
            archive.write(path, windows_name + '/' + path.relative_to(windows).as_posix())
assets.append(dist / (windows_name + '.zip'))
# Collect source files without changing the Git index.
files = set(subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines())
for directory in ('src/flashplay', 'tools', 'windows', 'release-notes', 'gui', 'docs', 'tests'):
    files.update(str(path.relative_to(root)) for path in (root / directory).rglob('*')
                 if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
files.update(('.gitignore', 'install-prebuilt.sh', 'src/steam-sdl-loader.c'))
files = {name for name in files if (root / name).is_file()
         and not any(part.startswith('.') and part != '.gitignore'
                     for part in Path(name).parts)}
with tarfile.open(dist / (source_name + '.tar.gz'), 'w:gz') as archive:
    for name in sorted(files):
        archive.add(root / name, arcname=source_name + '/' + name, recursive=False)
    archive.add(license_file, arcname=source_name + '/SDL-LICENSE.txt')
assets.append(dist / (source_name + '.tar.gz'))
# A full reviewable patch, including new files, without changing the real Git index.
patch = subprocess.check_output(['git', 'diff', '--binary', 'HEAD', '--', '.'], cwd=root)
tracked = set(subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines())
for name in sorted(files - tracked):
    result = subprocess.run(['git', 'diff', '--no-index', '--binary', '--', '/dev/null', name], cwd=root, stdout=subprocess.PIPE)
    if result.returncode not in (0, 1):
        raise SystemExit(f'Cannot produce patch for {name}')
    patch += result.stdout
(dist / 'local-update.patch').write_bytes(patch)
assets.append(dist / 'local-update.patch')
checksums = ''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in assets)
(dist / 'SHA256SUMS').write_text(checksums)
manifest = {'published': False, 'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'sdl_tag': 'release-3.4.4', 'version': version, 'linux': version + '-beta', 'windows': version + '-windows_experimental',
            'bluetooth_known_disconnects': True,
            'windows_hardware_verified': False, 'full_bluetooth_imu': False, 'linux_glibc_max': '2.31',
            'windows_feedback': {'gui_startup': True, 'bluetooth_input': True,
                                 'updated_steam_handoff_verified': False},
            'assets': [path.name for path in assets]}
(dist / 'release-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(checksums, end='')
