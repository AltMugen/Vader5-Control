"""Add the opt-in Flashplay backend to an already USB-patched SDL 3.4.4 tree."""
import argparse
from pathlib import Path
import shutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--platform', choices=('linux', 'windows'), required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
source = args.source
platform = args.platform
folder = source / 'src/joystick' / platform
for name in ('SDL_flydigi_flashplay.c', 'SDL_flydigi_flashplay_windows.h', 'SDL_flydigi_flashplay_bluez.h'):
    shutil.copyfile(root / 'src/flashplay' / name, folder / name)
p = source / 'src/joystick/SDL_joystick.c'
s = p.read_text()
if 'SDL_FLYDIGI_FLASHPLAY_JoystickDriver' in s:
    raise SystemExit('Flashplay backend already registered; use a clean SDL tree')
needle = 'static SDL_JoystickDriver *SDL_joystick_drivers[] = {'
s = s.replace(needle, '#if defined(SDL_JOYSTICK_LINUX) || defined(SDL_PLATFORM_WINDOWS)\n'
    'extern SDL_JoystickDriver SDL_FLYDIGI_FLASHPLAY_JoystickDriver;\n#endif\n\n' + needle + '\n'
    '#if defined(SDL_JOYSTICK_LINUX) || defined(SDL_PLATFORM_WINDOWS)\n'
    '    &SDL_FLYDIGI_FLASHPLAY_JoystickDriver,\n#endif', 1)
p.write_text(s)
if platform == 'windows':
    p = source / 'src/joystick/hidapi/SDL_hidapi_flydigi.c'
    s = p.read_text()
    s = s.replace('#ifdef SDL_JOYSTICK_HIDAPI_FLYDIGI\n',
                  '#ifdef SDL_JOYSTICK_HIDAPI_FLYDIGI\n#include "vader5-xinput.h"\n', 1)
    s = s.replace('return device->vendor_id == USB_VENDOR_FLYDIGI_V2 && device->interface_number == 1;',
                  'return device->vendor_id == USB_VENDOR_FLYDIGI_V2 && '
                  '(device->usage_page == 0xffa0 || (device->usage_page == 0 && device->interface_number == 1));')
    s = s.replace('return SDL_Unsupported();\n#endif\n}\n\nstatic bool HIDAPI_DriverFlydigi_RumbleJoystick',
                  'return SDL_Vader5WindowsRumble(low, high);\n#endif\n}\n\n'
                  'static bool HIDAPI_DriverFlydigi_RumbleJoystick', 1)
    p.write_text(s)
    shutil.copyfile(root / 'windows/vader5-xinput.h', p.parent / 'vader5-xinput.h')
    shim = source / 'src/joystick/windows/SDL_vader5_steam.c'
    shim.write_text('#include "SDL_internal.h"\n#include <SDL3/SDL_joystick.h>\n'
                    '__declspec(dllexport) int SDLCALL SDL_TryLockJoysticks(void) '
                    '{ SDL_LockJoysticks(); return 1; }\n')
    with (source / 'CMakeLists.txt').open('a') as f:
        f.write('\nif(TARGET SDL3-shared)\n'
                '  target_link_libraries(SDL3-shared PRIVATE bluetoothapis setupapi)\nendif()\n')
