"""Remove development tools and unused data from the portable GTK runtime."""
import hashlib
import json
from pathlib import Path
import shutil


SHARE_TOOLS = {
    'aclocal', 'applications', 'bash-completion', 'cmake', 'directx-headers',
    'directxmath', 'doc', 'gdb', 'gettext', 'gir-1.0', 'graphite2', 'gtk-doc',
    'info', 'man', 'metainfo', 'pkgconfig', 'tabset', 'terminfo',
    'thumbnailers', 'vala', 'zoneinfo', 'zsh',
}
PYTHON_TOOLS = {'test', 'ensurepip', 'idlelib', 'tkinter', 'turtledemo',
                'venv', 'Tools', 'config-3.14'}
TCL_PACKAGES = {'dde1.4', 'itcl4.3.7', 'reg1.3', 'sqlite3.54.0', 'tcl8',
                'tcl8.6', 'tdbc1.1.13', 'tdbcmysql1.1.13', 'tdbcodbc1.1.13',
                'tdbcpostgres1.1.13', 'thread2.8.13', 'tk8.6'}


def prune_runtime(bundle):
    bundle = Path(bundle)
    runtime = bundle / 'ucrt64'
    if not (runtime / 'bin/python.exe').is_file():
        raise ValueError('Expected a portable UCRT64 Python runtime')
    required = [runtime / name for name in (
        'bin/python.exe', 'bin/pythonw.exe', 'bin/libpython3.14.dll',
        'bin/libgtk-4-1.dll', 'bin/libadwaita-1-0.dll', 'bin/librsvg-2-2.dll',
        'lib/girepository-1.0/Gtk-4.0.typelib',
        'lib/girepository-1.0/Adw-1.typelib',
        'share/glib-2.0/schemas/gschemas.compiled')]
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in required}
    before = sum(path.stat().st_size for path in runtime.rglob('*') if path.is_file())
    removed = []

    def remove(path, reason):
        if not path.exists():
            return
        size = (sum(item.stat().st_size for item in path.rglob('*') if item.is_file())
                if path.is_dir() else path.stat().st_size)
        removed.append({'path': path.relative_to(runtime).as_posix(),
                        'bytes': size, 'reason': reason})
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    for name in SHARE_TOOLS:
        remove(runtime / 'share' / name, 'Development data or console-tool resources')
    for name in TCL_PACKAGES | {'cmake', 'pkgconfig', 'gettext', 'terminfo'}:
        remove(runtime / 'lib' / name, 'Unused development or Tcl/Tk package')
    for name in ('tclConfig.sh', 'tkConfig.sh'):
        remove(runtime / 'lib' / name, 'Tcl/Tk build configuration')
    for path in sorted((runtime / 'bin').iterdir()):
        if path.is_file() and path.suffix.lower() != '.dll' and path.name not in ('python.exe', 'pythonw.exe'):
            remove(path, 'Standalone tool; application uses the Python launchers only')
    # Keep binary typelibs, DLLs, icons, fonts, schemas, image loaders and licenses.
    for path in sorted((runtime / 'share/locale').iterdir()):
        language = path.name.split('_')[0].split('@')[0].lower()
        if path.is_dir() and language not in ('ru', 'en', 'c', 'posix'):
            remove(path, 'Translation outside the supported RU/EN languages')
    emoji = runtime / 'share/gtk-4.0/emoji'
    if emoji.is_dir():
        for path in sorted(emoji.glob('*.gresource')):
            if path.stem not in ('ru', 'en'):
                remove(path, 'Unused emoji translation')
    python = runtime / 'lib/python3.14'
    for name in PYTHON_TOOLS:
        remove(python / name, 'Python tests or unused interactive/development tool')
    for name in ('_tkinter.pyd',):
        remove(python / 'lib-dynload' / name, 'Tcl/Tk binding is not used by the GTK application')
    for path in sorted(runtime.rglob('*.pdb')):
        remove(path, 'Debug symbols')
    for path, expected in hashes.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Required runtime file changed: {path}')
    after = sum(path.stat().st_size for path in runtime.rglob('*') if path.is_file())
    report = {'runtime_bytes_before': before, 'runtime_bytes_after': after,
              'removed_bytes': before - after, 'languages': ['ru', 'en'],
              'removed': sorted(removed, key=lambda item: item['path'])}
    (bundle / 'runtime-pruning.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
