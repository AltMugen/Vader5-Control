[English](#english) | [**Русская версия ↓**](#russian)

<p align="center">
  <img src="gui/assets/vader5-control.png" width="192" alt="Vader5 Control">
</p>

<h1 align="center">Vader5 Control</h1>

---

## English

Configuration utility and SDL3 fixes for **Flydigi Vader 5 Pro** on Linux and Windows (2.4G dongle USB ID `37d7:2401`). Continuation of [flydigi-vader5-pro-linux](https://github.com/AltMugen/flydigi-vader5-pro-linux).

### What this repository includes

- **Controller configuration**: lighting, firmware and battery status, third-party software access, and a tester for buttons, sticks, triggers and available motion sensors.
- **Lighting editor**: standard effects, independent colors for 10 channels, animations of up to 10 frames, a brush and local presets. Lighting is saved to the controller and works after closing the application.
- **SDL3 rumble fix**: grip rumble through the dongle's Xbox interface on Linux and Windows, corrected HID command framing, and Steam RT3 integration.
- **Bluetooth Flashplay**: extra buttons, analog triggers and two grip-rumble channels through the patched SDL. This backend is experimental; Steam connections can drop.
- **Linux switcher (`vader5`)**: Steam Native / Padctl switching, automatic Padctl installation and profile editing.

### Input and rumble

Support for the extra buttons and gyro through the dongle is already present in [upstream SDL 3.4.4](https://github.com/libsdl-org/SDL/blob/release-3.4.4/src/joystick/hidapi/SDL_hidapi_flydigi.c). The patch corrects HID command framing and rumble routing. Input is read through **HID interface 1**. On Linux, grip rumble is sent through **Xbox interface 0** by the `vader5-rumble` user service. The `xpad` driver is detached from that interface so Steam does not see a second controller. On Windows, rumble uses the same Xbox path through the system XInput API (`XInputSetState`), without replacing the USB driver. The configurator does not need to stay open for rumble to work.

The trigger motors are separate from the two grip motors. The experimental vibration page can enable them, adjust the strength of all four motors and configure the controller's built-in effect: **a trigger vibrates while it is pressed and the main rumble is active**. This does not require games to send a separate trigger-rumble effect. A direct four-motor test is also available through the dongle.

Motor settings currently apply to controller memory; persistence after power-off is not guaranteed. They use the legacy 7.1 profile format. Writing incompatible 7.2 profiles is blocked.

### Installation — Linux

Download and extract the Linux x86_64 archive from [Releases](https://github.com/AltMugen/Vader5-Control/releases).

Requires Python 3.11+, GTK 4.10+, libadwaita 1.5+, PyGObject, pycairo and librsvg. Use a distribution release that provides these versions.

- **Fedora / Nobara**:
  ```bash
  sudo dnf install python3 python3-gobject python3-cairo gtk4 libadwaita librsvg2 libusb1 dbus-libs curl wget tar
  ```
- **Ubuntu / Debian**:
  ```bash
  sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-rsvg-2.0 libusb-1.0-0 libdbus-1-3 curl wget tar
  ```
- **Arch Linux / Manjaro / EndeavourOS**:
  ```bash
  sudo pacman -S --needed python python-gobject python-cairo gtk4 libadwaita librsvg libusb dbus curl wget tar
  ```

Close Steam, then run inside the extracted folder:

```bash
./install-prebuilt.sh
./gui/install.sh
```

Launch **Vader5 Control** from the application menu or run `vader5-control`.

The installer includes Padctl by default. To skip it, use `SKIP_PADCTL=1 ./install-prebuilt.sh`. Building SDL from source and additional installation details are described in [gui/README.md](gui/README.md) and [build.sh](build.sh).

### Important Note About Padctl Configuration

Padctl needs separate configuration for custom button mappings, macros and stick curves.

- Its default configuration behaves like an Xbox Elite Series 2 controller.
- Edit `~/.config/padctl/config.toml` from the Padctl page or use the `padctl` CLI.
- See the official [Padctl documentation](https://github.com/BANANASJIM/padctl).

### Installation — Windows

Download the **windows_experimental** x64 archive from [Releases](https://github.com/AltMugen/Vader5-Control/releases), extract it completely and run **Vader5Control.exe**. Python and GTK are included; MSYS2 installation is unnecessary. If startup fails, run `Launch.cmd` to see the error.

Windows 10 / 11 x64 is supported. Steam patch installation, backups and restoration are described in [windows/README.md](windows/README.md).

### Steam patch

Close Steam and select **Apply Steam patch** in Overview.

On Linux, the patched SDL lives under `~/.local/share/vader5-driver/sdl`. The Steam launcher loads it for Steam RT3 (`steamrt64`) and the legacy 64-bit client. Steam's own libraries remain in place, so verifying or updating Steam does not overwrite the private SDL.

`vader5 update` configures the terminal launcher and the existing Steam desktop shortcut. The launcher is `~/.local/bin/steam`; `~/.local/bin` must precede `/usr/bin` in `PATH`. Directly running `/usr/bin/steam` bypasses it. Root is needed for udev rules and mode switching, not for files owned by the current user.

On Windows, the installer finds Steam through Valve's registry entries, including installations on other drives. It backs up the original x64 client SDL3.dll files outside Steam and preserves their length when replacing them. A Steam update may require reapplying the patch.

### Bluetooth Flashplay

For the first connection, close Steam, disconnect the controller from the phone and turn it on in **Flashplay** mode. In Overview, select **Connect Bluetooth → Find controller**, choose the controller and connect. Close the configurator before using Steam. The selected device is saved locally; no controller MAC is compiled into SDL.

After setup, launch Steam normally with the patch installed. The patched SDL connects directly to the controller. Only one process can use this Flashplay connection at a time.

The default stream delivers about **100 reports/s**. Extra buttons, sticks, analog triggers and grip rumble are supported. Full three-axis gyro, separate trigger rumble and hardware configuration over Bluetooth are not available. **Steam connections can drop; Bluetooth remains experimental.**

### Hardware settings

Use the **USB dongle** for configuration. Close Steam, Space Station and Padctl before reading or writing settings. The controller's third-party software access setting can be read and changed from Overview.

Lighting includes wave, breathing, gradient, static, factory effect and off, as well as per-channel colors and custom frames. Read the current lighting, edit it and select **Apply** to save it to the controller. Local presets allow switching between saved effects. **Restore original** returns the lighting first read during the current session.

The firmware's lighting-save command also commits the active profile's current mappings and macros. The application makes backups before writing.

Stick, trigger and vibration pages are enabled under **About → Experimental settings**. Availability depends on firmware and input mode. The current extended Native SDL stream bypasses the late onboard stick curves; Linux therefore shows those curves as read-only. Trigger curves and earlier hardware filters are handled separately.

The SDL driver requires firmware **7.1.4.1** or newer. Profile writes target the legacy 7.1 format; incompatible 7.2 writes are blocked. The application does not flash firmware. Battery is reported in discrete levels rather than an exact percentage.

### CLI Usage (`vader5`, Linux)

```bash
vader5 native   # or vader5 n — switch to Steam Native mode
vader5 padctl   # or vader5 p — switch to Padctl mode
vader5 update   # or vader5 u — configure the Steam SDL launcher
vader5 status   # or vader5 s — show the current mode
```

### Credits & References

- [BANANASJIM/padctl](https://github.com/BANANASJIM/padctl) — research on the Vader 5 Pro dongle and its HID input interface.
- [firefloc, vader5-pro-linux-fix issue #8](https://github.com/DuncanTPerkins/vader5-pro-linux-fix/issues/8) — the original Steam SDL replacement and file-size adjustment method.
- [SDL](https://github.com/libsdl-org/SDL) — controller input library.

---

<a id="russian"></a>

## Русский

Программа настройки и исправления SDL3 для **Flydigi Vader 5 Pro** на Linux и Windows (2.4G-донгл, USB ID `37d7:2401`). Продолжение [flydigi-vader5-pro-linux](https://github.com/AltMugen/flydigi-vader5-pro-linux).

### Что входит в репозиторий

- **Настройка геймпада**: подсветка, чтение прошивок и заряда, доступ сторонних приложений, тестер кнопок, стиков, триггеров и доступных датчиков движения.
- **Редактор подсветки**: стандартные эффекты, независимые цвета 10 каналов, анимации до 10 кадров, кисть и локальные пресеты. Подсветка сохраняется в геймпаде и работает после закрытия программы.
- **Фикс вибрации SDL3**: вибрация рукояток через Xbox-интерфейс донгла в Linux и Windows, исправление формата HID-команд и интеграция со Steam RT3.
- **Bluetooth Flashplay**: дополнительные кнопки, аналоговые триггеры и два канала вибрации рукояток через пропатченную SDL. Подключение экспериментальное; в Steam возможны обрывы связи.
- **Утилита переключения (`vader5`) для Linux**: Steam Native / Padctl, автоматическая установка Padctl и редактирование профилей.

### Ввод и вибрация

Дополнительные кнопки и гироскоп через донгл уже поддерживаются в [стандартной SDL 3.4.4](https://github.com/libsdl-org/SDL/blob/release-3.4.4/src/joystick/hidapi/SDL_hidapi_flydigi.c). Патч исправляет формат HID-команд и отправку вибрации. Ввод читается через **HID-интерфейс 1**. В Linux вибрация рукояток отправляется через **Xbox-интерфейс 0** пользовательским сервисом `vader5-rumble`. Драйвер `xpad` отключается от этого интерфейса, чтобы Steam не видел второй геймпад. В Windows используется тот же Xbox-путь через системный XInput (`XInputSetState`), без замены USB-драйвера. Держать конфигуратор открытым для работы вибрации не нужно.

Моторы триггеров работают отдельно от двух основных моторов. На экспериментальной вкладке вибрации можно включить их, настроить силу всех четырёх моторов и штатный зависимый эффект: **триггер вибрирует, когда он нажат и работает основная вибрация**. Отдельная поддержка триггерной вибрации со стороны игры для этого не нужна. Через донгл также доступна прямая проверка четырёх моторов.

Настройки моторов пока применяются в память геймпада; сохранение после выключения не гарантируется. Используется прежний формат профилей 7.1. Запись несовместимых профилей 7.2 заблокирована.

### Установка — Linux

Скачайте и распакуйте архив Linux x86_64 из [Releases](https://github.com/AltMugen/Vader5-Control/releases).

Нужны Python 3.11+, GTK 4.10+, libadwaita 1.5+, PyGObject, pycairo и librsvg. В выбранном выпуске дистрибутива должны быть доступны эти версии.

- **Fedora / Nobara**:
  ```bash
  sudo dnf install python3 python3-gobject python3-cairo gtk4 libadwaita librsvg2 libusb1 dbus-libs curl wget tar
  ```
- **Ubuntu / Debian**:
  ```bash
  sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-rsvg-2.0 libusb-1.0-0 libdbus-1-3 curl wget tar
  ```
- **Arch Linux / Manjaro / EndeavourOS**:
  ```bash
  sudo pacman -S --needed python python-gobject python-cairo gtk4 libadwaita librsvg libusb dbus curl wget tar
  ```

Закройте Steam и выполните из распакованной папки:

```bash
./install-prebuilt.sh
./gui/install.sh
```

Запуск — **Vader5 Control** в меню приложений или команда `vader5-control`.

Установщик по умолчанию устанавливает Padctl. Если он не нужен, используйте `SKIP_PADCTL=1 ./install-prebuilt.sh`. Дополнительные сведения об установке находятся в [gui/README.md](gui/README.md), сборка SDL из исходников — в [build.sh](build.sh).

### Важное примечание по настройке Padctl

Для собственных назначений кнопок, макросов и кривых стиков Padctl нужно настроить отдельно.

- По умолчанию он работает как Xbox Elite Series 2.
- Редактируйте `~/.config/padctl/config.toml` на вкладке Padctl или используйте CLI `padctl`.
- Синтаксис настроек описан в официальной [документации Padctl](https://github.com/BANANASJIM/padctl).

### Установка — Windows

Скачайте архив **windows_experimental** x64 из [Releases](https://github.com/AltMugen/Vader5-Control/releases), распакуйте целиком и запустите **Vader5Control.exe**. Python и GTK уже внутри; устанавливать MSYS2 не нужно. При ошибке запуска откройте `Launch.cmd`, чтобы увидеть её текст.

Поддерживается Windows 10 / 11 x64. Установка патча Steam, резервные копии и восстановление описаны в [windows/README.md](windows/README.md).

### Патч Steam

Закройте Steam и нажмите **«Применить патч Steam»** в «Обзоре».

В Linux пропатченная SDL хранится в `~/.local/share/vader5-driver/sdl`. Запускатель Steam загружает её для Steam RT3 (`steamrt64`) и старого 64-битного клиента. Оригинальные библиотеки Steam остаются на месте: проверка файлов и обновление Steam не перезаписывают отдельную SDL.

`vader5 update` настраивает запуск из терминала и существующий ярлык Steam. Запускатель находится в `~/.local/bin/steam`; каталог `~/.local/bin` должен идти в `PATH` перед `/usr/bin`. Прямой запуск `/usr/bin/steam` обходит его. Root нужен для правил udev и переключения режимов; для файлов текущего пользователя он не требуется.

В Windows установщик находит Steam по реестру Valve, в том числе на других дисках. Оригинальные x64-библиотеки SDL3.dll клиента сохраняются за пределами Steam; при замене сохраняется исходная длина файла. После обновления Steam патч может потребоваться применить повторно.

### Bluetooth Flashplay

Для первого подключения закройте Steam, отключите геймпад от телефона и включите его в режиме **Flashplay**. В «Обзоре» нажмите **«Подключить Bluetooth» → «Найти геймпад»**, выберите устройство и подключитесь. Перед использованием Steam закройте конфигуратор. Выбор устройства сохраняется локально; MAC геймпада в SDL не зашит.

После настройки запускайте Steam обычным способом с установленным патчем. Пропатченная SDL подключается к геймпаду напрямую. Одновременно это Flashplay-соединение может использовать только один процесс.

По умолчанию поток выдаёт около **100 отчётов/с**. Работают дополнительные кнопки, стики, аналоговые триггеры и вибрация рукояток. Полного трёхосевого гироскопа, отдельной вибрации триггеров и аппаратной настройки по Bluetooth пока нет. **В Steam возможны обрывы связи; Bluetooth остаётся экспериментальным.**

### Аппаратные настройки

Настройка выполняется через **USB-донгл**. Перед чтением и записью закройте Steam, Space Station и Padctl. Доступ сторонних приложений можно считать и изменить в «Обзоре».

Подсветка включает волну, дыхание, градиент, статику, заводской эффект и выключение, а также независимые цвета каналов и собственные кадры. Считайте текущую подсветку, отредактируйте и нажмите **«Применить»** для сохранения в геймпад. Локальные пресеты позволяют переключать сохранённые эффекты. **«Вернуть исходное»** восстанавливает подсветку, впервые прочитанную в текущем сеансе.

Штатная команда сохранения подсветки также сохраняет текущие назначения и макросы активного профиля. Перед записью программа делает резервные копии.

Вкладки стиков, триггеров и вибрации включаются через **«О программе» → «Экспериментальные настройки»**. Доступность зависит от прошивки и режима ввода. Текущий расширенный Native-поток SDL обходит поздние аппаратные кривые стиков, поэтому в Linux они доступны только для чтения. Кривые триггеров и ранние аппаратные фильтры обрабатываются отдельно.

Для SDL-драйвера нужна прошивка **7.1.4.1** или новее. Запись профилей рассчитана на прежний формат 7.1; несовместимая запись в 7.2 заблокирована. Программа не перепрошивает геймпад. Заряд отображается уровнями, а не точным процентом.

### Использование (`vader5`, Linux)

```bash
vader5 native   # или vader5 n — включить нативный режим Steam
vader5 padctl   # или vader5 p — включить режим Padctl
vader5 update   # или vader5 u — настроить запуск Steam с патчем SDL
vader5 status   # или vader5 s — показать текущий режим
```

### Благодарности и ссылки

- [BANANASJIM/padctl](https://github.com/BANANASJIM/padctl) — исследование донгла Vader 5 Pro и его HID-интерфейса ввода.
- [firefloc, vader5-pro-linux-fix issue #8](https://github.com/DuncanTPerkins/vader5-pro-linux-fix/issues/8) — исходный метод подмены SDL в Steam с подгонкой размера файла.
- [SDL](https://github.com/libsdl-org/SDL) — библиотека ввода.
