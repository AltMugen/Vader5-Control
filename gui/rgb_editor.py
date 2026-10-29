"""GTK editor for ten independent RGB channels and controller keyframes."""
from gi.repository import Gdk, Gtk
from color_picker import ColorPicker


class FrameEditor(Gtk.Box):
    def __init__(self, owner):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.owner = owner
        if not hasattr(owner, 'rgb_brush_enabled'):
            owner.rgb_brush_enabled = False
            owner.rgb_brush_color = '#9d83ff'
        self.pickers = []
        self.render()

    def render(self):
        while self.get_first_child():
            self.remove(self.get_first_child())
        w = self.owner
        animated = w.prefs['effect'] == 'frames'
        frames = w.prefs['frames']
        w.rgb_frame_index = min(w.rgb_frame_index, len(frames) - 1)
        if animated:
            toolbar = w.box(False, 6)
            toolbar.append(Gtk.Label(label=w.t('rgb_transition'), xalign=0))
            transition = Gtk.DropDown.new_from_strings([w.t('rgb_smooth'), w.t('breathing')])
            transition.set_selected(1 if w.prefs['transition'] == 'breathing' else 0)
            transition.connect('notify::selected', self.transition_changed)
            toolbar.append(transition)
            play = Gtk.ToggleButton(label=w.t('rgb_pause') if w.rgb_playing else w.t('rgb_play'))
            play.set_active(w.rgb_playing)
            play.connect('toggled', self.play_changed)
            toolbar.append(play)
            self.append(toolbar)

            timeline = w.box(False, 5)
            for i in range(len(frames)):
                b = Gtk.ToggleButton(label=str(i + 1))
                b.set_active(i == w.rgb_frame_index)
                b.set_tooltip_text(w.t('rgb_frame').format(n=i + 1))
                b.connect('clicked', lambda b, index=i: self.select_frame(index))
                timeline.append(b)
            self.append(timeline)
            actions = w.box(False, 6)
            maximum = 5 if w.prefs['transition'] == 'breathing' else 10
            for title, action, enabled in [
                ('rgb_duplicate', lambda: self.duplicate(), len(frames) < maximum),
                ('rgb_delete', lambda: self.delete(), len(frames) > 1),
                ('←', lambda: self.move(-1), w.rgb_frame_index > 0),
                ('→', lambda: self.move(1), w.rgb_frame_index < len(frames) - 1),
            ]:
                b = w.button(w.t(title), lambda b, fn=action: fn())
                b.set_sensitive(enabled)
                actions.append(b)
            self.append(actions)

        line = w.box(False)
        line.append(Gtk.Label(label=w.t('rgb_frame').format(n=w.rgb_frame_index + 1)
                              if animated else w.t('per_led'), xalign=0,
                              hexpand=True, css_classes=['heading']))
        line.append(w.button(w.t('rgb_fill'), lambda b: self.fill()))
        self.append(line)
        tools = w.box(False, 8)
        brush = Gtk.ToggleButton(label=w.t('rgb_brush'))
        brush.set_active(w.rgb_brush_enabled)
        brush.connect('toggled', lambda button: setattr(w, 'rgb_brush_enabled', button.get_active()))
        tools.append(brush)
        rgba = Gdk.RGBA();rgba.parse(w.rgb_brush_color)
        brush_color = ColorPicker(rgba, cancel_label=w.t('cancel'))
        brush_color.set_tooltip_text(w.t('rgb_brush_color'))
        brush_color.connect('notify::rgba', self.brush_color_changed)
        tools.append(brush_color)
        hint = Gtk.Label(label=w.t('rgb_brush_hint'),wrap=True,xalign=0,hexpand=True,
                         css_classes=['dim-label'])
        tools.append(hint)
        self.append(tools)
        grid = Gtk.Grid(column_spacing=6, column_homogeneous=True, halign=Gtk.Align.START)
        self.pickers = []
        for index, color in enumerate(frames[w.rgb_frame_index]):
            cell = w.box(spacing=5)
            cell.add_css_class('rgb-channel')
            cell.append(Gtk.Label(label=str(index + 1)))
            rgba = Gdk.RGBA()
            rgba.parse(color)
            picker = ColorPicker(rgba=rgba, cancel_label=w.t('cancel'))
            picker.set_size_request(32, 28)
            picker.set_tooltip_text(w.t('rgb_channel').format(n=index + 1))
            picker.connect('notify::rgba', self.color_changed, index)
            picker._click_action = lambda i=index: self.paint(i)
            motion = Gtk.EventControllerMotion()
            motion.connect('enter', self.paint_enter, index)
            picker.add_controller(motion)
            cell.append(picker)
            grid.attach(cell, index, 0, 1, 1)
            self.pickers.append((cell, picker))
        self.append(grid)
        self.select_led(w.rgb_led_index)
        hint = Gtk.Label(label=w.t('rgb_order'), wrap=True, xalign=0,
                         css_classes=['dim-label'])
        self.append(hint)

    def brush_color_changed(self, picker, _):
        color = picker.get_rgba()
        self.owner.rgb_brush_color = '#%02x%02x%02x' % tuple(
            round(v * 255) for v in (color.red, color.green, color.blue))

    def paint_enter(self, controller, x, y, index):
        if controller.get_current_event_state() & Gdk.ModifierType.BUTTON1_MASK:
            self.paint(index)

    def paint(self, index):
        w = self.owner
        if not w.rgb_brush_enabled or w.busy:
            return False
        self.select_led(index)
        if w.prefs['frames'][w.rgb_frame_index][index] != w.rgb_brush_color:
            rgba = Gdk.RGBA();rgba.parse(w.rgb_brush_color)
            self.pickers[index][1].set_rgba(rgba)
        return True

    def select_led(self, index):
        self.owner.rgb_led_index = index
        for i, (cell, _) in enumerate(self.pickers):
            if i == index:
                cell.add_css_class('rgb-selected')
            else:
                cell.remove_css_class('rgb-selected')
        self.owner.light_picture.queue_draw()

    def color_changed(self, picker, prop, index):
        w = self.owner
        if w.busy:
            return
        self.select_led(index)
        color = picker.get_rgba()
        w.prefs['frames'][w.rgb_frame_index][index] = '#%02x%02x%02x' % (
            round(color.red * 255), round(color.green * 255), round(color.blue * 255))
        w.save_prefs()
        w.rgb_changed()

    def select_frame(self, index):
        self.owner.rgb_frame_index = index
        self.owner.rgb_playing = False
        self.render()
        self.owner.light_picture.queue_draw()

    def duplicate(self):
        w = self.owner
        maximum = 5 if w.prefs['transition'] == 'breathing' else 10
        if len(w.prefs['frames']) >= maximum:
            return
        i = w.rgb_frame_index
        w.prefs['frames'].insert(i + 1, w.prefs['frames'][i][:])
        w.rgb_frame_index += 1
        self.changed()

    def delete(self):
        w = self.owner
        if len(w.prefs['frames']) <= 1:
            return
        w.prefs['frames'].pop(w.rgb_frame_index)
        w.rgb_frame_index = min(w.rgb_frame_index, len(w.prefs['frames']) - 1)
        self.changed()

    def move(self, step):
        w = self.owner
        i, j = w.rgb_frame_index, w.rgb_frame_index + step
        if 0 <= j < len(w.prefs['frames']):
            frames = w.prefs['frames']
            frames[i], frames[j] = frames[j], frames[i]
            w.rgb_frame_index = j
            self.changed()

    def fill(self):
        w = self.owner
        frame = w.prefs['frames'][w.rgb_frame_index]
        color = w.rgb_brush_color if w.rgb_brush_enabled else frame[w.rgb_led_index]
        w.prefs['frames'][w.rgb_frame_index] = [color] * 10
        self.changed()

    def changed(self):
        self.owner.rgb_playing = False
        self.owner.save_prefs()
        self.owner.rgb_changed()
        self.render()

    def transition_changed(self, dropdown, prop):
        w = self.owner
        name = 'breathing' if dropdown.get_selected() == 1 else 'smooth'
        if name == 'breathing' and len(w.prefs['frames']) > 5:
            dropdown.set_selected(0)
            w.message(w.t('rgb_breath_limit'))
            return
        w.prefs['transition'] = name
        self.changed()

    def play_changed(self, button):
        import time
        self.owner.rgb_playing = button.get_active()
        self.owner.rgb_epoch = time.monotonic()
        button.set_label(self.owner.t('rgb_pause') if button.get_active()
                         else self.owner.t('rgb_play'))
        self.owner.light_picture.queue_draw()
