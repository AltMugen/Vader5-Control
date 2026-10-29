#!/usr/bin/env python3
"""Vader5 Control — native GTK 4/libadwaita settings application."""
import concurrent.futures
import json
import math
import os
from pathlib import Path
import re
import time
import threading
from xml.sax.saxutils import escape

if os.name == 'nt':
    runtime_bin = Path(__file__).resolve().parents[1] / 'ucrt64/bin'
    if runtime_bin.is_dir():
        _runtime_dll_directory = os.add_dll_directory(str(runtime_bin))

_startup_started = time.monotonic()
def startup_trace(stage):
    if os.environ.get('VADER5_STARTUP_TRACE') == '1':
        print(f'{time.strftime("%H:%M:%S")} Startup +{time.monotonic()-_startup_started:.3f}s: {stage}', flush=True)

startup_trace('loading GTK')
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Rsvg', '2.0')
gi.require_foreign('cairo')
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gtk, Rsvg
startup_trace('GTK imports complete')
import backend
import bluetooth_setup
import device
import motors
import lighting
from rgb_editor import FrameEditor
from color_picker import ColorPicker
from input_page import InputSettingsMixin, TRANSLATIONS

ROOT = Path(__file__).resolve().parent
PREFS = backend.CONFIG / 'vader5-control/preferences.json'
USER_PRESETS = backend.CONFIG / 'vader5-control/lighting-presets.json'
STRINGS = {
 'ru': {'overview':'Обзор','lighting':'Подсветка','vibration':'Вибрация','offline':'Не подключён','connected':'Подключён','patch':'Применить патч Steam','read':'Считать данные','stop':'Отключить чтение','battery':'Заряд батареи','firmware':'Прошивки','controller':'Геймпад','receiver':'Приёмник','connection':'Подключение','unknown':'Нет данных','notchecked':'Не проверен','patched':'Установлен','stock':'Требует обновления','apply':'Применить','save':'Сохранить','profile':'Профиль','colors':'Цвета','brightness':'Яркость','speed':'Скорость','default':'По умолчанию','flow':'Радуга','breathing':'Дыхание','gradient':'Градиент','solid':'Статика','off':'Выключить','rgbpending':'Запись RGB ещё не подключена','preset':'Палитра этого режима задана в прошивке','rumble':'Проверить вибрацию','left':'Левая рукоятка','right':'Правая рукоятка','triggers':'Моторы триггеров','triggerpending':'LT и RT: текущий драйвер не предоставляет управление вибрацией триггеров.','rumblehint':'Уровни для короткого тестового импульса. Настройки игровых эффектов не меняются.','saved':'Профиль сохранён и проверен Padctl','empty':'Padctl не установлен или профили не найдены','error':'Ошибка','cancel':'Отмена','busy':'Дождитесь завершения операции','last':'Последняя кнопка: ','light':'Светлая тема','dark':'Тёмная тема','noinput':'—'},
 'en': {'overview':'Overview','lighting':'Lighting','vibration':'Vibration','offline':'Not connected','connected':'Connected','patch':'Apply Steam patch','read':'Read device','stop':'Stop reading','battery':'Battery charge','firmware':'Firmware','controller':'Controller','receiver':'Receiver','connection':'Connection','unknown':'No data','notchecked':'Not checked','patched':'Installed','stock':'Needs updating','apply':'Apply','save':'Save','profile':'Profile','colors':'Colors','brightness':'Brightness','speed':'Speed','default':'Default','flow':'Streaming','breathing':'Breathing','gradient':'Gradient','solid':'Solid','off':'Off','rgbpending':'RGB writes are not connected yet','preset':'This mode uses a firmware palette','rumble':'Test vibration','left':'Left grip','right':'Right grip','triggers':'Trigger motors','triggerpending':'LT and RT: the current driver does not expose trigger vibration control.','rumblehint':'Levels for a short test pulse. Game effects are unchanged.','saved':'Profile saved and validated by Padctl','empty':'Padctl is not installed or no profiles were found','error':'Error','cancel':'Cancel','busy':'Wait for the operation to finish','last':'Last button: ','light':'Light theme','dark':'Dark theme','noinput':'—'}
}

STRINGS['ru'].update({
 'rgbread':'Считать с геймпада', 'rgbapply':'Применить', 'rgbrestore':'Вернуть исходное',
 'rgb_read_tip':'Считывает активный профиль. Первое чтение в этой сессии запоминается для отката.',
 'rgb_apply_tip':'Записывает выбранную подсветку и сверяет её повторным чтением. После выключения может сброситься.',
 'rgb_restore_tip':'Повторно считывает геймпад и возвращает состояние, сохранённое при первом чтении в этой сессии.',
 'rgb_original':'Исходное состояние этой сессии сохранено для отката.',
 'rgb_restored':'Исходная подсветка этой сессии восстановлена.',
 'padctl_guide':'Руководство по конфигам Padctl',
 'reconnect':'Переподключить', 'tester_start':'Запустить тестер', 'tester_stop':'Остановить тестер',
 'receiver_present':'Приёмник подключён; геймпад не проверен',
 'tester_hint':'Нажатия, стики и триггеры обновляются в реальном времени. Гироскоп пока недоступен через текущий SDL-ввод.',
 'preset_list':'Сохранённые подсветки', 'preset_name':'Название новой подсветки', 'preset_save':'Сохранить как',
 'preset_load':'Загрузить', 'preset_delete':'Удалить', 'preset_none':'Нет сохранённых подсветок',
 'preset_saved':'Подсветка сохранена локально. Нажми «Применить», чтобы записать её в геймпад.',
 'preset_deleted':'Сохранённая подсветка удалена.', 'preset_confirm_delete':'Удалить выбранную сохранённую подсветку?',
 'period':'Период эффекта', 'rgbready':'Профиль {profile} · {count} RGB-каналов · Считано с геймпада',
 'rgbdirty':'Есть неприменённые изменения', 'rgbapplied':'Применено и считано обратно · профиль {profile}',
 'rgbhint':'Считай подсветку через USB-донгл. Изменения могут сброситься после выключения геймпада.',
 'rgb_missing':'Совместимый приёмник не найден. Подключи донгл и включи геймпад в режиме донгла.',
 'rgb_no_response':'Приёмник найден, геймпад не отвечает. Проверь режим донгла, разбуди геймпад и закрой Steam/Padctl; затем повтори чтение.',
 'rgb_reading':'Считываю подсветку с геймпада…',
 'rgb_multiple':'Подключено несколько донглов. Оставь один для настройки подсветки.',
 'rgb_permission':'Нет доступа к HID. Выполни vader5 n и переподключи донгл.',
 'rgb_busy':'Подсветку уже настраивает другой экземпляр приложения.',
 'rgb_timeout':'Геймпад не ответил. Разбуди его и закрой Steam и Padctl.',
 'rgb_format':'Формат RGB-конфигурации не поддерживается. Запись остановлена.',
 'rgb_profile':'Профиль геймпада изменился. Считай настройки повторно.',
 'rgb_stale':'Настройки геймпада изменились. Считай их повторно перед применением.',
 'rgb_checksum':'Ошибка контрольной суммы ответа геймпада.',
 'rgb_colors':'Проверь число цветов: 1–5, для градиента — минимум 2.',
 'rgb_write':'Не удалось отправить команду геймпаду.',
 'rgb_verify':'Обратное чтение не совпало с отправленными настройками. Считай подсветку повторно.',
 'rgb_preview':'Анимация предпросмотра не синхронизирована с геймпадом.'})
STRINGS['en'].update({
 'rgbread':'Read from controller', 'rgbapply':'Apply', 'rgbrestore':'Restore original',
 'rgb_read_tip':'Reads the active profile. The first read in this session is saved for restoring.',
 'rgb_apply_tip':'Writes the selected lighting and verifies it by reading it back. It may reset after power-off.',
 'rgb_restore_tip':'Reads the controller again, then restores the state saved by the first read in this session.',
 'rgb_original':'This session’s original state is saved for restoring.',
 'rgb_restored':'This session’s original lighting has been restored.',
 'padctl_guide':'Padctl configuration guide',
 'reconnect':'Reconnect', 'tester_start':'Start tester', 'tester_stop':'Stop tester',
 'receiver_present':'Receiver connected; controller not confirmed',
 'tester_hint':'Button presses, sticks and triggers update in real time. Gyroscope data is not available through the current SDL input path.',
 'preset_list':'Saved lighting', 'preset_name':'Name this lighting preset', 'preset_save':'Save as',
 'preset_load':'Load', 'preset_delete':'Delete', 'preset_none':'No saved lighting presets',
 'preset_saved':'Lighting saved locally. Press Apply to write it to the controller.',
 'preset_deleted':'Saved lighting preset deleted.', 'preset_confirm_delete':'Delete the selected saved lighting preset?',
 'period':'Effect period', 'rgbready':'Profile {profile} · {count} RGB channels · Read from controller',
 'rgbdirty':'Unapplied changes', 'rgbapplied':'Applied and read back · profile {profile}',
 'rgbhint':'Read lighting through the USB receiver. Changes may reset when the controller is powered off.',
 'rgb_missing':'Compatible receiver not found. Connect the USB receiver and turn on the controller in receiver mode.',
 'rgb_no_response':'Receiver found, but the controller did not respond. Check receiver mode, wake it, close Steam/Padctl, then read again.',
 'rgb_reading':'Reading lighting from the controller…',
 'rgb_multiple':'Multiple receivers found. Connect just one to configure lighting.',
 'rgb_permission':'HID access denied. Run vader5 n and reconnect the receiver.',
 'rgb_busy':'Another application instance is configuring lighting.',
 'rgb_timeout':'No response. Wake the controller and close Steam and Padctl.',
 'rgb_format':'Unsupported RGB configuration. Writing was stopped.',
 'rgb_profile':'The controller profile changed. Read its settings again.',
 'rgb_stale':'Controller settings changed. Read them again before applying.',
 'rgb_checksum':'Controller response checksum failed.',
 'rgb_colors':'Use 1–5 colors, or at least 2 for a gradient.',
 'rgb_write':'Could not send the command to the controller.',
 'rgb_verify':'Read-back differs from the requested settings. Read lighting again.',
 'rgb_preview':'Preview animation is not synchronized with the controller.'})
STRINGS['ru'].update({
 'per_led':'Статика по каналам', 'frames':'Покадровая анимация',
 'rgb_transition':'Переход', 'rgb_smooth':'Плавный', 'rgb_play':'▶ Предпросмотр',
 'rgb_pause':'Ⅱ Пауза', 'rgb_duplicate':'Добавить копию кадра', 'rgb_delete':'Удалить кадр',
 'rgb_frame':'Кадр {n}', 'rgb_channel':'Канал {n}', 'rgb_fill':'Этот цвет на все каналы',
 'rgb_order':'Номера обозначают каналы протокола. Их физический порядок на полоске пока не сопоставлен.',
 'rgb_breath_limit':'Для дыхания доступно до 5 цветных кадров: остальные 5 нужны для затухания. Уменьши число кадров или выбери плавный переход.',
 'rgb_frames':'Нужны 1–10 кадров по 10 цветов; для дыхания — не более 5 кадров.',
 'rgb_effect':'Эффект'})
STRINGS['en'].update({
 'per_led':'Per-channel static', 'frames':'Frame animation',
 'rgb_transition':'Transition', 'rgb_smooth':'Smooth', 'rgb_play':'▶ Preview',
 'rgb_pause':'Ⅱ Pause', 'rgb_duplicate':'Duplicate frame', 'rgb_delete':'Delete frame',
 'rgb_frame':'Frame {n}', 'rgb_channel':'Channel {n}', 'rgb_fill':'Fill with selected color',
 'rgb_order':'Numbers identify protocol channels. Their physical order on the light bar has not been mapped yet.',
 'rgb_breath_limit':'Breathing supports up to 5 color frames; the other 5 are used for fading. Remove frames or select Smooth.',
 'rgb_frames':'Use 1–10 frames with 10 RGB colors each; breathing supports at most 5 frames.',
 'rgb_effect':'Effect'})
KEYS = [('LT','lt',90,42),('LM','lm',163,47),('LB','lb',130,93),('RT','rt',630,42),('RM','rm',557,47),('RB','rb',590,93),('Home','home',360,167),('Select','select',278,186),('Start','start',442,186),('LS','ls',205,240),('RS','rs',439,302),('↑','up',285,265),('←','left',252,298),('→','right',318,298),('↓','down',285,331),('Y','y',511,218),('X','x',477,254),('B','b',548,254),('A','a',511,290),('Z','z',562,318),('C','c',528,353),('M2','m2',307,435),('M1','m1',413,435),('M4','m4',288,499),('M3','m3',432,499),('FN','fn',389,557),('Turbo','turbo',335,557)]

STRINGS['ru'].update({
 'device_read':'Считать состояние', 'device_read_tip':'Читает прошивку и разрешение доступа напрямую, даже если SDL не показывает геймпад.',
 'motor_profile':'Параметры активного профиля', 'motor_read':'Считать параметры моторов',
 'motor_values':'Рукоятки: {left}% / {right}% · Триггеры, длинный ход: {lt}% / {rt}%',
 'motor_switches':'Основная вибрация: {grip} · Вибрация триггеров: {trigger}',
 'enabled':'включена', 'disabled':'выключена',
 'motor_unread':'Параметры профиля ещё не считаны. Ползунки ниже относятся только к тестовому импульсу.',
 'motor_format':'Формат настроек моторов этой прошивки пока не поддерживается. Профиль не изменён.',
 'motor_verify':'Обратное чтение настроек моторов не совпало. Повтори чтение; резервная копия сохранена.',
 'charging':'Заряжается', 'battery_stage':'Уровень {level} из 5',
 'access':'Сторонние приложения', 'access_on':'Доступ разрешён', 'access_off':'Доступ выключен',
 'access_disable':'Запретить доступ', 'access_disabled':'Доступ сторонним приложениям выключен.', 'access_enable':'Разрешить доступ', 'access_enabled':'Доступ разрешён. Можно запустить тестер или Steam.',
 'access_hint':'Включает или выключает доступ SDL и Steam к расширенным кнопкам. Меняется только по нажатию; перед записью тестер останавливается.',
 'access_unsupported':'Для этой версии прошивки запись разрешения ещё не подтверждена. Состояние доступно только для чтения.',
 'access_verify':'Геймпад не подтвердил изменение доступа. Настройки повторно считаны; успешная запись не подтверждена.',
 'device_format':'Геймпад вернул неизвестный формат состояния. Запись недоступна.',
 'device_owned':'Геймпад используется другим приложением. Закрой его и повтори операцию.',
 'owner':'Управление', 'free':'Свободен', 'device_reading':'Читаю состояние геймпада…',
 'rgb_wrong_mode':'Геймпад подключён через другой интерфейс. Для настройки подсветки подключи донгл и выбери его режим.',
 'tester_native':'Переключись в Native для проверки физических кнопок.', 'tester_steam':'Закрой Steam перед запуском тестера.', 'tester_missing':'Vader 5 Pro недоступен через SDL. Проверь подключение и разрешение сторонним приложениям.',
 'rgb_auto':'Исходная подсветка будет считана автоматически при открытии этой вкладки.',
 'gyro':'Гироскоп · рад/с', 'accel':'Акселерометр · м/с²', 'sensor_unavailable':'Этот режим не предоставляет датчик через SDL.',
 'tester_hint':'Нажимай кнопки и двигай стики. Доступные датчики отображаются ниже; тестер останавливается перед настройкой устройства.',
 'trigger_left':'Левый триггер · LT', 'trigger_right':'Правый триггер · RT',
 'rumblehint':'Короткий импульс выбранных моторов. Ползунки задают силу проверки, а не настройки игровых эффектов.',
 'motor_direct':'Проверить четыре мотора',
 'motor_hint':'Для отдельной проверки триггеров нужен донгл и закрытые Steam/Padctl. Вибрация длится 0,3 с.',
 'triggerpending':'Сохранение силы моторов и привязка триггеров к основной вибрации ещё не подключены. Тест не меняет профиль.',
 'rgb_snapshot':'Исходное состояние сохранено · профиль {profile}',
 'read_failed':'Не удалось считать состояние',
})
STRINGS['en'].update({
 'device_read':'Read status', 'device_read_tip':'Read firmware and access permission directly, even when SDL cannot see the controller.',
 'motor_profile':'Active profile settings', 'motor_read':'Read motor settings',
 'motor_values':'Grips: {left}% / {right}% · Triggers, long travel: {lt}% / {rt}%',
 'motor_switches':'Grip vibration: {grip} · Trigger vibration: {trigger}',
 'enabled':'enabled', 'disabled':'disabled',
 'motor_unread':'Profile settings have not been read. The sliders below control the test pulse only.',
 'motor_format':'This firmware motor settings format is not supported yet. The profile was not changed.',
 'motor_verify':'Motor settings read-back does not match. Read again; a backup has been saved.',
 'charging':'Charging', 'battery_stage':'Level {level} of 5',
 'access':'Third-party applications', 'access_on':'Access enabled', 'access_off':'Access disabled',
 'access_disable':'Disable access', 'access_disabled':'Third-party access disabled.', 'access_enable':'Enable access', 'access_enabled':'Access enabled. You can start the tester or Steam.',
 'access_hint':'Enable or disable SDL and Steam access to extended buttons. Changes only on click; the tester stops before writing.',
 'access_unsupported':'Writing access permission is not verified for this firmware. Status is read-only.',
 'access_verify':'The controller did not confirm the access change. Status was read again; the write is not confirmed.',
 'device_format':'Unknown device status format. Writing is unavailable.',
 'device_owned':'Another application owns the controller. Close it and retry.',
 'owner':'Controlled by', 'free':'Available', 'device_reading':'Reading controller status…',
 'rgb_wrong_mode':'The controller is connected through another interface. Connect the receiver and select receiver mode to configure lighting.',
 'tester_native':'Switch to Native to test physical buttons.', 'tester_steam':'Close Steam before starting the tester.', 'tester_missing':'Vader 5 Pro is unavailable through SDL. Check the connection and third-party permission.',
 'rgb_auto':'Original lighting will be read automatically when you open this page.',
 'gyro':'Gyroscope · rad/s', 'accel':'Accelerometer · m/s²', 'sensor_unavailable':'This mode does not expose this sensor through SDL.',
 'tester_hint':'Press buttons and move the sticks. Available sensors appear below. Testing stops before device configuration.',
 'trigger_left':'Left trigger · LT', 'trigger_right':'Right trigger · RT',
 'rumblehint':'A short pulse on the selected motors. Sliders control the test strength, not in-game settings.',
 'motor_direct':'Test four motors',
 'motor_hint':'Individual trigger testing requires the receiver with Steam/Padctl closed. The pulse lasts 0.3 s.',
 'triggerpending':'Saving motor strength and binding trigger effects to grip vibration are not connected yet. Testing leaves the profile unchanged.',
 'rgb_snapshot':'Original state saved · profile {profile}',
 'read_failed':'Could not read status',
})


STRINGS['ru'].update({
 'motor_edit_hint':'Настройки игровых эффектов активного профиля. Применение меняет память геймпада; сохранение после выключения пока не гарантируется. Микроход триггеров не изменяется.',
 'motor_grip_enabled':'Основная вибрация', 'motor_trigger_enabled':'Вибрация триггеров',
 'motor_apply':'Применить игровые настройки', 'motor_applied':'Настройки моторов применены и считаны обратно.',
 'motor_source':'Источник эффекта', 'motor_sources':['Канал триггера','Основные моторы: левый первым','Основные моторы: правый первым','Выключен'],
 'motor_min':'Минимальный уровень (0–255)', 'motor_max':'Максимальный уровень (0–255)',
 'motor_filter':'Порог входной вибрации (0–255)', 'motor_press':'Порог нажатия триггера (0–255)',
 'motor_test_title':'Короткий тест моторов',
 'motor_link':'Триггеры при нажатии + основной вибрации',
 'motor_link_tip':'Для длинного хода: включает триггеры, выбирает основные моторы как источник и задаёт минимальные пороги. Силу настрой ползунками, затем нажми «Применить».',
 'motor_unread':'Считай активный профиль, чтобы менять игровые эффекты.',
})
STRINGS['en'].update({
 'motor_edit_hint':'In-game effects for the active profile. Apply changes controller memory; retention after power-off is not guaranteed. Hair-trigger settings remain unchanged.',
 'motor_grip_enabled':'Grip vibration', 'motor_trigger_enabled':'Trigger vibration',
 'motor_apply':'Apply game settings', 'motor_applied':'Motor settings applied and verified by read-back.',
 'motor_source':'Effect source', 'motor_sources':['Trigger channel','Grip motors: left first','Grip motors: right first','Disabled'],
 'motor_min':'Minimum level (0–255)', 'motor_max':'Maximum level (0–255)',
 'motor_filter':'Input vibration threshold (0–255)', 'motor_press':'Trigger press threshold (0–255)',
 'motor_test_title':'Short motor test',
 'motor_link':'Triggers while pressed + grip vibration',
 'motor_link_tip':'For long travel: enables triggers, uses grip vibration as the source and sets minimum thresholds. Adjust strength, then click Apply.',
 'motor_unread':'Read the active profile to change game effects.',
})

class PadPicture(Gtk.DrawingArea):
    def __init__(self, owner, lighting=False):
        super().__init__()
        self.owner, self.lighting = owner, lighting
        self.source = (ROOT / 'assets' / ('lighting.svg' if lighting else 'overview.svg')).read_text(encoding='utf-8')
        self.set_hexpand(True)
        self.set_content_width(470)
        self.set_content_height(360 if lighting else 440)
        self.set_draw_func(self.draw)
        if lighting:
            click=Gtk.GestureClick()
            click.connect('pressed',self.pick_led)
            self.add_controller(click)
            motion=Gtk.EventControllerMotion()
            motion.connect('motion',self.paint_led)
            self.add_controller(motion)

    led_positions=[(204,409),(241,381),(279,378),(311,378),(344,378),
                   (376,378),(409,378),(441,378),(479,381),(516,409)]

    def pick_led(self,gesture,presses,x,y):
        editor=getattr(self.owner,'rgb_editor',None)
        if editor is None or self.owner.busy:return
        width,height=self.get_width(),self.get_height()
        scale=min(width/600,height/430)
        x=(x-(width-600*scale)/2)/scale+60
        y=(y-(height-430*scale)/2)/scale+90
        index=min(range(10),key=lambda i:math.dist((x,y),self.led_positions[i]))
        if math.dist((x,y),self.led_positions[index])<=28:
            if not editor.paint(index):editor.select_led(index)

    def paint_led(self,controller,x,y):
        if controller.get_current_event_state() & Gdk.ModifierType.BUTTON1_MASK:
            self.pick_led(None,1,x,y)

    def draw(self, area, cr, width, height):
        dark = self.owner.prefs['theme'] == 'dark'
        svg = self.source
        if not dark:
            for old, new in {'#242833':'#f8f8fb','#1b1e26':'#e9edf4','#151922':'#dde3ed','#353c49':'#ffffff','#20252f':'#dce2ec','#b4bccb':'#5b6575','#8992a2':'#727c8d','#515a69':'#9da7b8'}.items():
                svg = svg.replace(old, new)
        color, body, key = ('#b9c1d1','#1b1e26','#242832') if dark else ('#5c6677','#eef1f6','#f6f7fb')
        css = '.vc-outline{fill:'+body+';stroke:'+color+';stroke-width:2}.vc-key{fill:'+key+';stroke:'+color+';stroke-width:2}.vc-contour{fill:none;stroke:'+color+';stroke-width:1.5;opacity:.35}.vc-rear{fill:'+body+';stroke:'+color+';stroke-width:2}text{fill:'+color+';text-anchor:middle;dominant-baseline:central;font-family:sans-serif;font-size:21px}.vc-label{font-size:19px}.vc-strip-base{fill:none;stroke:'+body+';stroke-width:11;stroke-linecap:round}.vc-strip{fill:none;stroke-width:6;filter:url(#led-glow)}'
        for k in self.owner.pressed:
            css += '[data-key="'+k+'"],[data-key="'+k+'"] .vc-key{fill:#7962bd;stroke:#bbaaff;stroke-width:3}'
        axes=self.owner.telemetry.get('axes', [0]*6)
        for key,x,y,ax,ay in [('ls',205,240,axes[0],axes[1]),('rs',439,326,axes[2],axes[3])]:
            pattern=r'(<circle\b[^>]*)(data-key="'+key+r'")([^>]*/>)'
            svg=re.sub(pattern,lambda m:m[1]+'transform="translate(%.2f %.2f)" '%(ax*12,ay*12)+m[2]+m[3],svg)
        svg = svg.replace('>', '><style>'+css+'</style>', 1)
        colors = self.owner.light_colors()
        i = 0
        editing=self.lighting and self.owner.prefs['effect'] in ['per_led','frames']
        def paint(match):
            nonlocal i
            color, level = colors[i % len(colors)]
            selected=editing and i==self.owner.rgb_led_index;i += 1
            return match[0].replace('/>', ' style="stroke:'+color+';opacity:'+str(level)+';stroke-width:'+('10' if selected else '6')+'"/>')
        svg = re.sub(r'<path\b[^>]*class="vc-strip"[^>]*/>', paint, svg)
        if editing:
            numbers=''.join('<text x="%d" y="%d" style="font-size:12px">%d</text>'%(x,y+20,i+1) for i,(x,y) in enumerate(self.led_positions))
            svg=svg.replace('</svg>',numbers+'</svg>')
        handle = Rsvg.Handle.new_from_data(svg.encode())
        box = Rsvg.Rectangle()
        vw, vh = (600, 430) if self.lighting else (720, 590)
        scale = min(width / vw, height / vh)
        box.x, box.y = (width-vw*scale)/2, (height-vh*scale)/2
        box.width, box.height = vw*scale, vh*scale
        handle.render_document(cr, box)

STRINGS['ru'].update({
 'bt_setup':'Подключить Bluetooth', 'bt_title':'Bluetooth Flashplay',
 'bt_hint':'Включи Flashplay, разбуди геймпад и отключи его от телефона. Закрой Steam перед подключением.',
 'bt_search':'Найти геймпад', 'bt_searching':'Поиск Bluetooth…',
 'bt_connect':'Подключить', 'bt_connecting':'Подключаю Bluetooth…',
 'bt_none':'Геймпад не найден. Проверь режим Flashplay и повтори поиск.',
 'bt_off':'Включи Bluetooth на компьютере.', 'bt_invalid':'Некорректный Bluetooth-адрес.',
 'bt_failed':'Не удалось настроить Bluetooth-подключение.',
 'bt_timeout':'Геймпад выбран, но поток ввода не появился. Разбуди его и повтори подключение.',
 'bt_choose':'Выбери геймпад и адаптер:'})
STRINGS['en'].update({
 'bt_setup':'Connect Bluetooth', 'bt_title':'Bluetooth Flashplay',
 'bt_hint':'Wake the controller in Flashplay and disconnect the phone. Close Steam before connecting.',
 'bt_search':'Find controller', 'bt_searching':'Searching Bluetooth…',
 'bt_connect':'Connect', 'bt_connecting':'Connecting Bluetooth…',
 'bt_none':'Controller not found. Check Flashplay mode and search again.',
 'bt_off':'Turn on Bluetooth on the computer.', 'bt_invalid':'Invalid Bluetooth address.',
 'bt_failed':'Could not configure the Bluetooth connection.',
 'bt_timeout':'Controller selected, but no input stream arrived. Wake it and reconnect.',
 'bt_choose':'Choose a controller and adapter:'})

for language,values in TRANSLATIONS.items():
    STRINGS[language].update(values)


STRINGS['ru'].update({
 'tester_connecting':'Подключение…','rgb_brush':'Кисть','rgb_brush_color':'Цвет кисти','rgb_brush_hint':'Выбери цвет и проведи с зажатой кнопкой по каналам или полоске на схеме.',
 'about':'О программе','author':'Автор','experimental':'Экспериментальные настройки',
 'experimental_hint':'Показывать настройки стиков, триггеров и вибрации.',
 'rgb_apply_tip':'Применяет подсветку, сохраняет активный профиль в память геймпада и проверяет чтением. Вместе с RGB прошивка сохраняет текущие назначения и макросы.',
 'rgbapplied':'Сохранено в геймпад и считано обратно · профиль {profile}',
 'rgb_unsupported':'Сохранение подсветки для этой версии прошивки пока не поддерживается.',
 'rgb_save':'Геймпад не подтвердил команду сохранения подсветки.'})
STRINGS['en'].update({
 'tester_connecting':'Connecting…','rgb_brush':'Brush','rgb_brush_color':'Brush color','rgb_brush_hint':'Choose a color, then click or drag across channels or the light bar.',
 'about':'About','author':'Author','experimental':'Experimental settings',
 'experimental_hint':'Show stick, trigger and vibration settings.',
 'rgb_apply_tip':'Applies lighting, commits the active profile to controller memory and reads it back. The firmware also saves current mappings and macros along with RGB.',
 'rgbapplied':'Saved to controller and read back · profile {profile}',
 'rgb_unsupported':'Lighting persistence is not supported for this firmware version yet.',
 'rgb_save':'The controller did not acknowledge the lighting save command.'})


class Window(InputSettingsMixin, Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Vader5 Control', default_width=1040, default_height=790)
        self.prefs = {'lang':'ru' if os.environ.get('LANG','').startswith('ru') else 'en', 'theme':'dark', 'effect':'flow', 'brightness':75, 'speed':50, 'period':15, 'colors':['#9d83ff','#5cdaed','#f67eab'], 'frames':[['#9d83ff']*10], 'transition':'smooth', 'experimental':False}
        try:
            p = json.loads(PREFS.read_text(encoding='utf-8'))
            for key in self.prefs:
                if isinstance(p,dict) and key in p: self.prefs[key] = p[key]
        except (OSError, ValueError): pass
        if self.prefs['lang'] not in STRINGS: self.prefs['lang']='en'
        if self.prefs['theme'] not in ['dark','light']: self.prefs['theme']='dark'
        self.prefs['experimental'] = self.prefs['experimental'] is True
        if self.prefs['effect'] not in ['default','flow','breathing','gradient','solid','off','per_led','frames']:self.prefs['effect']='flow'
        for key,default in [('brightness',75),('speed',50)]:
            value=self.prefs[key]
            self.prefs[key]=max(0 if key=='brightness' else 1,min(100,int(value))) if isinstance(value,(int,float)) and math.isfinite(value) else default
        colors=self.prefs['colors']
        self.prefs['colors']=[c for c in colors if isinstance(c,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',c)][:5] if isinstance(colors,list) else []
        if not self.prefs['colors']:self.prefs['colors']=['#9d83ff','#5cdaed']
        if self.prefs['effect']=='gradient' and len(self.prefs['colors'])<2:self.prefs['colors'].append('#5cdaed')
        value = self.prefs['period']
        self.prefs['period'] = max(1,min(255,int(value))) if isinstance(value,(int,float)) and math.isfinite(value) else 15
        frames = self.prefs['frames']
        if not (isinstance(frames,list) and 1<=len(frames)<=10 and all(
                isinstance(f,list) and len(f)==10 and all(isinstance(c,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',c) for c in f) for f in frames)):
            self.prefs['frames']=[['#9d83ff']*10]
        if self.prefs['transition'] not in ['smooth','breathing'] or (self.prefs['transition']=='breathing' and len(self.prefs['frames'])>5):
            self.prefs['transition']='smooth'
        self.rgb_frame_index=self.rgb_led_index=0
        self.rgb_playing=False
        self.motor_config = None
        self.rgb_config = self.rgb_initial = None
        self.rgb_originals = {}
        self.device_info = None
        self.probed_endpoint = None
        self.rgb_device_ready = None
        self.rgb_dirty = False
        self.rgb_loading = False
        self.rgb_epoch = time.monotonic()
        self.closed=False
        self.bt_cancel=threading.Event()
        self.bt_operation=False
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.busy = self.refreshing = False
        self.reader = backend.InputReader()
        self.pressed = set()
        self.telemetry = {}
        self.status = {'mode':None,'devices':[], 'patch':None,'endpoints':[]}
        self.page = 'overview'
        self.profile = None
        self.drafts = {}
        self.user_presets = self.load_user_presets()
        self.connect('close-request', self.close_window)
        startup_trace('building window')
        self.build()
        startup_trace('window built')
        self.refresh()
        self.timers=[GLib.timeout_add(3000,self.refresh),GLib.timeout_add(20,self.poll_input),GLib.timeout_add(100,self.animate)]

    def t(self, key): return STRINGS[self.prefs['lang']].get(key, key)
    def label(self, key, cls=None):
        l = Gtk.Label(label=self.t(key), xalign=0)
        if cls: l.add_css_class(cls)
        return l
    def button(self, title, callback, cls=None):
        b=Gtk.Button(label=title); b.connect('clicked', callback)
        if cls: b.add_css_class(cls)
        return b
    def box(self, vertical=True, spacing=12): return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)
    def save_prefs(self):
        PREFS.parent.mkdir(parents=True, exist_ok=True)
        temp=PREFS.with_suffix('.tmp');temp.write_text(json.dumps(self.prefs), encoding='utf-8');temp.replace(PREFS)
    def load_user_presets(self):
        try:
            data=json.loads(USER_PRESETS.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            return {}
        result={}
        if not isinstance(data,dict):return result
        for name,value in data.items():
            if not isinstance(name,str) or not name.strip() or not isinstance(value,dict):continue
            effect=value.get('effect')
            frames=value.get('frames')
            colors=value.get('colors')
            if effect not in ['default','flow','breathing','gradient','solid','off','per_led','frames']:continue
            if not (isinstance(frames,list) and 1<=len(frames)<=10 and all(isinstance(f,list) and len(f)==10 and all(isinstance(c,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',c) for c in f) for f in frames)):continue
            if not (isinstance(colors,list) and 1<=len(colors)<=5 and all(isinstance(c,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',c) for c in colors)):continue
            if value.get('transition') not in ['smooth','breathing'] or (value['transition']=='breathing' and len(frames)>5):continue
            if not isinstance(value.get('brightness'),int) or not 0<=value['brightness']<=100:continue
            if not isinstance(value.get('period'),int) or not 1<=value['period']<=255:continue
            result[name.strip()]=dict(effect=effect,frames=frames,colors=colors,transition=value['transition'],brightness=value['brightness'],period=value['period'])
        return result
    def write_user_presets(self):
        USER_PRESETS.parent.mkdir(parents=True,exist_ok=True)
        temp=USER_PRESETS.with_suffix('.tmp')
        temp.write_text(json.dumps(self.user_presets,ensure_ascii=False,indent=2), encoding='utf-8')
        temp.replace(USER_PRESETS)
    def capture_editor(self):
        if getattr(self,'editor',None) and self.profile:
            buf=self.editor.get_buffer();self.drafts[self.profile]=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),True)
    def capture_rgb_editor(self):
        return
    def appearance(self):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK if self.prefs['theme']=='dark' else Adw.ColorScheme.FORCE_LIGHT)
    def change_theme(self, b):
        self.prefs['theme']='light' if self.prefs['theme']=='dark' else 'dark';self.appearance();self.save_prefs();self.picture.queue_draw();self.light_picture.queue_draw()
    def change_language(self, dropdown, prop):
        lang=['ru','en'][dropdown.get_selected()]
        if lang!=self.prefs['lang']:
            drafts=self.capture_setting_drafts()
            self.capture_editor();self.prefs['lang']=lang;self.save_prefs();self.build()
            self.restore_setting_drafts(drafts)

    def build(self):
        self.appearance()
        outer=self.box(spacing=0); self.set_content(outer)
        header=Adw.HeaderBar();header.set_title_widget(Adw.WindowTitle(title='Vader5 Control'))
        theme=Gtk.Button(icon_name='weather-clear-night-symbolic');theme.set_tooltip_text(self.t('light') if self.prefs['theme']=='dark' else self.t('dark'));theme.connect('clicked',self.change_theme);header.pack_end(theme)
        lang=Gtk.DropDown.new_from_strings(['RU','EN']);lang.set_selected(0 if self.prefs['lang']=='ru' else 1);lang.connect('notify::selected',self.change_language);header.pack_end(lang);outer.append(header)
        row=self.box(False,0);row.set_vexpand(True);outer.append(row)
        sidebar=self.box(spacing=6);sidebar.set_size_request(164,-1);sidebar.add_css_class('sidebar');sidebar.set_margin_top(20);sidebar.set_margin_start(10);sidebar.set_margin_end(10)
        row.append(sidebar)
        self.stack=Gtk.Stack();self.stack.set_hexpand(True);self.stack.set_vexpand(True);row.append(self.stack)
        self.nav={}
        for page in (['overview','sticks','trigger_curves','lighting','vibration','about'] if backend.WINDOWS else ['overview','padctl','sticks','trigger_curves','lighting','vibration','about']):
            b=self.button('Padctl' if page=='padctl' else self.t(page),lambda b,p=page:self.navigate(p))
            b.add_css_class('flat');b.set_halign(Gtk.Align.FILL);sidebar.append(b);self.nav[page]=b
        self.content={}
        for p in self.nav:
            pagebox=self.box(spacing=20)
            for side in ['top','bottom','start','end']:getattr(pagebox,'set_margin_'+side)(24)
            if p in ('lighting','vibration','sticks','trigger_curves','about'):
                scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
                scroll.set_child(pagebox);self.stack.add_named(scroll,p)
            else:self.stack.add_named(pagebox,p)
            self.content[p]=pagebox
        self.overview()
        if not backend.WINDOWS:self.padctl_page()
        self.lighting_page();self.vibration_page();self.input_pages();self.about_page();self.experimental_visibility();self.navigate(self.page);self.update_status()

    def about_page(self):
        page=self.content['about']
        page.append(Gtk.Label(label='Vader5 Control',xalign=0,css_classes=['title-1']))
        page.append(Gtk.Label(label='0.1 beta',xalign=0))
        page.append(Gtk.Label(label=self.t('author')+': AltMugen',xalign=0,selectable=True))
        group=Adw.PreferencesGroup()
        switch=Adw.SwitchRow(title=self.t('experimental'),subtitle=self.t('experimental_hint'))
        switch.set_active(self.prefs['experimental'])
        switch.connect('notify::active',self.experimental_changed)
        group.add(switch);page.append(group)

    def experimental_visibility(self):
        for name,button in self.nav.items():
            button.set_visible(name in ('overview','lighting','padctl','about') or self.prefs['experimental'])
        if self.page not in self.nav or not self.nav[self.page].get_visible():
            self.page='overview'

    def experimental_changed(self,switch,_):
        self.prefs['experimental']=switch.get_active();self.save_prefs()
        self.experimental_visibility();self.navigate(self.page)

    def navigate(self, page):
        self.capture_editor();self.page=page;self.stack.set_visible_child_name(page)
        for p,b in self.nav.items():
            if p==page:b.add_css_class('selected-nav')
            else:b.remove_css_class('selected-nav')
        if page=='lighting' and self.rgb_config is None and not self.rgb_dirty and not self.busy and self.status.get('endpoints', ()):
            GLib.idle_add(self.auto_read_lighting)

    def auto_read_lighting(self):
        if not self.closed and not self.busy and self.rgb_config is None and not self.rgb_dirty:
            self.read_lighting(None)
        return False

    def overview(self):
        box=self.content['overview'];head=self.box(False);head.append(Gtk.Label(label='Vader5 Pro',xalign=0,css_classes=['title-1']));self.connection_label=self.label('offline','dim-label');self.connection_label.set_hexpand(True);self.connection_label.set_halign(Gtk.Align.END);head.append(self.connection_label);box.append(head)
        toolbar=self.box(False);self.mode_buttons={}
        for mode in ([] if backend.WINDOWS else ['native','padctl']):
            b=Gtk.ToggleButton(label='Native' if mode=='native' else 'Padctl');b.connect('clicked',lambda b,m=mode:self.set_mode(m));toolbar.append(b);self.mode_buttons[mode]=b
        space=Gtk.Box();space.set_hexpand(True);toolbar.append(space)
        toolbar.append(self.button(self.t('patch'),lambda b:self.command('update'),'suggested-action'));box.append(toolbar)
        row=self.box(False,24);row.set_vexpand(True);box.append(row)
        main=self.box();main.set_hexpand(True);row.append(main)
        self.picture=PadPicture(self);main.append(self.picture)
        lower=self.box(False);self.last_input=Gtk.Label(label='—',xalign=0);self.last_input.set_hexpand(True);lower.append(self.last_input)
        self.read_button=self.button(self.t('tester_start'),self.toggle_reader);lower.append(self.read_button);main.append(lower)
        self.reconnect_button=self.button(self.t('reconnect'),self.reconnect_input);lower.append(self.reconnect_button)
        self.bluetooth_button=self.button(self.t('bt_setup'),self.bluetooth_dialog);main.append(self.bluetooth_button)
        self.axis_label=Gtk.Label(label='LS —   RS —   LT —   RT —',xalign=0,css_classes=['dim-label']);main.append(self.axis_label)
        self.tester_hint=self.label('tester_hint','dim-label');self.tester_hint.set_wrap(True);main.append(self.tester_hint)
        self.sensor_labels={}
        for sensor in ('gyro','accel'):
            label=Gtk.Label(label=self.t(sensor)+'  —',xalign=0,css_classes=['dim-label'])
            label.set_tooltip_text(self.t('sensor_unavailable'));main.append(label);self.sensor_labels[sensor]=label
        info=self.box(spacing=10);info.set_size_request(190,-1);row.append(info);self.fields={}
        for key in ['battery','connection','controller','receiver','access','owner','SDL']:
            if key=='controller':info.append(self.label('firmware','title-4'))
            r=self.box();r.append(self.label(key,'dim-label'));value=Gtk.Label(label='—',xalign=0);r.append(value);info.append(r);self.fields[key]=value
        self.device_read_button=self.button(self.t('device_read'),self.read_device)
        self.device_read_button.set_tooltip_text(self.t('device_read_tip'));info.append(self.device_read_button)
        self.access_button=self.button(self.t('access_enable'),self.enable_device_access)
        self.access_button.set_tooltip_text(self.t('access_hint'));self.access_button.set_sensitive(False);info.append(self.access_button)


    def padctl_page(self):
        box=self.content['padctl'];box.append(Gtk.Label(label='Padctl',xalign=0,css_classes=['title-1']))
        guide=Gtk.LinkButton.new_with_label('https://github.com/BANANASJIM/padctl','')
        guide.set_label(self.t('padctl_guide'));guide.set_halign(Gtk.Align.START);box.append(guide)
        self.maps=backend.mappings();names=list(self.maps)
        if not names:box.append(self.label('empty'));self.editor=None;return
        if self.profile not in self.maps:self.profile=names[0]
        row=self.box(False);drop=Gtk.DropDown.new_from_strings(names);drop.set_selected(names.index(self.profile));drop.set_hexpand(True);row.append(drop)
        row.append(self.button(self.t('apply'),lambda b:self.job(lambda:backend.run(['padctl','switch',self.profile]),lambda r:self.result(r))))
        row.append(self.button(self.t('save'),self.save_profile));box.append(row)
        scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);self.editor=Gtk.TextView(monospace=True);self.editor.set_top_margin(12);self.editor.set_left_margin(12);scroll.set_child(self.editor);box.append(scroll)
        self.load_profile()
        def choose(d,p):
            self.capture_editor();self.profile=names[d.get_selected()];self.load_profile()
        drop.connect('notify::selected',choose)
    def load_profile(self):self.editor.get_buffer().set_text(self.drafts.get(self.profile,self.maps[self.profile].read_text(encoding='utf-8')))
    def save_profile(self,b):
        self.capture_editor();name=self.profile;content=self.drafts[name]
        self.job(lambda:backend.save_mapping(name,content),lambda r:self.message(self.t('saved')))

    def lighting_page(self):
        box=self.content['lighting'];box.append(self.label('lighting','title-1'))
        actions=self.box(False)
        self.rgb_read_button=self.button(self.t('rgbread'),self.read_lighting)
        self.rgb_apply_button=self.button(self.t('rgbapply'),self.apply_lighting,'suggested-action')
        self.rgb_restore_button=self.button(self.t('rgbrestore'),self.restore_lighting)
        self.rgb_read_button.set_tooltip_text(self.t('rgb_read_tip'))
        self.rgb_apply_button.set_tooltip_text(self.t('rgb_apply_tip'))
        self.rgb_restore_button.set_tooltip_text(self.t('rgb_restore_tip'))
        for b in [self.rgb_read_button,self.rgb_apply_button,self.rgb_restore_button]:actions.append(b)
        box.append(actions)
        presetrow=self.box(False,8);presetrow.set_hexpand(True)
        presetrow.append(self.label('preset_list'))
        self.preset_names=list(self.user_presets)
        self.preset_dropdown=Gtk.DropDown.new_from_strings(self.preset_names or [self.t('preset_none')])
        self.preset_dropdown.set_hexpand(True);presetrow.append(self.preset_dropdown)
        self.preset_entry=Gtk.Entry();self.preset_entry.set_placeholder_text(self.t('preset_name'));self.preset_entry.set_width_chars(18);presetrow.append(self.preset_entry)
        self.preset_save_button=self.button(self.t('preset_save'),self.save_lighting_preset);presetrow.append(self.preset_save_button)
        self.preset_load_button=self.button(self.t('preset_load'),self.load_lighting_preset);presetrow.append(self.preset_load_button)
        self.preset_delete_button=self.button(self.t('preset_delete'),self.delete_lighting_preset);presetrow.append(self.preset_delete_button)
        box.append(presetrow);self.preset_buttons()
        self.rgb_status=Gtk.Label(label=self.t('rgbdirty') if self.rgb_dirty else self.t('rgbready').format(profile=self.rgb_config.profile%4+1,count=10) if self.rgb_config else self.t('rgbhint'),xalign=0,wrap=True,css_classes=['dim-label'])
        box.append(self.rgb_status)
        row=self.box(False,24);box.append(row)
        self.light_picture=PadPicture(self,True);row.append(self.light_picture)
        controls=self.box();self.rgb_controls=controls;controls.set_size_request(260,-1);row.append(controls)
        controls.append(self.label('rgb_effect'))
        self.effect_names=['default','flow','breathing','gradient','solid','off','per_led','frames']
        self.effect_dropdown=Gtk.DropDown.new_from_strings([self.t(n) for n in self.effect_names])
        self.effect_dropdown.set_selected(self.effect_names.index(self.prefs['effect']))
        self.effect_dropdown.connect('notify::selected',lambda d,p:self.effect(self.effect_names[d.get_selected()]) if not self.rgb_loading else None)
        controls.append(self.effect_dropdown)
        self.rgb_scales={}
        for key in ['brightness','period']:
            controls.append(self.label(key));scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0 if key=='brightness' else 1,100 if key=='brightness' else 255,1);scale.set_value(self.prefs[key]);scale.set_draw_value(True);scale.connect('value-changed',lambda s,k=key:self.slider(k,s.get_value()));controls.append(scale);self.rgb_scales[key]=scale
        self.palette_box=self.box();box.append(self.palette_box);self.render_palette()
        bottom=self.box(False);hint=self.label('rgb_preview','dim-label');hint.set_wrap(True);bottom.append(hint);box.append(bottom)
        self.rgb_buttons()
    def rgb_buttons(self):
        receiver=bool(self.status.get('endpoints', ()))
        ready=not self.busy and receiver and self.rgb_device_ready is True
        self.rgb_controls.set_sensitive(ready)
        self.palette_box.set_sensitive(ready)
        self.rgb_read_button.set_sensitive(not self.busy and receiver)
        self.rgb_apply_button.set_sensitive(not self.busy and receiver and self.rgb_device_ready is True and self.rgb_config is not None and self.rgb_dirty)
        self.rgb_restore_button.set_sensitive(not self.busy and receiver and self.rgb_device_ready is True and self.rgb_config is not None and self.rgb_initial is not None)
        self.preset_buttons()
    def preset_buttons(self):
        if not hasattr(self,'preset_load_button'):return
        available=bool(self.user_presets)
        self.preset_load_button.set_sensitive(not self.busy and available)
        self.preset_delete_button.set_sensitive(not self.busy and available)
        self.preset_save_button.set_sensitive(not self.busy)
    def selected_lighting_preset(self):
        if not self.preset_names:return None
        index=self.preset_dropdown.get_selected()
        return self.preset_names[index] if index<len(self.preset_names) else None
    def refresh_lighting_presets(self,selected=None):
        self.preset_names=list(self.user_presets)
        names=self.preset_names or [self.t('preset_none')]
        self.preset_dropdown.set_model(Gtk.StringList.new(names))
        self.preset_dropdown.set_selected(self.preset_names.index(selected) if selected in self.preset_names else 0)
        self.preset_buttons()
    def save_lighting_preset(self,b):
        self.capture_rgb_editor()
        name=self.preset_entry.get_text().strip()
        if not name:
            self.message(self.t('preset_name'));return
        self.user_presets[name]=json.loads(json.dumps(dict(effect=self.prefs['effect'],frames=self.prefs['frames'],colors=self.prefs['colors'],transition=self.prefs['transition'],brightness=self.prefs['brightness'],period=self.prefs['period'])))
        try:self.write_user_presets()
        except OSError as e:self.message(str(e));return
        self.refresh_lighting_presets(name);self.message(self.t('preset_saved'))
    def load_lighting_preset(self,b):
        name=self.selected_lighting_preset()
        if name is None or name not in self.user_presets:return
        self.capture_rgb_editor();self.prefs.update(json.loads(json.dumps(self.user_presets[name])));self.rgb_frame_index=0;self.rgb_playing=False
        self.save_prefs();self.render_palette();self.light_picture.queue_draw()
        if self.rgb_config is not None:self.rgb_changed()
        else:self.rgb_status.set_label(self.t('rgbhint'))
    def delete_lighting_preset(self,b):
        name=self.selected_lighting_preset()
        if name is None or name not in self.user_presets:return
        dialog=Adw.AlertDialog(heading=self.t('preset_delete'),body=self.t('preset_confirm_delete'))
        dialog.add_response('cancel',self.t('cancel'));dialog.add_response('delete',self.t('preset_delete'))
        dialog.set_response_appearance('delete',Adw.ResponseAppearance.DESTRUCTIVE)
        def response(d,response_id):
            if response_id!='delete':return
            self.user_presets.pop(name,None)
            try:self.write_user_presets()
            except OSError as e:self.message(str(e));return
            self.refresh_lighting_presets();self.message(self.t('preset_deleted'))
        dialog.connect('response',response);dialog.present(self)
    def rgb_changed(self):
        if self.rgb_loading:return
        self.rgb_dirty=True
        self.rgb_status.set_label(self.t('rgbdirty'))
        self.rgb_buttons()
    def read_lighting(self,b):
        self.stop_input_reader()
        self.rgb_device_ready=None;self.rgb_status.set_label(self.t('rgb_reading'));self.rgb_buttons()
        self.job(lighting.read_config,self.lighting_loaded)
    def lighting_loaded(self,config,preferred_effect=None):
        identity=(config.device,config.profile)
        if identity not in self.rgb_originals:
            lighting.backup(config,backend.DATA/'vader5-control/backups')
            self.rgb_originals[identity]=config
        self.rgb_initial=self.rgb_originals[identity]
        self.rgb_loading=True
        self.rgb_config=config;self.rgb_device_ready=True;self.rgb_dirty=False;self.rgb_epoch=time.monotonic()
        self.prefs.update(effect=config.effect,brightness=config.raw[6],period=max(1,config.raw[5]))
        custom = ((config.independent_channels and config.effect in ['solid','gradient','breathing']) or
                  (config.effect=='gradient' and len(config.keyframes)==1))
        if custom:
            self.prefs['effect']='per_led' if len(config.keyframes)==1 else 'frames'
        if preferred_effect in ['per_led','frames']:
            self.prefs['effect']=preferred_effect
        self.prefs['frames']=config.keyframes
        self.prefs['transition']='breathing' if config.effect=='breathing' else 'smooth'
        self.rgb_frame_index=0;self.rgb_playing=False
        if config.effect in ['solid','breathing','gradient']:
            self.prefs['colors']=config.colors
        self.effect_dropdown.set_selected(self.effect_names.index(self.prefs['effect']))
        for name,scale in self.rgb_scales.items():scale.set_value(self.prefs[name])
        self.rgb_loading=False
        self.render_palette();self.save_prefs()
        self.rgb_status.set_label(self.t('rgbready').format(profile=config.profile%4+1,count=10)+' · '+self.t('rgb_original'))
        self.rgb_buttons();self.light_picture.queue_draw();self.picture.queue_draw()
    def apply_lighting(self,b):
        if self.rgb_config is None:return
        try:
            target=self.lighting_target()
        except Exception as e:self.show_error(e);return
        self.write_lighting(target)
    def restore_lighting(self,b):
        if self.rgb_initial is None or self.rgb_config is None:return
        target=self.rgb_initial
        self.stop_input_reader()
        def restore():
            # Restore rebases on the current RGB state before overwriting it.
            current=lighting.read_config()
            if (current.device,current.profile)!=(target.device,target.profile):
                raise lighting.LightingError('rgb_profile')
            return lighting.apply_config(current,target,backend.DATA/'vader5-control/backups')
        def done(config):
            self.lighting_loaded(config,'per_led' if target.independent_channels else None)
            self.rgb_status.set_label(self.t('rgb_restored'))
        self.job(restore,done)
    def write_lighting(self,target):
        before=self.rgb_config
        preferred=self.prefs['effect'] if target!=self.rgb_initial else None
        self.stop_input_reader()
        def done(config):
            self.lighting_loaded(config,preferred)
            self.rgb_status.set_label(self.t('rgbapplied').format(profile=config.profile%4+1))
        self.job(lambda:lighting.apply_config(before,target,backend.DATA/'vader5-control/backups'),done)
    def effect(self,name):
        if self.busy:return
        self.prefs['effect']=name
        self.rgb_playing=False
        if name=='gradient' and len(self.prefs['colors'])<2:self.prefs['colors'].append('#5cdaed')
        self.save_prefs();self.render_palette();self.light_picture.queue_draw()
        self.rgb_changed()
    def lighting_target(self):
        if self.prefs['effect'] in ['per_led','frames']:
            frames=self.prefs['frames']
            transition=self.prefs['transition']
            if self.prefs['effect']=='per_led':
                frames=[frames[self.rgb_frame_index]];transition='smooth'
            return self.rgb_config.custom(frames,self.prefs['brightness'],self.prefs['period'],transition)
        return self.rgb_config.changed(self.prefs['effect'],self.prefs['brightness'],self.prefs['period'],self.prefs['colors'])
    def slider(self,key,value):
        self.prefs[key]=int(value);self.save_prefs();self.light_picture.queue_draw();self.rgb_changed()
    def render_palette(self):
        while self.palette_box.get_first_child():self.palette_box.remove(self.palette_box.get_first_child())
        mode=self.prefs['effect']
        self.rgb_editor=None
        if mode in ['per_led','frames']:
            self.rgb_editor=FrameEditor(self);self.palette_box.append(self.rgb_editor);return
        if mode in ['default','flow','off']:
            if mode!='off':self.palette_box.append(self.label('preset','dim-label'))
            return
        self.palette_box.append(self.label('colors'));row=self.box(False);self.palette_box.append(row)
        colors=self.prefs['colors'][:1] if mode=='solid' else self.prefs['colors']
        for i,c in enumerate(colors):
            rgba=Gdk.RGBA();rgba.parse(c);picker=ColorPicker(rgba=rgba,cancel_label=self.t('cancel'));row.append(picker)
            def change(p,prop,index=i):
                c=p.get_rgba();self.prefs['colors'][index]='#%02x%02x%02x'%(round(c.red*255),round(c.green*255),round(c.blue*255));self.save_prefs();self.light_picture.queue_draw();self.rgb_changed()
            picker.connect('notify::rgba',change)
        if mode!='solid':
            add=self.button('+',lambda b:self.change_palette(True));add.set_sensitive(len(colors)<5);row.append(add)
            remove=self.button('−',lambda b:self.change_palette(False));remove.set_sensitive(len(colors)>(2 if mode=='gradient' else 1));row.append(remove)
            row.append(self.button('←',lambda b:self.rotate_palette(-1)));row.append(self.button('→',lambda b:self.rotate_palette(1)))
    def change_palette(self,add):
        if add and len(self.prefs['colors'])<5:self.prefs['colors'].append('#f0ba68')
        elif not add and len(self.prefs['colors'])>(2 if self.prefs['effect']=='gradient' else 1):self.prefs['colors'].pop()
        self.save_prefs();self.render_palette();self.light_picture.queue_draw()
        self.rgb_changed()
    def rotate_palette(self,step):
        cs=self.prefs['colors'];self.prefs['colors']=cs[step:]+cs[:step];self.save_prefs();self.render_palette();self.rgb_changed()
    def light_colors(self):
        mode=self.prefs['effect'];level=self.prefs['brightness']/100;t=(time.monotonic()-self.rgb_epoch)/max(.1,self.prefs['period']/10);colors=self.prefs['colors']
        if mode in ['per_led','frames'] and (mode=='per_led' or not self.rgb_playing):
            return [(c,level) for c in self.prefs['frames'][self.rgb_frame_index]]
        if mode=='frames' and self.rgb_config is None:
            frames=self.prefs['frames'];pos=(t%1)*len(frames);a=frames[int(pos)];b=frames[(int(pos)+1)%len(frames)];f=pos%1
            if self.prefs['transition']=='breathing':
                return [(c,level*math.sin((pos%1)*math.pi)**2) for c in a]
            return [('#'+''.join('%02x'%round(int(c[j:j+2],16)*(1-f)+int(d[j:j+2],16)*f) for j in [1,3,5]),level) for c,d in zip(a,b)]
        if self.rgb_config is not None:
            try:
                config=self.lighting_target() if self.rgb_dirty else self.rgb_config
                frames=config.frames[config.raw[3]:config.raw[4]+1]
                pos=(t%1)*len(frames);a=frames[int(pos)];b=frames[(int(pos)+1)%len(frames)];f=pos%1
                return [('#%02x%02x%02x'%tuple(round(x*(1-f)+y*f) for x,y in zip(c,d)),level) for c,d in zip(a,b)]
            except (lighting.LightingError,KeyError):pass
        result=[]
        for i in range(10):
            v=level
            if mode=='off':c='#555e70';v=.35
            elif mode=='flow':
                import colorsys
                c='#%02x%02x%02x'%tuple(round(n*255) for n in colorsys.hsv_to_rgb((i/10-t)%1,.75,1))
            elif mode=='default':c='#829def'
            elif mode=='solid':c=colors[0]
            elif mode=='breathing':c=colors[int(t)%len(colors)];v*=math.sin((t%1)*math.pi)**2
            else:
                p=(t%1)*len(colors);a=colors[int(p)];b=colors[(int(p)+1)%len(colors)];f=p%1
                c='#'+''.join('%02x'%round(int(a[j:j+2],16)*(1-f)+int(b[j:j+2],16)*f) for j in [1,3,5])
            result.append((c,v))
        return result

    def vibration_page(self):
        box=self.content['vibration'];box.append(self.label('vibration','title-1'))
        box.append(self.label('motor_profile','title-3'))
        self.motor_read_button=self.button(self.t('motor_read'),self.read_motor_settings)
        box.append(self.motor_read_button)
        self.motor_values_label=Gtk.Label(label=self.t('motor_unread'),wrap=True,xalign=0,css_classes=['dim-label'])
        box.append(self.motor_values_label)
        self.motor_editor=self.box();box.append(self.motor_editor)
        hint=self.label('motor_edit_hint','dim-label');hint.set_wrap(True);self.motor_editor.append(hint)
        self.motor_enabled=[]
        for key in ('motor_grip_enabled','motor_trigger_enabled'):
            switch=Gtk.CheckButton(label=self.t(key));self.motor_editor.append(switch);self.motor_enabled.append(switch)
        self.game_gains=[]
        for key in ('left','right','trigger_left','trigger_right'):
            row=self.box(False);row.append(self.label(key))
            scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1)
            scale.set_hexpand(True);scale.set_draw_value(True);row.append(scale)
            self.motor_editor.append(row);self.game_gains.append(scale)
        self.trigger_editors=[]
        for key in ('trigger_left','trigger_right'):
            group=Adw.ExpanderRow(title=self.t(key))
            listing=Gtk.ListBox(css_classes=['boxed-list']);listing.append(group);self.motor_editor.append(listing)
            source=Gtk.DropDown.new_from_strings(self.t('motor_sources'))
            row=Adw.ActionRow(title=self.t('motor_source'));row.add_suffix(source);group.add_row(row)
            fields=[]
            for field in ('motor_min','motor_max','motor_filter','motor_press'):
                spin=Gtk.SpinButton.new_with_range(0,255,1)
                row=Adw.ActionRow(title=self.t(field));row.add_suffix(spin);group.add_row(row);fields.append(spin)
            self.trigger_editors.append((source,fields))
        link=self.button(self.t('motor_link'),self.link_trigger_effects)
        link.set_tooltip_text(self.t('motor_link_tip'));self.motor_editor.append(link)
        self.motor_apply_button=self.button(self.t('motor_apply'),self.apply_motor_settings,'suggested-action')
        self.motor_editor.append(self.motor_apply_button)
        self.populate_motor_settings()
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(self.label('motor_test_title','title-3'))
        hint=self.label('rumblehint','dim-label');hint.set_wrap(True);box.append(hint);self.motors=[]
        for name in ['left','right','trigger_left','trigger_right']:
            if name=='trigger_left':box.append(self.label('triggers','title-3'))
            box.append(self.label(name))
            scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1)
            scale.set_value(30 if name in ['left','right'] else 0);scale.set_draw_value(True)
            box.append(scale);self.motors.append(scale)
        actions=self.box(False)
        self.grip_test_button=self.button(self.t('rumble'),self.test_grip_motors)
        self.direct_test_button=self.button(self.t('motor_direct'),self.test_all_motors,'suggested-action')
        actions.append(self.grip_test_button);actions.append(self.direct_test_button);box.append(actions)
        for key in ['motor_hint']:
            hint=self.label(key,'dim-label');hint.set_wrap(True);box.append(hint)

    def populate_motor_settings(self):
        settings=self.motor_config
        self.motor_editor.set_sensitive(settings is not None and not self.busy)
        if settings is None:return
        for scale,value in zip(self.game_gains,settings.gains):scale.set_value(value)
        for switch,value in zip(self.motor_enabled,settings.enabled):switch.set_active(value)
        for (source,fields),values in zip(self.trigger_editors,settings.trigger_settings):
            source.set_selected((0,1,2,255).index(values[0]) if values[0] in (0,1,2,255) else Gtk.INVALID_LIST_POSITION)
            for spin,value in zip(fields,values[1:5]):spin.set_value(value)
        self.motor_values_label.set_label(self.t('motor_profile')+' · '+str(settings.profile%4+1))

    def read_motor_settings(self,b):
        self.stop_input_reader()
        def done(settings):
            motors.backup(settings,backend.DATA/'vader5-control/backups')
            self.motor_config=settings;self.populate_motor_settings()
        self.job(motors.read,done)

    def link_trigger_effects(self,b):
        self.motor_enabled[0].set_active(True);self.motor_enabled[1].set_active(True)
        for index,(source,fields) in enumerate(self.trigger_editors):
            source.set_selected(index+1)
            for spin,value in zip(fields,(0,255,1,1)):spin.set_value(value)

    def apply_motor_settings(self,b):
        if self.motor_config is None:return
        self.stop_input_reader()
        try:
            triggers=[]
            for source,fields in self.trigger_editors:
                selected=source.get_selected()
                if selected>=4:raise lighting.LightingError('motor_format')
                triggers.append(((0,1,2,255)[selected],*(spin.get_value_as_int() for spin in fields)))
            before=self.motor_config
            after=before.changed(tuple(round(s.get_value()) for s in self.game_gains),
                                 tuple(s.get_active() for s in self.motor_enabled),triggers)
        except Exception as error:self.show_error(error);return
        def done(settings):
            self.motor_config=settings;self.populate_motor_settings()
            self.rebase_input_profiles(settings)
            self.motor_values_label.set_label(self.t('motor_applied'))
        self.job(lambda:motors.apply(before,after,backend.DATA/'vader5-control/backups'),done)

    def test_grip_motors(self,b):
        levels=tuple(round(s.get_value()*2.55) for s in self.motors[:2])
        self.job(lambda:backend.rumble(*levels),lambda r:None)

    def test_all_motors(self,b):
        self.stop_input_reader()
        if backend.active('padctl') or backend.steam_running():
            self.message(self.t('motor_hint'));return
        levels=tuple(round(s.get_value()*2.55) for s in self.motors)
        self.job(lambda:device.test_motors(*levels),lambda r:None)

    def auto_read_device(self):
        if not self.closed and not self.busy and not self.reader.pad:
            self.read_device()
        return False

    def read_device(self,b=None):
        self.stop_input_reader()
        self.device_info=None;self.access_button.set_sensitive(False)
        for name in ('access','owner'):self.fields[name].set_label('—')
        self.connection_label.set_label(self.t('device_reading'))
        self.job(device.read_information,self.device_loaded)

    def device_loaded(self,info):
        self.device_info=info
        self.fields['controller'].set_label(info['firmware'] or '—')
        self.fields['receiver'].set_label(info.get('receiver_firmware') or '—')
        level=info.get('battery_level')
        self.fields['battery'].set_label(self.t('charging') if info.get('charging') else self.t('battery_stage').format(level=level) if level is not None else '—')
        access=info['access']
        self.fields['access'].set_label(self.t('access_on' if access.enabled else 'access_off'))
        self.fields['owner'].set_label(access.owner or self.t('free'))
        self.connection_label.set_label(self.t('connected'))
        self.access_button.set_label(self.t('access_disable' if access.enabled else 'access_enable'))
        self.access_button.set_sensitive(not self.busy and info['access_writable'] and not access.owner)
        self.access_button.set_tooltip_text(self.t('access_hint' if info['access_writable'] else 'access_unsupported'))

    def enable_device_access(self,b):
        if self.busy or self.device_info is None:return
        enabled=not self.device_info['access'].enabled
        self.stop_input_reader()
        def done(info):
            self.device_loaded(info)
            self.message(self.t('access_enabled' if enabled else 'access_disabled'))
        self.job(lambda:device.set_access(enabled),done)

    def toggle_reader(self,b):
        if self.busy:return
        try:
            if self.reader.pad or self.reader.waiting:self.stop_input_reader()
            else:self.reader.start(wait=False);b.set_label(self.t('tester_stop'));self.last_input.set_label(self.t('tester_connecting'));self.picture.queue_draw()
        except Exception as e:self.stop_input_reader();self.show_error(e)
    def stop_input_reader(self):
        self.reader.close();self.pressed=set()
        if hasattr(self,'read_button'):self.read_button.set_label(self.t('tester_start'))
        if hasattr(self,'last_input'):self.last_input.set_label('—')
        self.telemetry={}
        if hasattr(self,'sensor_labels'):
            for name,label in self.sensor_labels.items():label.set_label(self.t(name)+'  —')
        if hasattr(self,'axis_label'):self.axis_label.set_label('LS —   RS —   LT —   RT —')
        if hasattr(self,'picture'):self.picture.queue_draw()
    def bluetooth_dialog(self, button=None):
        if self.busy:
            return
        dialog=Adw.AlertDialog(heading=self.t('bt_title'),body=self.t('bt_hint'))
        dialog.add_response('cancel',self.t('cancel'))
        dialog.add_response('search',self.t('bt_search'))
        dialog.set_response_appearance('search',Adw.ResponseAppearance.SUGGESTED)
        dialog.connect('response',lambda dialog,response:self.scan_bluetooth() if response=='search' else None)
        dialog.present(self)

    def scan_bluetooth(self):
        if self.busy:
            return
        self.stop_input_reader()
        self.bt_cancel.clear()
        self.last_input.set_label(self.t('bt_searching'))
        self.bt_operation=True
        progress=Gtk.Window(title=self.t('bt_title'),transient_for=self,modal=True,
                            default_width=360,default_height=160,resizable=False)
        content=self.box(spacing=16)
        for side in ('top','bottom','start','end'):getattr(content,'set_margin_'+side)(24)
        spinner=Gtk.Spinner(spinning=True)
        content.append(spinner);content.append(Gtk.Label(label=self.t('bt_searching')))
        def cancel(*_):
            self.bt_cancel.set();progress.destroy();return False
        content.append(self.button(self.t('cancel'),cancel))
        progress.connect('close-request',cancel);progress.set_child(content);progress.present()
        def search():
            try:
                if backend.active('padctl'):raise device.DeviceError('tester_native')
                if backend.steam_running():raise device.DeviceError('tester_steam')
                return bluetooth_setup.discover(cancelled=self.bt_cancel)
            finally:
                GLib.idle_add(lambda:progress.destroy())
        self.job(search,self.choose_bluetooth)

    def choose_bluetooth(self, candidates):
        self.last_input.set_label('—')
        if self.bt_cancel.is_set():return
        if not candidates:
            self.message(self.t('bt_none'))
            return
        names=[row['name']+' · '+row['address']+(' · '+row['adapter'] if row.get('adapter') else '') for row in candidates]
        picker=Gtk.DropDown.new_from_strings(names)
        dialog=Adw.AlertDialog(heading=self.t('bt_title'),body=self.t('bt_choose'))
        dialog.set_extra_child(picker)
        dialog.add_response('cancel',self.t('cancel'))
        dialog.add_response('connect',self.t('bt_connect'))
        dialog.set_response_appearance('connect',Adw.ResponseAppearance.SUGGESTED)
        def response(dialog, response):
            if response=='connect':
                selected=candidates[picker.get_selected()]
                self.bt_operation=True
                self.job(lambda:bluetooth_setup.configure(selected,cancelled=self.bt_cancel),self.bluetooth_selected)
        dialog.connect('response',response)
        dialog.present(self)

    def bluetooth_selected(self, selected):
        if selected is None:return
        self.stop_input_reader()
        self.reader.start(bluetooth=selected,wait=False)
        self.read_button.set_label(self.t('tester_stop'))
        self.last_input.set_label(self.t('bt_connecting'))

    def reconnect_input(self,b):
        testing=self.reader.pad is not None or self.reader.waiting
        self.stop_input_reader()
        self.device_info=None;self.rgb_device_ready=None;self.rgb_config=None
        self.access_button.set_sensitive(False)
        if self.status.get('endpoints', ()) and not testing:
            self.read_device();return
        try:
            self.reader.start(wait=False);self.read_button.set_label(self.t('tester_stop'));self.last_input.set_label(self.t('tester_connecting'))
        except Exception as e:
            self.last_input.set_label(self.t('offline'));self.show_error(e)
        self.refresh();self.picture.queue_draw()
    def poll_input(self):
        try:
            sample=self.reader.poll()
            if sample:
                changed=sample['pressed']!=self.pressed;self.pressed=sample['pressed'];self.telemetry=sample
                if changed:
                    self.last_input.set_label(self.t('last')+', '.join(k.upper() for k in sorted(self.pressed)) if self.pressed else self.t('connected'))
                    self.picture.queue_draw()
                self.picture.queue_draw()
                for name,label in self.sensor_labels.items():
                    values=sample['motion'].get(name)
                    label.set_label(self.t(name)+('  X %+.2f   Y %+.2f   Z %+.2f'%values if values is not None else '  —'))
                a=sample['axes'];self.axis_label.set_label('LS %.2f, %.2f   RS %.2f, %.2f   LT %.0f%%   RT %.0f%%'%(*a[:4],max(0,a[4])*100,max(0,a[5])*100))
                self.fields['battery'].set_label(str(sample['battery'])+'%' if sample['battery'] is not None else '—')
                self.fields['controller'].set_label(sample['firmware'] or (self.device_info or {}).get('firmware') or '—')
            elif self.reader.pad is None and not self.reader.waiting and self.read_button.get_label()==self.t('tester_stop'):
                self.read_button.set_label(self.t('tester_start'));self.last_input.set_label(self.t('offline'));self.pressed=set();self.picture.queue_draw()
        except Exception as e:self.stop_input_reader();self.show_error(e)
        return True
    def animate(self):
        if self.page=='lighting':self.light_picture.queue_draw()
        return True
    def set_mode(self,mode):
        if not self.busy and self.status['mode']!=mode:
            self.stop_input_reader();self.rgb_device_ready=None;self.rgb_buttons();self.command(mode)
    def command(self,action):self.job(lambda:backend.console(action),lambda r:self.result(r))
    def job(self,work,done):
        if self.busy:return
        self.busy=True;self.bluetooth_button.set_sensitive(False);self.input_sensitivity(False);self.motor_editor.set_sensitive(False);self.set_cursor_from_name('wait')
        self.read_button.set_sensitive(False)
        self.device_read_button.set_sensitive(False);self.access_button.set_sensitive(False)
        self.direct_test_button.set_sensitive(False);self.grip_test_button.set_sensitive(False);self.motor_read_button.set_sensitive(False)
        if hasattr(self,'reconnect_button'):self.reconnect_button.set_sensitive(False)
        self.rgb_buttons()
        future=self.pool.submit(work)
        def finish():
            self.busy=False;self.bt_operation=False;self.set_cursor(None)
            if hasattr(self,'reconnect_button'):self.reconnect_button.set_sensitive(True)
            if self.closed:return False
            try:done(future.result())
            except Exception as e:self.show_error(e)
            self.rgb_buttons()
            self.update_status();self.refresh();return False
        future.add_done_callback(lambda f:GLib.idle_add(finish))
    def show_error(self,error):
        if isinstance(error,lighting.LightingError):
            if error.key in ['rgb_timeout','rgb_missing']:
                self.rgb_device_ready=False
                if hasattr(self,'rgb_status'):self.rgb_status.set_label(self.t('rgb_no_response') if error.key=='rgb_timeout' else self.t('rgb_missing'))
                if hasattr(self,'rgb_read_button'):self.rgb_buttons()
            self.message(self.t(error.key)+((' ('+error.detail+')') if error.detail else ''))
        elif isinstance(error,device.DeviceError):
            if error.key.startswith('bt_'):self.last_input.set_label('—')
            self.message(self.t(error.key)+((' ('+error.detail+')') if error.detail else ''))
        else:self.message(str(error))
    def result(self,r):
        self.message((r.stdout+'\n'+r.stderr).strip() or ('OK' if r.returncode==0 else self.t('error')))
    def message(self,text):
        dialog=Adw.AlertDialog(heading=self.t('error') if 'error' in text.lower() else 'Vader5 Control',body=text[:6000]);dialog.add_response('close','OK');dialog.present(self)
    def refresh(self):
        if self.closed:return False
        if self.busy or self.refreshing:return True
        self.refreshing=True
        def status():
            endpoints=device.endpoints()
            devices=([{'path':key,'name':'Flydigi Vader 5 Pro','connection':'USB receiver'}
                      for key,path in endpoints] if backend.WINDOWS else backend.devices())
            result={'mode':backend.mode(),'devices':devices,'endpoints':endpoints,
                    'patch':backend.patch_status(),'steam':backend.steam_running()}
            startup_trace('device status ready')
            return result
        f=self.pool.submit(status)
        def finish():
            self.refreshing=False
            if self.closed:return False
            try:self.status=f.result();self.update_status()
            except Exception:self.connection_label.set_label(self.t('unknown'))
            return False
        f.add_done_callback(lambda f:GLib.idle_add(finish));return True
    def update_status(self):
        if self.status.get('steam') and (self.reader.pad or self.reader.waiting):
            self.stop_input_reader()
            self.last_input.set_label(self.t('tester_steam'))
        self.connection_label.set_label(self.t('connected') if self.reader.pad or self.device_info else self.t('receiver_present') if self.status['devices'] else self.t('offline'))
        self.fields['connection'].set_label(self.status['devices'][0]['connection'] if self.status['devices'] else 'Bluetooth' if self.reader.pad else '—')
        endpoint_key=tuple(item[0] for item in self.status.get('endpoints', ()))
        receiver=bool(endpoint_key)
        if endpoint_key!=self.probed_endpoint and not self.busy:
            self.probed_endpoint=endpoint_key
            if receiver and not self.reader.pad:
                GLib.idle_add(self.auto_read_device)
        if not receiver:
            self.input_profiles.clear();self.hardware_state=None
            self.device_info=None;self.motor_config=None;self.rgb_config=None;self.rgb_device_ready=None
            for name in ('controller','receiver','access','owner','battery'):self.fields[name].set_label('—')
        if self.device_info and not self.reader.pad:
            self.device_loaded(self.device_info)
        self.bluetooth_button.set_sensitive(not self.busy)
        self.read_button.set_sensitive(not self.busy)
        self.device_read_button.set_sensitive(receiver and not self.busy)
        self.access_button.set_sensitive(not self.busy and self.device_info is not None and self.device_info['access_writable'] and not self.device_info['access'].owner)
        self.direct_test_button.set_sensitive(receiver and not self.busy)
        self.input_sensitivity(receiver)
        self.motor_read_button.set_sensitive(receiver and not self.busy)
        self.motor_editor.set_sensitive(receiver and not self.busy and self.motor_config is not None)
        self.grip_test_button.set_sensitive(receiver and self.status['mode']=='native' and not self.busy)
        self.fields['SDL'].set_label(self.t('notchecked') if self.status['patch'] is None else self.t('patched') if self.status['patch'] else self.t('stock'))
        for mode,b in self.mode_buttons.items():b.set_active(self.status['mode']==mode)
        if hasattr(self,'rgb_read_button'):
            receiver=bool(self.status.get('endpoints', ()))
            if not self.busy and not receiver:self.rgb_status.set_label(self.t('rgb_wrong_mode') if self.reader.pad else self.t('rgb_missing'))
            elif not self.busy and self.rgb_device_ready is False:self.rgb_status.set_label(self.t('rgb_no_response'))
            self.rgb_buttons()
    def close_window(self,w):
        self.bt_cancel.set()
        if self.busy and not self.bt_operation:self.message(self.t('busy'));return True
        self.closed=True
        for timer in self.timers:GLib.source_remove(timer)
        self.capture_editor();self.reader.close();self.pool.shutdown(wait=False,cancel_futures=True);return False

# Padctl is a Linux integration; Windows messages mention only competing Windows apps.
if backend.WINDOWS:
    for locale in STRINGS.values():
        for key, value in locale.items():
            if isinstance(value, str):
                locale[key] = value.replace(' и Padctl', '').replace(' и padctl', '').replace(' and Padctl', '').replace('/Padctl', '')

class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.github.AltMugen.Vader5Control',flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    def do_activate(self):
        startup_trace('application activated')
        if self.get_active_window():self.get_active_window().present();return
        Gtk.Window.set_default_icon_name('io.github.AltMugen.Vader5Control')
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(ROOT/'assets/icons'))
        provider=Gtk.CssProvider();provider.load_from_path(str(ROOT/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        if backend.WINDOWS:
            accent=Gtk.CssProvider()
            accent.load_from_data(b'@define-color accent_bg_color #3584e4; @define-color accent_fg_color #ffffff; @define-color accent_color #3584e4; :root { --accent-bg-color: #3584e4; --accent-fg-color: #ffffff; --accent-color: #3584e4; }')
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),accent,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        window=Window(self)
        window.present()
        startup_trace('window presented')

if __name__=='__main__': App().run(None)
