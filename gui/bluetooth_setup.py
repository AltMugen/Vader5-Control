"""Flashplay discovery and per-user connection settings."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from protocol import DeviceError

ADDRESS = re.compile(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\Z')


def controller_name(value):
    return value.casefold().replace(' ', '').replace('_', '') == 'flydigivader5pro'


def config_path():
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA', Path.home()/'AppData/Roaming'))/'Vader5Control/bluetooth'
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'vader5/bluetooth'


def save_selection(selected):
    address = selected.get('address', '')
    adapter = selected.get('adapter', '')
    if not ADDRESS.fullmatch(address) or (adapter and not ADDRESS.fullmatch(adapter)):
        raise DeviceError('bt_invalid')
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='ascii', dir=target.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(address.upper()+'\n'+adapter.upper()+'\n')
        temporary.replace(target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def windows_call(action, device_id=None, cancelled=None):
    args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(Path(__file__).with_name('Bluetooth.ps1')), '-Action', action]
    if device_id:
        args += ['-DeviceId', device_id]
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          encoding='utf-8', errors='replace',
                          creationflags=subprocess.CREATE_NO_WINDOW) as process:
        deadline = time.monotonic()+50
        while True:
            if (cancelled and cancelled.is_set()) or time.monotonic() >= deadline:
                process.kill()
                process.communicate()
                if cancelled and cancelled.is_set():
                    return []
                raise DeviceError('bt_timeout')
            try:
                stdout, stderr = process.communicate(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise DeviceError('bt_failed', stderr.strip())
    try:
        return json.loads(stdout.lstrip('\ufeff') or '[]')
    except ValueError as error:
        raise DeviceError('bt_failed', 'Invalid discovery response') from error


def discover(seconds=12, cancelled=None):
    if os.name == 'nt':
        return windows_call('Scan', cancelled=cancelled)
    from gi.repository import Gio, GLib
    context = GLib.MainContext.new()
    context.push_thread_default()
    bus = None
    started = []
    subscriptions = []
    seen = set()
    try:
        # A separate connection owns only this scan's discovery sessions.
        bus = Gio.DBusConnection.new_for_address_sync(
            Gio.dbus_address_get_for_bus_sync(Gio.BusType.SYSTEM, None),
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
        def call(path, interface, method, params=None):
            return bus.call_sync('org.bluez', path, interface, method, params, None,
                                 Gio.DBusCallFlags.NONE, 4000, None)
        def objects():
            return call('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects').unpack()[0]
        entries = objects()
        adapters = {path: values['org.bluez.Adapter1'] for path, values in entries.items()
                    if values.get('org.bluez.Adapter1', {}).get('Powered')}
        if not adapters:
            raise DeviceError('bt_off')
        def changed(connection, sender, path, interface, signal, params, data):
            values = params.unpack()
            if signal == 'InterfacesAdded':
                seen.add(values[0])
            elif values[0] == 'org.bluez.Device1':
                seen.add(path)
        for interface, signal in (('org.freedesktop.DBus.ObjectManager', 'InterfacesAdded'),
                                   ('org.freedesktop.DBus.Properties', 'PropertiesChanged')):
            subscriptions.append(bus.signal_subscribe('org.bluez', interface, signal, None, None,
                                 Gio.DBusSignalFlags.NONE, changed, None))
        for path in adapters:
            call(path, 'org.bluez.Adapter1', 'SetDiscoveryFilter', GLib.Variant('(a{sv})', ({
                'Transport': GLib.Variant('s', 'le'), 'DuplicateData': GLib.Variant('b', True)},)))
            call(path, 'org.bluez.Adapter1', 'StartDiscovery')
            started.append(path)
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            if cancelled and cancelled.is_set():
                return []
            while context.pending():
                context.iteration(False)
            time.sleep(.05)
        candidates = []
        for path, values in objects().items():
            item = values.get('org.bluez.Device1', {})
            adapter = adapters.get(item.get('Adapter'))
            if (adapter and controller_name(item.get('Name', '')) and
                    item.get('AddressType') == 'public' and
                    (path in seen or item.get('Connected'))):
                candidates.append({'name': item['Name'], 'address': item['Address'],
                                   'adapter': adapter['Address']})
        return sorted(candidates, key=lambda row: (row['address'], row['adapter']))
    except DeviceError:
        raise
    except GLib.Error as error:
        raise DeviceError('bt_failed', str(error)) from error
    finally:
        if bus:
            for path in started:
                try:
                    bus.call_sync('org.bluez', path, 'org.bluez.Adapter1', 'StopDiscovery',
                                  None, None, Gio.DBusCallFlags.NONE, 1000, None)
                except GLib.Error:
                    pass
            for subscription in subscriptions:
                bus.signal_unsubscribe(subscription)
            try:
                bus.close_sync(None)
            except GLib.Error:
                pass
        context.pop_thread_default()


def configure(selected, cancelled=None):
    if os.name == 'nt':
        windows_call('Pair', selected['id'], cancelled=cancelled)
    if cancelled and cancelled.is_set():
        return None
    save_selection(selected)
    return selected
