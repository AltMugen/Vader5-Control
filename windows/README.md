# Vader5 Control — Windows

[English](#english) | [Русский](#русский)

## Русский

Переносимая сборка для Windows 10/11 x64. Распакуйте архив целиком и
запустите **Vader5Control.exe**. Python, GTK и SDL уже внутри; устанавливать
MSYS2 не нужно. `Launch.cmd` запускает то же приложение с окном вывода.

По умолчанию доступны «Обзор», «Подсветка» и «О программе». В «О программе» указан автор AltMugen; тумблер экспериментальных настроек открывает стики, триггеры и вибрацию.
Есть RU/EN, светлая и тёмная темы с синим акцентом.
Подсветка сохраняется в геймпад кнопкой «Применить», до 10 кадров по 10 каналов. Команда сохранения прошивки также сохраняет текущие назначения и макросы.
Настройки считываются и записываются напрямую через HID донгла 37d7:2401.
Перед настройкой закройте Steam и Space Station. Версия 7.2 пока закрыта
для записи: её профиль несовместим с редактором 7.1.

Аппаратные настройки и подсветка исполняются контроллером. Приложение
не создаёт виртуальный геймпад, игровые профили обработки или фоновую
службу. Редактор кривых стиков показывает аппаратный профиль; текущий
расширенный SDL-поток получает координаты до его преобразования.

### Патч Steam

В обзоре нажмите **Применить патч Steam**. Права администратора
запрашиваются только для установщика. Steam определяется по реестру Valve:
диск C не обязателен. Заменяются только x64 SDL3.dll в каталогах клиента.
Игровые библиотеки Steam не изменяются.

Ручная установка из PowerShell в папке `app`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1
```

Если Steam не зарегистрирован в реестре:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -SteamDir 'D:\Games\Steam'
```

Оригиналы находятся в `%LOCALAPPDATA%\Vader5Control\SteamBackups`, вне
папки Steam. При замене сохраняется исходная длина файла. Это не гарантия
прохождения всех будущих проверок Steam. После обновления клиента патч
может потребоваться применить повторно.

Восстановление при полностью закрытом Steam:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Action Restore
```

Установщик проверяет контрольные суммы и не заменяет обновлённую Steam
библиотеку старым бэкапом.

### Bluetooth

В «Обзоре» нажмите «Подключить Bluetooth» → «Найти геймпад», выберите контроллер и нажмите «Подключить». Геймпад должен быть включён в Flashplay и отключён от телефона; Steam закройте. Поиск и сопряжение выполняются через WinRT. Выбор сохраняется для следующих запусков.

Для настройки из PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -Action Bluetooth -DeviceAddress 'AA:BB:CC:DD:EE:FF'
```

Укажите MAC своего геймпада один раз. Он сохраняется в `%APPDATA%\Vader5Control\bluetooth`; после этого Steam можно открывать обычным ярлыком. Поддерживаются кнопки, стики, триггеры и
два канала вибрации; по умолчанию 100 отчётов/с. Полный гироскоп Bluetooth
и настройка аппаратного профиля через Bluetooth пока отсутствуют.

## English

Portable Windows 10/11 x64 build. Extract the entire archive and run
**Vader5Control.exe**. Python, GTK and SDL are included; MSYS2 installation
is unnecessary. `Launch.cmd` starts the same app with console output.

Overview/tester, sticks, triggers, lighting and vibration; RU/EN and
light/dark themes. No background service. Hardware settings
use the receiver's 37d7:2401 vendor HID. Close Steam and Space Station before
configuring it. Firmware 7.2 writes remain blocked due to a different format.
The current extended SDL input bypasses onboard stick response curves.

Use **Apply Steam patch** in Overview. Only the installer requests UAC.
Steam is located through Valve's registry entries on any drive. To override,
run `app\Install.ps1 -SteamDir 'D:\Games\Steam'` in PowerShell. Only x64
client SDL3.dll files are patched. Backups live outside Steam under
`%LOCALAPPDATA%\Vader5Control\SteamBackups`; original length is preserved.
Steam updates may require reapplying. Restore with `Install.ps1 -Action Restore`
while Steam is closed; changed files are protected by hash checks.

Flashplay launch: `Install.ps1 -Action Bluetooth -DeviceAddress 'AA:BB:CC:DD:EE:FF'`
after pairing with Windows. Buttons, sticks, triggers and two rumble channels;
100 reports/s by default. Full Bluetooth gyro and hardware configuration over
Bluetooth are unavailable.

## Сборка / Build

On Linux with MinGW-w64, CMake, Ninja, Pillow, curl, glib-compile-schemas and Python 3.14+ (tar.zst support):

```bash
./windows/build.sh
python3 windows/package-portable.py --cache /path/to/download-cache
```

`build.sh` builds SDL and the native launcher with the application icon.
`package-portable.py` downloads official MSYS2 UCRT64 runtime packages,
checks their SHA256 and creates the portable ZIP. `runtime-packages.json`
records exact versions, hashes and upstream sources. Package licenses
are retained under `ucrt64/share/licenses`.

The Bluetooth action now saves the selection under `%APPDATA%\Vader5Control\bluetooth`. Subsequent Steam launches can use the normal shortcut.

## Build 2026-10-29

Lighting Apply now completes the RGB upload and commits the active profile.
The firmware also persists current mappings and macros. Static and custom
frame-animation persistence were checked on firmware 7.1.5.4. The color dialog
is resizable (640×600 by default). Experimental pages are hidden until enabled
in About; author: AltMugen. Both Windows themes use a blue accent. Localized
tasklist output no longer breaks the Bluetooth and vibration actions.

### Update 2026-10-29.2

Color buttons show swatches only. The standard GTK palette opens first.
The frame editor has a brush for clicking or dragging across channels and the
controller light bar. Starting Steam stops the configurator input tester at
the next status refresh so it releases the Bluetooth stream.

### Build 2026-10-29.3

The ten frame-color controls fit in one row. The color dialog opens the GTK
palette first; the brush paints selected channels by click or drag.
The tester closes its connection when Steam is detected.

The included SDL also removes a mandatory read of the firmware's malformed
CCCD response and accepts RX characteristics advertised as Write. It retains
the Write Without Response command procedure required by the audited firmware.
Real Windows reconnection timing remains unverified. Close Steam and reapply
**Apply Steam patch** after updating: replacing the app alone does not replace
Steam's installed SDL3.dll.

После обновления закройте Steam и повторно нажмите **Применить патч Steam**:
новая SDL находится внутри сборки; копирование приложения не обновляет
библиотеку, уже установленную в Steam. Задержку подключения на реальной
Windows ещё нужно проверить.

Bluetooth diagnostics (Command Prompt, from the portable folder):

```bat
set SDL_LOGGING=input=debug
Launch.cmd > "%TEMP%\Vader5Control-Bluetooth.log" 2>&1
```

Close the app to finish the log. It includes GATT stages, HRESULTs, call
latencies and the first input notification. Logging is disabled by default;
it does not record button values. Reproduce one connection before sharing
only the relevant `Flashplay:` lines. For Steam startup diagnostics, its
process must inherit the same SDL_LOGGING setting.

### Slow startup

Receiver enumeration now runs in the status worker. Window construction,
page switching and lighting-control refresh use that worker's snapshot.
A slow HID request therefore does not hold window presentation.

If startup is still slow, run `Diagnose-Startup.cmd`, wait for the window and
close it. `%TEMP%\Vader5Control-Startup.log` records GTK import, window-build
and device-discovery timing. This distinguishes a HID delay from runtime or
font initialization; it does not assume all startup stalls have one cause.
