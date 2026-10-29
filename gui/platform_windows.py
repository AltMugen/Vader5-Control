"""Windows integrations. Steam location is read from Valve's registry entries."""
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import winreg

ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
DATA = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))


def steam_directory():
    override = os.environ.get('VADER5_STEAM_DIR')
    candidates = [override] if override else []
    for hive, key, value in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                              (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamExe'),
                              (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath'),
                              (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as handle:
                    path = Path(winreg.QueryValueEx(handle, value)[0])
                    candidates.append(str(path.parent if value == 'SteamExe' else path))
            except OSError:
                pass
    for path in candidates:
        if path and (Path(path) / 'steam.exe').is_file():
            return Path(path)
    return None


def steam_running():
    # CSV avoids localized tasklist headings.
    import csv
    result = subprocess.run(['tasklist.exe', '/FI', 'IMAGENAME eq steam.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip()
                           or 'Unable to query running processes')
    # Process names are ASCII even when tasklist's informational text uses OEM.
    output = result.stdout.decode('ascii', errors='replace')
    return any(row and row[0].lower() == 'steam.exe' for row in csv.reader(output.splitlines()))


def devices():
    from hid_windows import endpoints
    return [{'path': key, 'name': 'Flydigi Vader 5 Pro', 'connection': 'USB receiver'}
            for key, path in endpoints()]


def patch_status():
    steam = steam_directory()
    if steam is None:
        return None
    state_path = DATA / 'Vader5Control/SteamBackups/state.json'
    if not state_path.exists():
        return False
    try:
        state = json.loads(state_path.read_text(encoding='utf-8-sig'))
        if isinstance(state, dict):
            state = [state]
        entries = [item for item in state if Path(item['Target']).is_relative_to(steam)]
        return bool(entries) and all(Path(e['Target']).is_file() and
            hashlib.sha256(Path(e['Target']).read_bytes()).hexdigest().upper() == e['PatchedHash'].upper()
            for e in entries)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def console(action):
    if action != 'update':
        raise ValueError('Windows supports only the Steam patch action')
    # Start-Process requests UAC only for the installer, the GUI stays unelevated.
    script = ROOT / 'Install.ps1'
    runner = ROOT / 'Run-Patch.ps1'
    args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(runner),
            '-Installer', str(script)]
    steam = steam_directory()
    if steam:
        args += ['-SteamDir', str(steam)]
    return subprocess.run(args, capture_output=True, encoding='utf-8', errors='replace', timeout=600,
                          creationflags=subprocess.CREATE_NO_WINDOW)
