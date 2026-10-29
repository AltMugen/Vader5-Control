"""RGB picker with an editable hex value and a resizable color dialog."""
from gi.repository import Gdk, GObject, Gtk


class ColorPicker(Gtk.Button):
    rgba = GObject.Property(type=Gdk.RGBA)

    def __init__(self, rgba, cancel_label='Cancel'):
        super().__init__()
        self.cancel_label = cancel_label
        self._click_action = None
        self.set_rgba(rgba)
        self.connect('notify::rgba', self.update_label)
        self.connect('clicked', self.choose)
        self.update_label()

    def get_rgba(self):
        return self.props.rgba

    def set_rgba(self, value):
        self.props.rgba = value.copy()

    def update_label(self, *_):
        value = self.get_rgba()
        swatch = Gtk.DrawingArea(content_width=24, content_height=20)
        def draw(area, cr, width, height):
            cr.set_source_rgb(value.red, value.green, value.blue)
            cr.paint()
        swatch.set_draw_func(draw)
        self.set_child(swatch)

    def choose(self, *_):
        if self._click_action and self._click_action():
            return
        window = Gtk.Dialog(transient_for=self.get_root(), modal=True,
                            default_width=640, default_height=600, resizable=True)
        chooser = Gtk.ColorChooserWidget(show_editor=False, use_alpha=False,
                                         hexpand=True, vexpand=True)
        chooser.set_rgba(self.get_rgba())
        chooser.set_property('show-editor', False)
        window.get_content_area().append(chooser)
        window.add_button(self.cancel_label, Gtk.ResponseType.CANCEL)
        window.add_button('OK', Gtk.ResponseType.OK)
        def response(dialog, result):
            if result == Gtk.ResponseType.OK:
                self.set_rgba(chooser.get_rgba())
            dialog.destroy()
        window.connect('response', response)
        window.present()
