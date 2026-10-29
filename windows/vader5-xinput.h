/* Vader5 Control, zlib license. Native Windows Xbox rumble; no USB driver replacement. */
#include "../../core/windows/SDL_windows.h"
#include "../../core/windows/SDL_xinput.h"

static bool SDL_Vader5WindowsRumble(Uint8 left, Uint8 right)
{
    HMODULE dll = LoadLibraryExW(L"XInput1_4.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    XInputGetCapabilitiesEx_t caps;
    XInputSetState_t rumble;
    DWORD selected = XUSER_MAX_COUNT;
    int matches = 0;
    if (!dll) return SDL_SetError("XInput 1.4 unavailable");
    caps = (XInputGetCapabilitiesEx_t)GetProcAddress(dll, (LPCSTR)108);
    rumble = (XInputSetState_t)GetProcAddress(dll, "XInputSetState");
    if (caps && rumble) {
        for (DWORD slot = 0; slot < XUSER_MAX_COUNT; ++slot) {
            SDL_XINPUT_CAPABILITIES_EX info;
            SDL_zero(info);
            if (caps(1, slot, 0, &info) == ERROR_SUCCESS && info.VendorId == 0x37d7 && info.ProductId == 0x2401) {
                selected = slot; ++matches;
            }
        }
        if (matches == 1) {
            XINPUT_VIBRATION value = {(WORD)(left * 257), (WORD)(right * 257)};
            DWORD result = rumble(selected, &value);
            FreeLibrary(dll);
            return result == ERROR_SUCCESS ? true : SDL_SetError("Vader 5 XInput rumble failed: %lu", (unsigned long)result);
        }
    }
    FreeLibrary(dll);
    return SDL_SetError("Cannot identify a unique Vader 5 XInput slot");
}
