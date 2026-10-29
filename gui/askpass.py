#!/usr/bin/env python3
"""Password goes directly to sudo through stdout, never into application logs."""
import sys
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gio

class Ask(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='io.github.AltMugen.Vader5Askpass',flags=Gio.ApplicationFlags.NON_UNIQUE)
    def do_activate(self):
        w=Gtk.ApplicationWindow(application=self,title='Vader5 Control · sudo',default_width=370)
        b=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
        for side in ['top','bottom','start','end']:getattr(b,'set_margin_'+side)(20)
        b.append(Gtk.Label(label=sys.argv[1] if len(sys.argv)>1 else 'sudo',wrap=True))
        entry=Gtk.PasswordEntry();entry.set_show_peek_icon(False);b.append(entry)
        def submit(*args):
            sys.stdout.write(entry.get_text()+'\n');sys.stdout.flush();self.quit()
        entry.connect('activate',submit)
        button=Gtk.Button(label='OK');button.connect('clicked',submit);b.append(button)
        w.set_child(b);w.present();entry.grab_focus()

Ask().run([])
