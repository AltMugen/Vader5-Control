"""Local integrations. No device writes occur during discovery."""
import ctypes as C
import ctypes.util
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import tomllib
from protocol import firmware_string, DeviceError

WINDOWS = os.name == 'nt'
HOME = Path.home()
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config'))
DATA = Path(os.environ.get('XDG_DATA_HOME', HOME / '.local/share'))


def run(args, timeout=10, env=None):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)


def active(unit):
    if WINDOWS:
        return False
    return run(['systemctl', '--user', 'is-active', '--quiet', unit]).returncode == 0


def devices():
    if WINDOWS:
        from platform_windows import devices as windows_devices
        return windows_devices()
    result = []
    for p in Path('/sys/bus/usb/devices').glob('*'):
        try:
            vendor = (p / 'idVendor').read_text(encoding='utf-8').strip()
            product = (p / 'product').read_text(encoding='utf-8').strip()
            if vendor == '37d7' and ((p / 'idProduct').read_text(encoding='utf-8').strip() == '2401' or 'vader5' in product.lower().replace(' ', '')):
                result.append({'path': str(p), 'name': product, 'connection':
                               'USB receiver' if (p / 'idProduct').read_text(encoding='utf-8').strip() == '2401' else 'USB'})
        except OSError:
            continue
    return result


def mappings():
    found = {}
    for base in [Path('/usr/share/padctl/mappings'), Path('/etc/padctl/mappings'), CONFIG / 'padctl/mappings']:
        for path in sorted(base.glob('*.toml')):
            try:
                name = tomllib.loads(path.read_text(encoding='utf-8')).get('name', path.stem)
                found[name] = path
            except (OSError, tomllib.TOMLDecodeError):
                pass
    return found


def save_mapping(name, content):
    known = mappings()
    if name not in known:
        raise ValueError('Unknown mapping')
    parsed = tomllib.loads(content)
    if parsed.get('name') != name:
        raise ValueError('Keep the profile name unchanged')
    directory = CONFIG / 'padctl/mappings'
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', dir=directory, delete=False) as f:
        f.write(content)
        temp = Path(f.name)
    try:
        checked = run(['padctl', '--validate', str(temp)])
        if checked.returncode:
            raise ValueError(checked.stderr or checked.stdout or 'Padctl validation failed')
        # User overrides leave system mappings intact. Validation precedes atomic replacement.
        temp.replace(directory / known[name].name)
    finally:
        temp.unlink(missing_ok=True)


def patch_status():
    if WINDOWS:
        from platform_windows import patch_status as windows_patch_status
        return windows_patch_status()
    root = Path(os.environ.get('VADER5_DRIVER_DIR', HOME / '.local/share/vader5-driver/sdl'))
    launcher = HOME / '.local/bin/steam'
    try:
        library = root / 'libSDL3-64.so.0'
        loader = root / 'steam-sdl-loader.so'
        shim = root / 'sdl3_shim64.so'
        if not all(path.is_file() for path in (library, loader, shim)):
            return None
        import shlex
        values = {}
        launcher_text = launcher.read_text(encoding='utf-8')
        for line in launcher_text.splitlines():
            for key in ('export VADER5_PRIVATE_SDL', 'export VADER5_STEAM_ROOT', 'loader'):
                if line.startswith(key + '='):
                    words = shlex.split(line.split('=', 1)[1])
                    if len(words) == 1:
                        values[key] = Path(words[0])
        private = root / 'steam64'
        return (values.get('export VADER5_PRIVATE_SDL') == private / 'libSDL3.so.0'
                and values.get('loader') == loader
                and 'export VADER5_STEAM_ROOT' in values
                and os.access(launcher, os.X_OK)
                and 'export LD_PRELOAD="${LD_PRELOAD:+$LD_PRELOAD:}$loader"' in launcher_text
                and 'exec /usr/bin/steam "$@"' in launcher_text
                and (private / 'libSDL3.so.0').resolve() == library.resolve()
                and (private / 'sdl3_shim.so').resolve() == shim.resolve())
    except (OSError, ValueError):
        return False


def console(action):
    if WINDOWS:
        from platform_windows import console as windows_console
        return windows_console(action)
    if action not in ['native', 'padctl', 'update']:
        raise ValueError('Unsupported action')
    cli = shutil.which('vader5')
    if cli is None:
        candidates = (HOME / '.local/bin/vader5',
                      Path(__file__).resolve().parent.parent / 'vader5')
        cli = next((str(path) for path in candidates
                    if path.is_file() and os.access(path, os.X_OK)), None)
        if cli is None:
            raise FileNotFoundError('Install the vader5 console utility first')
    env = dict(os.environ)
    env['PATH'] = str(Path(__file__).parent / 'helpers') + os.pathsep + env.get('PATH', '')
    env['SUDO_ASKPASS'] = str(Path(__file__).parent / 'askpass.py')
    return run([cli, action], timeout=600, env=env)


def rumble(left, right, duration=.3):
    if WINDOWS:
        if steam_running():
            raise DeviceError('tester_steam')
        from device import test_motors
        return test_motors(left, right, duration=duration)
    if not active('vader5-rumble'):
        raise RuntimeError('Switch to Native mode to use this vibration test')
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
        s.connect('\0vader5-rumble-' + str(os.getuid()))
        s.send(bytes([max(0, min(255, int(left))), max(0, min(255, int(right)))]))
        try:
            threading.Event().wait(duration)
        finally:
            s.send(b'\x00\x00')


class InputReader:
    """SDL is opened only on an explicit tester request and closed on mode changes."""
    raw_keys = ['a', 'b', 'x', 'y', 'select', 'home', 'start', 'ls', 'rs', 'lb', 'rb',
                'm1', 'm2', 'm3', 'm4', 'c', 'z', 'lm', 'rm', 'fn', 'turbo']

    def __init__(self):
        self.sdl = None
        self.pad = None
        self.joy = None
        self.sensors = set()
        self.waiting = False
        self.connect_deadline = 0
        self.bluetooth_address = None

    def bind(self, name, result, *args):
        f = getattr(self.sdl, name)
        f.restype, f.argtypes = result, args
        return f

    def start(self, bluetooth=None, wait=True):
        self.close()
        self.bluetooth_address = bluetooth['address'].casefold() if bluetooth else None
        if active('padctl'):
            raise DeviceError('tester_native')
        if steam_running():
            raise DeviceError('tester_steam')
        lib = DATA / 'vader5-driver/sdl/steam64/libSDL3.so.0'
        if not lib.exists():
            lib = DATA / 'vader5-driver/sdl/libSDL3-64.so.0'
        if WINDOWS:
            lib = Path(__file__).resolve().parent / 'SDL3.dll'
        self.sdl = C.CDLL(str(lib) if lib.exists() else ctypes.util.find_library('SDL3') or 'libSDL3.so.0')
        self.bind('SDL_Init', C.c_bool, C.c_uint32)
        self.bind('SDL_GetError', C.c_char_p)
        self.bind('SDL_QuitSubSystem', None, C.c_uint32)
        self.bind('SDL_GetGamepads', C.POINTER(C.c_uint32), C.POINTER(C.c_int))
        self.bind('SDL_free', None, C.c_void_p)
        self.bind('SDL_GetGamepadNameForID', C.c_char_p, C.c_uint32)
        self.bind('SDL_GetGamepadPathForID', C.c_char_p, C.c_uint32)
        self.bind('SDL_OpenGamepad', C.c_void_p, C.c_uint32)
        self.bind('SDL_CloseGamepad', None, C.c_void_p)
        self.bind('SDL_GetGamepadJoystick', C.c_void_p, C.c_void_p)
        self.bind('SDL_PumpEvents', None)
        self.bind('SDL_GamepadConnected', C.c_bool, C.c_void_p)
        self.bind('SDL_GetNumJoystickButtons', C.c_int, C.c_void_p)
        self.bind('SDL_GetJoystickButton', C.c_bool, C.c_void_p, C.c_int)
        self.bind('SDL_GetJoystickHat', C.c_uint8, C.c_void_p, C.c_int)
        self.bind('SDL_GetGamepadAxis', C.c_int16, C.c_void_p, C.c_int)
        self.bind('SDL_GetGamepadPowerInfo', C.c_int, C.c_void_p, C.POINTER(C.c_int))
        self.bind('SDL_GetGamepadFirmwareVersion', C.c_uint16, C.c_void_p)
        self.bind('SDL_GamepadHasSensor', C.c_bool, C.c_void_p, C.c_int)
        self.bind('SDL_SetGamepadSensorEnabled', C.c_bool, C.c_void_p, C.c_int, C.c_bool)
        self.bind('SDL_GetGamepadSensorData', C.c_bool, C.c_void_p, C.c_int, C.POINTER(C.c_float), C.c_int)
        if bluetooth:
            self.bind('SDL_SetHintWithPriority', C.c_bool, C.c_char_p, C.c_char_p, C.c_int)
            for key, value in (('SDL_FLYDIGI_BT_ADDRESS', bluetooth['address']),
                               ('SDL_FLYDIGI_BT_ADAPTER', bluetooth.get('adapter', ''))):
                if not self.sdl.SDL_SetHintWithPriority(key.encode(), value.encode('ascii'), 2):
                    raise DeviceError('bt_failed')
        if not self.sdl.SDL_Init(0x2000):
            raise RuntimeError(self.sdl.SDL_GetError().decode(errors='replace'))
        self.waiting = True
        self.connect_deadline = time.monotonic() + 15
        if not wait:
            return
        for attempt in range(25):
            if self._open_available():
                return
            time.sleep(.02)
        self.close()
        raise DeviceError('tester_missing')

    def _open_available(self):
        self.sdl.SDL_PumpEvents()
        count = C.c_int()
        ids = self.sdl.SDL_GetGamepads(C.byref(count))
        try:
            for index in range(count.value):
                name = (self.sdl.SDL_GetGamepadNameForID(ids[index]) or b'').decode(errors='replace')
                path = (self.sdl.SDL_GetGamepadPathForID(ids[index]) or b'').decode(errors='replace')
                if self.bluetooth_address and path.casefold() != self.bluetooth_address:
                    continue
                if 'vader5' not in name.lower().replace(' ', ''):
                    continue
                self.pad = self.sdl.SDL_OpenGamepad(ids[index])
                if self.pad:
                    self.joy = self.sdl.SDL_GetGamepadJoystick(self.pad)
                    for sensor in (1, 2):
                        if (self.sdl.SDL_GamepadHasSensor(self.pad, sensor) and
                                self.sdl.SDL_SetGamepadSensorEnabled(self.pad, sensor, True)):
                            self.sensors.add(sensor)
                    self.waiting = False
                    return True
        finally:
            self.sdl.SDL_free(ids)
        return False

    @staticmethod
    def _comm(path):
        try:
            return path.read_text(encoding='utf-8').strip()
        except OSError:
            return ''

    def poll(self):
        if self.waiting and not self._open_available():
            if time.monotonic() >= self.connect_deadline:
                key = 'bt_timeout' if self.bluetooth_address else 'tester_missing'
                self.close()
                raise DeviceError(key)
            return None
        if not self.pad:
            return None
        self.sdl.SDL_PumpEvents()
        if not self.sdl.SDL_GamepadConnected(self.pad):
            self.close()
            return None
        count = self.sdl.SDL_GetNumJoystickButtons(self.joy)
        pressed = {k for i, k in enumerate(self.raw_keys[:count]) if self.sdl.SDL_GetJoystickButton(self.joy, i)}
        hat = self.sdl.SDL_GetJoystickHat(self.joy, 0)
        pressed.update(k for mask, k in [(1, 'up'), (2, 'right'), (4, 'down'), (8, 'left')] if hat & mask)
        axes = [self.sdl.SDL_GetGamepadAxis(self.pad, i) / 32767 for i in range(6)]
        pressed.update(k for i, k in [(4, 'lt'), (5, 'rt')] if axes[i] > .1)
        percent = C.c_int(-1)
        power = self.sdl.SDL_GetGamepadPowerInfo(self.pad, C.byref(percent))
        firmware = self.sdl.SDL_GetGamepadFirmwareVersion(self.pad)
        motion = {}
        for kind, name in [(1, 'accel'), (2, 'gyro')]:
            if kind in self.sensors:
                values = (C.c_float * 3)()
                if self.sdl.SDL_GetGamepadSensorData(self.pad, kind, values, 3):
                    motion[name] = tuple(values)
        return {'motion': motion, 'pressed': pressed, 'axes': axes, 'battery': percent.value if power in (1, 3, 4) and percent.value >= 0 else None,
                'firmware': firmware_string(firmware)}

    def close(self):
        self.waiting = False
        self.bluetooth_address = None
        if self.sdl:
            if self.pad:
                self.sdl.SDL_CloseGamepad(self.pad)
            self.sdl.SDL_QuitSubSystem(0x2000)
        self.sensors.clear()
        self.pad = self.joy = None


def steam_running():
    if WINDOWS:
        from platform_windows import steam_running as windows_steam_running
        return windows_steam_running()
    return any(InputReader._comm(p) == 'steam' for p in Path('/proc').glob('[0-9]*/comm'))


def mode():
    if WINDOWS:
        return 'native'
    return 'padctl' if active('padctl') else 'native' if active('vader5-rumble') else None


if WINDOWS:
    from platform_windows import CONFIG, DATA
