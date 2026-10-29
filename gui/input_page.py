"""Analog and hardware settings pages for the GTK application."""
from gi.repository import Gtk
import backend
import input_settings as settings
import hardware_settings
import motors

TRANSLATIONS = {
 'ru': {
  'sticks':'Стики', 'trigger_curves':'Триггеры', 'input_read':'Считать активный профиль',
  'input_apply':'Применить настройки', 'input_restore':'Вернуть исходные',
  'input_unread':'Считай настройки геймпада для редактирования.',
  'input_ready':'Считан профиль {profile}. Исходные настройки сохранены для отката.',
  'input_applied':'Применено и проверено обратным чтением.',
  'input_transport':'Кривые встроенного профиля показаны для справки. В Linux редактирование отключено: текущий Native SDL читает стики до применения этих кривых. Аппаратные настройки ниже доступны отдельно.',
  'input_transport_windows':'Кривые встроенного профиля действуют на обработанный Xbox-ввод. Расширенный ввод нашего Native SDL обходит их.',
  'trigger_transport':'Кривые триггеров попадают в общий обработанный буфер, включая расширенный ввод Native SDL.',
  'input_hint':'Настройки записываются в память активного профиля. После выключения могут сброситься. Другие параметры профиля не меняются.',
  'stick_left':'Левый стик', 'stick_right':'Правый стик',
  'stick_center':'Центр из профиля (справочно)', 'stick_end':'Конец хода из профиля (справочно)',
  'curve_center':'Зона центра для шаблона (%)', 'curve_full':'Полный ход для шаблона (%)',
  'curve_builder_hint':'Задай зону центра и полный ход, затем выбери шаблон. Он перестроит девять точек; из-за их количества границы получаются приблизительными.',
  'stick_shape':'Форма края', 'stick_shapes':['Квадрат','Круг'],
  'curve_points':'Точки кривой', 'curve_hint':'Радиальная кривая: по горизонтали — отклонение стика, по вертикали — уровень кривой. 0 соответствует центру, 100 — полному ходу. Мёртвая зона и коррекция края применяются отдельно.',
  'curve_linear':'Линейная', 'curve_slow':'Точнее у центра', 'curve_fast':'Быстрый отклик',
  'basic_units':'Считанные базовые поля сохранены для справки. Зону центра и полный ход шаблона задавай ниже: они закодируются в девяти точках кривой.',
  'trigger_hint':'Шкала профиля 0–255. Начальный порог должен быть меньше конечного; точки X — внутри этого диапазона, X и Y — по возрастанию. Изменённая кривая становится пользовательской.',
  'curve_zero':'Zero (параметр прошивки)', 'curve_end':'End (параметр прошивки)',
  'trigger_zero_hint':'Ненулевой Zero может давать скачок выходного значения в этой прошивке. Для обычной мёртвой зоны используй шаблон выше.',
  'input_format':'Не поддерживается формат настроек или нарушен диапазон значений.',
  'input_verify':'Обратное чтение не совпало. Считай состояние заново; резервная копия сохранена.',
  'hardware':'Аппаратные настройки', 'hardware_read':'Считать аппаратные настройки',
  'hardware_hint':'Эти настройки общие для профилей. Прошивка сохраняет их отдельно. Открытие приложения ничего не переключает.',
  'quick_switch':'Быстрое переключение профилей Fn + ABXY', 'mapping':'Переназначения в прошивке',
  'debounce':'Подавление мелкого дрожания стиков', 'auto_center':'Автокалибровка центра стиков',
  'rebound':'Подавление отскока стиков', 'sleep':'Сон при бездействии (минуты, 0 — отключить)',
  'sleep_set':'Изменить таймер сна', 'sleep_zero':'Геймпад вернул 0: этот ответ не различает выключенный сон и заводской таймер. Для явной настройки включи изменение таймера.',
  'sleep_hint':'Таймер для обычного подключения. При потере связи прошивка может использовать отдельный таймер выключения.',
 },
 'en': {
  'sticks':'Sticks', 'trigger_curves':'Triggers', 'input_read':'Read active profile',
  'input_apply':'Apply settings', 'input_restore':'Restore original',
  'input_unread':'Read controller settings to edit them.',
  'input_ready':'Profile {profile} read. Original settings saved for restoring.',
  'input_applied':'Applied and verified by read-back.',
  'input_transport':'Onboard profile curves are shown for reference. Editing is disabled on Linux: current Native SDL reads sticks before these curves are applied. Hardware settings below remain available.',
  'input_transport_windows':'Onboard curves affect processed Xbox input. Our extended Native SDL input bypasses them.',
  'trigger_transport':'Trigger curves reach the shared processed buffer, including extended Native SDL input.',
  'input_hint':'Changes the active profile in controller memory. Settings may reset after power-off. Other profile fields are preserved.',
  'stick_left':'Left stick', 'stick_right':'Right stick',
  'stick_center':'Profile center (reference)', 'stick_end':'Profile travel end (reference)',
  'curve_center':'Template center dead zone (%)', 'curve_full':'Template full travel (%)',
  'curve_builder_hint':'Set center dead zone and full travel, then choose a template to rebuild nine points. With nine samples, zone boundaries are approximate.',
  'stick_shape':'Edge shape', 'stick_shapes':['Square','Circle'],
  'curve_points':'Curve points', 'curve_hint':'Radial curve: horizontal axis is stick deflection, vertical axis is curve level. 0 is center, 100 is full travel. Dead zone and edge correction are separate stages.',
  'curve_linear':'Linear', 'curve_slow':'Precise center', 'curve_fast':'Fast response',
  'basic_units':'Basic profile fields are shown for reference. Set template dead zone and full travel below to encode them in the nine curve points.',
  'trigger_hint':'Profile scale: 0–255. Start must be below end; point X coordinates must be within this range; X and Y must be in order. Editing selects a custom curve.',
  'curve_zero':'Zero (firmware parameter)', 'curve_end':'End (firmware parameter)',
  'trigger_zero_hint':'Nonzero Zero may produce an output discontinuity in this firmware. Use the template above for a regular dead zone.',
  'input_format':'Unsupported settings format or invalid value range.',
  'input_verify':'Read-back does not match. Read the controller again; a backup was saved.',
  'hardware':'Hardware settings', 'hardware_read':'Read hardware settings',
  'hardware_hint':'Shared across profiles and saved separately by firmware. Opening the app changes nothing.',
  'quick_switch':'Quick profile switching: Fn + ABXY', 'mapping':'Onboard mappings',
  'debounce':'Stick jitter suppression', 'auto_center':'Automatic stick centering',
  'rebound':'Stick rebound suppression', 'sleep':'Idle sleep (minutes, 0 to disable)',
  'sleep_set':'Change idle sleep timer', 'sleep_zero':'Controller returned 0: this reply cannot distinguish disabled sleep from the factory timer. Enable timer editing to set it explicitly.',
  'sleep_hint':'Timer for a normal connection. Firmware may use a separate shutdown timer when disconnected.',
 },
}


class InputSettingsMixin:
    def input_pages(self):
        if not hasattr(self,'input_profiles'):
            self.input_profiles={};self.input_originals={};self.hardware_state=None
        self.input_widgets={};self.trigger_builders={}
        for kind in ('sticks','trigger_curves'):
            box=self.content[kind];box.append(self.label(kind,'title-1'))
            read_button=self.button(self.t('input_read'),lambda b,k=kind:self.read_input_settings(k));box.append(read_button)
            status=Gtk.Label(label=self.t('input_unread'),wrap=True,xalign=0,css_classes=['dim-label']);box.append(status)
            hint=self.label('input_hint','dim-label');hint.set_wrap(True);box.append(hint)
            transport=self.label(('input_transport_windows' if backend.WINDOWS else 'input_transport') if kind=='sticks' else 'trigger_transport','dim-label');transport.set_wrap(True);box.append(transport)
            editor=self.box();box.append(editor)
            controls=[]
            for side,name in enumerate(('stick_left','stick_right') if kind=='sticks' else ('trigger_left','trigger_right')):
                editor.append(self.label(name,'title-3'))
                if kind=='sticks':controls.append(self.stick_controls(editor))
                else:controls.append(self.trigger_controls(editor,side))
            actions=self.box(False)
            actions.append(self.button(self.t('input_apply'),lambda b,k=kind:self.apply_input_settings(k),'suggested-action'))
            actions.append(self.button(self.t('input_restore'),lambda b,k=kind:self.restore_input_settings(k)))
            editor.append(actions)
            self.input_widgets[kind]={'editor':editor,'controls':controls,'status':status,'read':read_button}
            self.populate_input_settings(kind)
        self.hardware_page()

    def spin_row(self,box,key,minimum,maximum):
        row=self.box(False);label=self.label(key);label.set_hexpand(True);row.append(label)
        spin=Gtk.SpinButton.new_with_range(minimum,maximum,1);row.append(spin);box.append(row)
        return spin

    def stick_controls(self,box):
        controls={key:self.spin_row(box,key,-128,127) for key in ('stick_center','stick_end')}
        for spin in controls.values():spin.set_sensitive(False)
        row=self.box(False);label=self.label('stick_shape');label.set_hexpand(True);row.append(label)
        controls['shape']=Gtk.DropDown.new_from_strings(self.t('stick_shapes'));row.append(controls['shape']);box.append(row)
        hint=self.label('basic_units','dim-label');hint.set_wrap(True);box.append(hint)
        plot=Gtk.DrawingArea(content_height=170);plot.set_hexpand(True);box.append(plot)
        controls['points']=[]
        grid=Gtk.Grid(column_spacing=8,row_spacing=6);grid.set_column_homogeneous(True)
        for i in range(9):
            label=Gtk.Label(label='%g%%'%(i*12.5));spin=Gtk.SpinButton.new_with_range(-50,205,1)
            grid.attach(label,i%5,(i//5)*2,1,1);grid.attach(spin,i%5,(i//5)*2+1,1,1)
            spin.connect('value-changed',lambda s:plot.queue_draw());controls['points'].append(spin)
        box.append(grid)
        hint=self.label('curve_hint','dim-label');hint.set_wrap(True);box.append(hint)
        plot.set_draw_func(lambda area,cr,w,h:self.draw_curve(cr,w,h,[s.get_value() for s in controls['points']]))
        controls['builder_center']=self.spin_row(box,'curve_center',0,99)
        controls['builder_full']=self.spin_row(box,'curve_full',1,100);controls['builder_full'].set_value(100)
        hint=self.label('curve_builder_hint','dim-label');hint.set_wrap(True);box.append(hint)
        buttons=self.box(False)
        for key,power in (('curve_linear',1),('curve_slow',2),('curve_fast',.5)):
            def preset(b,power=power):
                try:
                    points=settings.build_stick_curve(controls['builder_center'].get_value_as_int(),controls['builder_full'].get_value_as_int(),power)
                except Exception as error:self.show_error(error);return
                for spin,value in zip(controls['points'],points):spin.set_value(value)
            buttons.append(self.button(self.t(key),preset))
        box.append(buttons)
        return controls

    @staticmethod
    def draw_curve(cr,width,height,values):
        left,top=36,16;w=max(1,width-52);h=max(1,height-40)
        low=min(0,min(values));high=max(100,max(values));span=max(1,high-low)
        def y(value):return top+h*(1-(value-low)/span)
        cr.set_source_rgba(.5,.5,.5,.25);cr.set_line_width(1)
        for i in range(5):
            cr.move_to(left+w*i/4,top);cr.line_to(left+w*i/4,top+h)
            cr.move_to(left,top+h*i/4);cr.line_to(left+w,top+h*i/4)
        cr.stroke();cr.set_source_rgba(.5,.5,.5,.6)
        cr.move_to(left,y(0));cr.line_to(left+w,y(100));cr.stroke()
        cr.set_source_rgb(.68,.53,.95);cr.set_line_width(2)
        for i,value in enumerate(values):
            (cr.move_to if i==0 else cr.line_to)(left+w*i/8,y(value))
        cr.stroke()
        for i,value in enumerate(values):cr.arc(left+w*i/8,y(value),3,0,6.284);cr.fill()
        cr.set_source_rgb(.55,.55,.55);cr.set_font_size(11)
        for x,yy,label in ((left,top+h+17,'0'),(left+w-24,top+h+17,'100%'),(0,y(100)+4,'100'),(10,y(0)+4,'0')):
            cr.move_to(x,yy);cr.show_text(label)

    def trigger_controls(self,box,side):
        center=self.spin_row(box,'curve_center',0,99)
        end=self.spin_row(box,'curve_full',1,100);end.set_value(100)
        self.trigger_builders[side]=(center,end)
        fields=[]
        def linear(b):
            try:values=settings.build_trigger_curve(center.get_value_as_int(),end.get_value_as_int())
            except Exception as error:self.show_error(error);return
            for spin,value in zip(fields,values[1:]):spin.set_value(value)
        box.append(self.button(self.t('curve_linear'),linear))
        hint=self.label('trigger_hint','dim-label');hint.set_wrap(True);box.append(hint)
        for key in ('curve_zero','P1 X','P1 Y','P2 X','P2 Y','curve_end'):
            fields.append(self.spin_row(box,key,0,255))
        warning=self.label('trigger_zero_hint','dim-label');warning.set_wrap(True);box.append(warning)
        fields[0].connect('value-changed',lambda spin:warning.set_visible(spin.get_value()!=0))
        warning.set_visible(False)
        return fields

    def input_editable(self,kind):
        return kind != 'sticks' or backend.WINDOWS

    def populate_input_settings(self,kind):
        widgets=self.input_widgets[kind];profile=self.input_profiles.get(kind)
        widgets['editor'].set_sensitive(profile is not None and not self.busy and self.input_editable(kind))
        if profile is None:return
        for side,controls in enumerate(widgets['controls']):
            if kind=='sticks':
                value=profile.stick(side)
                for key,field in (('stick_center','center'),('stick_end','end')):controls[key].set_value(value[field])
                controls['shape'].set_selected(value['shape'] if value['shape'] in (0,1) else Gtk.INVALID_LIST_POSITION)
                for spin,point in zip(controls['points'],value['points']):spin.set_value(point)
            else:
                for spin,value in zip(controls,profile.trigger(side)[1:]):spin.set_value(value)
        widgets['status'].set_label(self.t('input_ready').format(profile=profile.profile%4+1))

    def read_input_settings(self,kind):
        self.stop_input_reader()
        def done(profile):
            settings.backup(profile,backend.DATA/'vader5-control/backups')
            self.input_originals.setdefault((profile.device,profile.profile),profile)
            self.input_profiles[kind]=profile;self.populate_input_settings(kind)
        self.job(settings.read,done)

    def apply_input_settings(self,kind):
        if not self.input_editable(kind):return
        before=self.input_profiles.get(kind)
        if before is None:return
        try:
            if kind=='sticks':
                values=[]
                for side,controls in enumerate(self.input_widgets[kind]['controls']):
                    values.append({'center':controls['stick_center'].get_value_as_int(),'end':controls['stick_end'].get_value_as_int(),
                                   'edge':before.stick(side)['edge'],'shape':controls['shape'].get_selected(),
                                   'points':tuple(s.get_value_as_int() for s in controls['points'])})
                after=before.changed_sticks(values)
            else:
                values=[]
                for side,controls in enumerate(self.input_widgets[kind]['controls']):
                    fields=tuple(s.get_value_as_int() for s in controls)
                    values.append((3 if fields!=before.trigger(side)[1:] else before.trigger(side)[0],*fields))
                after=before.changed_triggers(values)
        except Exception as error:self.show_error(error);return
        self.write_input_settings(kind,before,after)

    def write_input_settings(self,kind,before,after):
        self.stop_input_reader()
        allowed=settings.STICK_OFFSETS if kind=='sticks' else settings.TRIGGER_OFFSETS
        def done(profile):self.input_written(kind,profile)
        self.job(lambda:settings.apply(before,after,backend.DATA/'vader5-control/backups',allowed),done)

    def rebase_input_profiles(self,profile):
        # Disjoint editors can share the fresh full-profile snapshot while their
        # widgets keep their unsaved values. Never rebase another device/bank.
        identity=(profile.device,profile.profile)
        for kind,before in tuple(self.input_profiles.items()):
            if (before.device,before.profile)==identity:
                self.input_profiles[kind]=settings.Profile(*identity,profile.raw)
        before=self.motor_config
        if before is not None and (before.device,before.profile)==identity:
            self.motor_config=motors.Settings(*identity,profile.raw)

    def input_written(self,kind,profile):
        self.rebase_input_profiles(profile)
        self.input_profiles[kind]=profile;self.populate_input_settings(kind)
        self.input_widgets[kind]['status'].set_label(self.t('input_applied'))

    def restore_input_settings(self,kind):
        if not self.input_editable(kind):return
        before=self.input_profiles.get(kind)
        if before is None:return
        original=self.input_originals.get((before.device,before.profile))
        if original is None:return
        allowed=settings.STICK_OFFSETS if kind=='sticks' else settings.TRIGGER_OFFSETS
        self.stop_input_reader()
        def restore():
            current=settings.read()
            if (current.device,current.profile)!=(original.device,original.profile):
                raise settings.DeviceError('rgb_profile')
            raw=bytearray(current.raw)
            for i in allowed:raw[i]=original.raw[i]
            target=settings.Profile(current.device,current.profile,bytes(raw))
            return settings.apply(current,target,backend.DATA/'vader5-control/backups',allowed)
        self.job(restore,lambda profile:self.input_written(kind,profile))

    def hardware_page(self):
        box=self.content['sticks'];box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        box.append(self.label('hardware','title-2'))
        self.hardware_read_button=self.button(self.t('hardware_read'),self.read_hardware);box.append(self.hardware_read_button)
        hint=self.label('hardware_hint','dim-label');hint.set_wrap(True);box.append(hint)
        self.hardware_editor=self.box();box.append(self.hardware_editor);self.hardware_controls={}
        for key in hardware_settings.FLAGS:
            switch=Gtk.CheckButton(label=self.t(key));self.hardware_editor.append(switch);self.hardware_controls[key]=switch
        self.sleep_edit=Gtk.CheckButton(label=self.t('sleep_set'));self.hardware_editor.append(self.sleep_edit)
        self.sleep_spin=self.spin_row(self.hardware_editor,'sleep',0,254)
        self.sleep_spin.set_sensitive(False)
        self.sleep_edit.connect('toggled',lambda button:self.sleep_spin.set_sensitive(button.get_active()))
        hint=self.label('sleep_hint','dim-label');hint.set_wrap(True);self.hardware_editor.append(hint)
        self.hardware_editor.append(self.button(self.t('input_apply'),self.apply_hardware,'suggested-action'))
        self.hardware_status=Gtk.Label(xalign=0,wrap=True);box.append(self.hardware_status)
        self.populate_hardware()

    def populate_hardware(self):
        state=self.hardware_state;self.hardware_editor.set_sensitive(state is not None and not self.busy)
        if state is None:return
        for key,switch in self.hardware_controls.items():
            switch.set_active(state.enabled(key));switch.set_sensitive(state.supported(key))
        self.sleep_edit.set_active(False);self.sleep_spin.set_value(state.sleep)
        self.hardware_status.set_label(self.t('sleep_zero') if state.sleep==0 else '')

    def read_hardware(self,b):
        self.stop_input_reader()
        def done(state):self.hardware_state=state;self.populate_hardware()
        self.job(hardware_settings.read,done)

    def apply_hardware(self,b):
        if self.hardware_state is None:return
        self.stop_input_reader();before=self.hardware_state
        flags={k:v.get_active() for k,v in self.hardware_controls.items() if before.supported(k)}
        sleep=self.sleep_spin.get_value_as_int() if self.sleep_edit.get_active() else None
        def done(state):
            self.hardware_state=state;self.populate_hardware();self.hardware_status.set_label(self.t('input_applied'))
        self.job(lambda:hardware_settings.apply(before,flags,sleep,backend.DATA/'vader5-control/backups'),done)

    def input_sensitivity(self,receiver):
        self.hardware_read_button.set_sensitive(receiver and not self.busy)
        for kind,widgets in self.input_widgets.items():
            widgets['read'].set_sensitive(receiver and not self.busy)
            widgets['editor'].set_sensitive(receiver and not self.busy and self.input_profiles.get(kind) is not None and self.input_editable(kind))
            if not self.busy and (not receiver or self.input_profiles.get(kind) is None):
                widgets['status'].set_label(self.t('input_unread') if receiver else self.t('rgb_wrong_mode' if self.reader.pad else 'rgb_missing'))
        self.hardware_editor.set_sensitive(receiver and not self.busy and self.hardware_state is not None)
        if not receiver and not self.busy:self.hardware_status.set_label(self.t('rgb_wrong_mode' if self.reader.pad else 'rgb_missing'))

    def capture_setting_drafts(self):
        """Keep unsaved values when rebuilding translated widgets."""
        drafts={'input':{},'trigger_templates':{side:tuple(spin.get_value_as_int() for spin in pair) for side,pair in self.trigger_builders.items()}}
        for kind,widgets in self.input_widgets.items():
            if self.input_profiles.get(kind) is None:continue
            if kind=='sticks':
                drafts['input'][kind]=[
                    {'center':c['stick_center'].get_value_as_int(),'end':c['stick_end'].get_value_as_int(),
                     'shape':c['shape'].get_selected(),
                     'points':[v.get_value_as_int() for v in c['points']],
                     'builder_center':c['builder_center'].get_value_as_int(),'builder_full':c['builder_full'].get_value_as_int()}
                    for c in widgets['controls']]
            else:drafts['input'][kind]=[[v.get_value_as_int() for v in c] for c in widgets['controls']]
        if self.motor_config is not None:
            drafts['motors']=([v.get_value() for v in self.game_gains],
                              [v.get_active() for v in self.motor_enabled],
                              [(source.get_selected(),[v.get_value_as_int() for v in fields]) for source,fields in self.trigger_editors])
        if self.hardware_state is not None:
            drafts['hardware']=({k:v.get_active() for k,v in self.hardware_controls.items()},self.sleep_spin.get_value_as_int(),self.sleep_edit.get_active())
        return drafts

    def restore_setting_drafts(self,drafts):
        for side,values in drafts['trigger_templates'].items():
            for spin,value in zip(self.trigger_builders[side],values):spin.set_value(value)
        for kind,values in drafts['input'].items():
            for controls,value in zip(self.input_widgets[kind]['controls'],values):
                if kind=='sticks':
                    for key,field in (('stick_center','center'),('stick_end','end')):controls[key].set_value(value[field])
                    controls['shape'].set_selected(value['shape'])
                    controls['builder_center'].set_value(value['builder_center']);controls['builder_full'].set_value(value['builder_full'])
                    for spin,point in zip(controls['points'],value['points']):spin.set_value(point)
                else:
                    for spin,point in zip(controls,value):spin.set_value(point)
        if 'motors' in drafts:
            gains,enabled,triggers=drafts['motors']
            for scale,value in zip(self.game_gains,gains):scale.set_value(value)
            for switch,value in zip(self.motor_enabled,enabled):switch.set_active(value)
            for (source,fields),(selected,values) in zip(self.trigger_editors,triggers):
                source.set_selected(selected)
                for spin,value in zip(fields,values):spin.set_value(value)
        if 'hardware' in drafts:
            flags,sleep,editing=drafts['hardware']
            for key,value in flags.items():self.hardware_controls[key].set_active(value)
            self.sleep_spin.set_value(sleep);self.sleep_edit.set_active(editing)
