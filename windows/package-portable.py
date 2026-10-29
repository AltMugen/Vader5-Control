#!/usr/bin/env python3
"""Assemble a Windows GTK runtime from official MSYS2 UCRT64 packages.

Run after windows/build.sh. Downloads are cached and checked against SHA256
from the repository database. No packages are installed on the build host.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from runtime_bundle import prune_runtime

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'mingw-w64-ucrt-x86_64-'
MIRROR = 'https://repo.msys2.org/mingw/ucrt64/'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--cache', type=Path, required=True)
p.add_argument('--output', type=Path, default=ROOT/'dist/Vader5Control-Windows-x64')
p.add_argument('--database', type=Path)
p.add_argument('--sdl-build', type=Path, default=ROOT/'dist/windows-x64')
a = p.parse_args()
a.cache.mkdir(parents=True, exist_ok=True)

def fetch(url, path):
    temporary = path.with_suffix(path.suffix+'.part')
    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                    '--retry', '3', '--connect-timeout', '15', '--max-time', '180',
                    url, '--output', str(temporary)], check=True)
    temporary.replace(path)


database = a.database or a.cache/'ucrt64.db'
if not a.database:
    fetch(MIRROR+'ucrt64.db', database)
packages = {}; providers = {}
with tarfile.open(database) as archive:
    for member in archive:
        if not member.name.endswith('/desc'):
            continue
        fields = {}
        for section in archive.extractfile(member).read().decode().strip().split('\n\n'):
            lines = section.splitlines(); fields[lines[0].strip('%')] = lines[1:]
        packages[fields['NAME'][0]] = fields
        for provided in fields.get('PROVIDES', []):
            providers[re.split('[<>=]', provided)[0]] = fields['NAME'][0]
selected = {}
pending = [PREFIX+n for n in ('libadwaita', 'librsvg', 'python-gobject', 'adwaita-icon-theme')]
while pending:
    name = re.split('[<>=]', pending.pop())[0]
    name = providers.get(name, name)
    if name in selected:
        continue
    if name not in packages or not name.startswith(PREFIX):
        raise ValueError('Unresolved UCRT64 runtime dependency: '+name)
    selected[name] = packages[name]
    pending.extend(packages[name].get('DEPENDS', []))
print(f'Resolved {len(selected)} packages, {sum(int(x["CSIZE"][0]) for x in selected.values())/1048576:.1f} MiB', flush=True)

def download(record):
    filename = record['FILENAME'][0]
    if Path(filename).name != filename:
        raise ValueError('Invalid package filename')
    path = a.cache/filename
    expected = record['SHA256SUM'][0]
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        fetch(MIRROR+filename, path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('Package checksum mismatch: '+filename)
    return path

with ThreadPoolExecutor(max_workers=4) as pool:
    downloaded = list(pool.map(download, selected.values()))
if a.output.exists():
    raise SystemExit('Output exists; choose a new --output directory')
a.output.mkdir(parents=True)
# Keep DLLs, typelib files, Python libraries, resources and licenses. Development
# headers/static libraries and manuals are unnecessary for this runtime bundle.
for path in downloaded:
    with tarfile.open(path) as archive:
        for member in archive:
            parts = Path(member.name).parts
            if not parts or parts[0] != 'ucrt64':
                continue
            if len(parts)>1 and parts[1] == 'include':
                continue
            if member.name.endswith(('.a', '.la')) or '/pkgconfig/' in member.name or '/cmake/' in member.name:
                continue
            if '/share/doc/' in member.name or '/share/man/' in member.name or '/share/gtk-doc/' in member.name:
                continue
            # data filter prevents unsafe paths/symlinks in downloaded archives.
            archive.extract(member, a.output, filter='data')
app = a.output/'app'
shutil.copytree(ROOT/'gui', app, ignore=shutil.ignore_patterns('__pycache__','tests','helpers'))
sdl = a.sdl_build/'SDL3.dll'
if not sdl.is_file():
    raise SystemExit('Build SDL first with windows/build.sh')
shutil.copy2(sdl, app/'SDL3.dll')
for name in ('Install.ps1', 'Run-Patch.ps1', 'Bluetooth.ps1'):
    shutil.copy2(ROOT/'windows'/name, app/name)
shutil.copy2(ROOT/'windows/README.md', a.output/'README.md')
shutil.copy2(a.sdl_build/'SDL-LICENSE.txt', a.output/'SDL-LICENSE.txt')
shutil.copy2(a.sdl_build/'Vader5Control.exe', a.output/'Vader5Control.exe')
shutil.copy2(ROOT/'windows/Launch.cmd', a.output/'Launch.cmd')
shutil.copy2(ROOT/'windows/Diagnose-Startup.cmd', a.output/'Diagnose-Startup.cmd')
(a.output/'runtime-packages.json').write_text(json.dumps({
    'repository': MIRROR, 'database_sha256': hashlib.sha256(database.read_bytes()).hexdigest(),
    'packages': list(selected.values())}, indent=2)+'\n')
# The schema cache is portable between little-endian Linux and Windows.
# MSYS2 package install hooks are not run while extracting archives.
subprocess.run(['glib-compile-schemas', str(a.output/'ucrt64/share/glib-2.0/schemas')], check=True)
prune_runtime(a.output)
zip_path = a.output.with_suffix('.zip')
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(a.output.rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(a.output.parent))
sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
zip_path.with_suffix('.zip.sha256').write_text(f'{sha}  {zip_path.name}\n')
print(f'Portable bundle: {zip_path} ({zip_path.stat().st_size/1048576:.1f} MiB)', flush=True)
