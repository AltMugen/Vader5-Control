#ifndef UNICODE
#define UNICODE
#endif
#define _UNICODE
#include <windows.h>
#include <wchar.h>
#include <stdlib.h>

static wchar_t root[32768];
static void environment(const wchar_t *key, const wchar_t *suffix) {
    wchar_t value[32768];
    _snwprintf(value, 32768, L"%ls\\%ls", root, suffix);
    SetEnvironmentVariableW(key, value);
}
int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, LPWSTR args, int show) {
    (void)instance; (void)previous; (void)args; (void)show;
    if (!GetModuleFileNameW(NULL, root, 8000)) return 1;
    wchar_t *slash = wcsrchr(root, L'\\');
    if (!slash) return 1;
    *slash = 0;
    wchar_t python[32768], command[32768], path[32768], old_path[16000] = {0};
    _snwprintf(python, 32768, L"%ls\\ucrt64\\bin\\pythonw.exe", root);
    _snwprintf(command, 32768, L"\"%ls\" \"%ls\\app\\app.py\"", python, root);
    GetEnvironmentVariableW(L"PATH", old_path, 16000);
    _snwprintf(path, 32768, L"%ls\\ucrt64\\bin;%ls", root, old_path);
    SetEnvironmentVariableW(L"PATH", path);
    environment(L"PYTHONHOME", L"ucrt64");
    environment(L"GI_TYPELIB_PATH", L"ucrt64\\lib\\girepository-1.0");
    environment(L"XDG_DATA_DIRS", L"ucrt64\\share");
    environment(L"GSETTINGS_SCHEMA_DIR", L"ucrt64\\share\\glib-2.0\\schemas");
    environment(L"FONTCONFIG_PATH", L"ucrt64\\etc\\fonts");
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"GSK_RENDERER", L"cairo");
    SetEnvironmentVariableW(L"GDK_BACKEND", L"win32");
    SetEnvironmentVariableW(L"GSETTINGS_BACKEND", L"keyfile");
    STARTUPINFOW startup = {0}; startup.cb = sizeof(startup);
    PROCESS_INFORMATION process = {0};
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, CREATE_NO_WINDOW,
                        NULL, root, &startup, &process)) {
        wchar_t error[256];
        _snwprintf(error, 256, L"Unable to start Vader5 Control (Windows error %lu).\nExtract the entire archive before starting.", GetLastError());
        MessageBoxW(NULL, error, L"Vader5 Control", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hProcess);
    if (code) MessageBoxW(NULL, L"The application could not start. Run Launch.cmd to see the error.",
                          L"Vader5 Control", MB_OK | MB_ICONERROR);
    return (int)code;
}
