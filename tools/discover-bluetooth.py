#!/usr/bin/env python3
"""Find nearby Vader 5 Flashplay devices through BlueZ discovery, without pairing."""
import argparse
import os
import sys
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter-only', action='store_true')
    p.add_argument('--seconds', type=float, default=12)
    p.add_argument('--list-switch', action='store_true')
    args = p.parse_args()
    if not 2 <= args.seconds <= 30: p.error('seconds must be 2..30')
    ru = any(os.environ.get(k, '').startswith('ru') for k in ('LANG', 'LC_ALL', 'LC_MESSAGES'))
    try:
        from gi.repository import Gio, GLib
    except ImportError:
        raise SystemExit('Install python3-gobject (Fedora) or python3-gi (Debian/Ubuntu) for Bluetooth discovery.')
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    def call(path, interface, method, params=None):
        return bus.call_sync('org.bluez', path, interface, method, params, None,
                             Gio.DBusCallFlags.NONE, 4000, None)
    def objects():
        return call('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects').unpack()[0]
    entries = objects()
    adapters = {path: values['org.bluez.Adapter1'] for path, values in entries.items()
                if values.get('org.bluez.Adapter1', {}).get('Powered')}
    if not adapters: raise SystemExit('Включите Bluetooth.' if ru else 'Turn Bluetooth on first.')
    if args.adapter_only:
        if len(adapters) != 1: raise SystemExit('Укажите MAC адаптера: включено несколько адаптеров.' if ru else 'Specify an adapter MAC: multiple adapters are powered.')
        print(next(iter(adapters.values()))['Address']); return
    seen = {path for path, obj in entries.items()
            if 'RSSI' in obj.get('org.bluez.Device1', {}) or obj.get('org.bluez.Device1', {}).get('Connected')}
    def changed(connection, sender, path, interface, signal, params, data):
        values = params.unpack()
        if signal == 'InterfacesAdded': seen.add(values[0])
        elif values[0] == 'org.bluez.Device1': seen.add(path)
    subscriptions = [bus.signal_subscribe('org.bluez', 'org.freedesktop.DBus.ObjectManager', 'InterfacesAdded', None, None, Gio.DBusSignalFlags.NONE, changed, None),
                     bus.signal_subscribe('org.bluez', 'org.freedesktop.DBus.Properties', 'PropertiesChanged', None, None, Gio.DBusSignalFlags.NONE, changed, None)]
    started = []
    def matches(name):
        name = name.lower().replace(' ', '').replace('_', '')
        if args.list_switch: return 'procontroller' in name or 'nintendo' in name or 'flydigi' in name or 'vader' in name
        return 'flydigi' in name and 'vader5' in name
    def candidates():
        result = []
        for path, values in objects().items():
            device = values.get('org.bluez.Device1', {})
            if path not in seen or not matches(device.get('Name', '')): continue
            adapter = adapters.get(device.get('Adapter'))
            if adapter: result.append((device['Address'], adapter['Address'], device.get('Name', '')))
        return sorted(set(result))
    try:
        for path in adapters:
            # Stop only discovery sessions started by this D-Bus client.
            call(path, 'org.bluez.Adapter1', 'SetDiscoveryFilter', GLib.Variant('(a{sv})', ({
                'Transport': GLib.Variant('s', 'auto' if args.list_switch else 'le'),
                'DuplicateData': GLib.Variant('b', True)},)))
            call(path, 'org.bluez.Adapter1', 'StartDiscovery'); started.append(path)
        print('Поиск геймпада…' if ru else 'Searching for controller...', file=sys.stderr, flush=True)
        until = time.monotonic() + args.seconds
        context = GLib.MainContext.default()
        while time.monotonic() < until:
            while context.pending(): context.iteration(False)
            time.sleep(.05)
        devices = candidates()
    finally:
        for path in started:
            try: call(path, 'org.bluez.Adapter1', 'StopDiscovery')
            except GLib.Error: pass
        for sub in subscriptions: bus.signal_unsubscribe(sub)
    if not devices: raise SystemExit('Геймпад не найден. Разбудите его в нужном режиме и отключите от других устройств.' if ru else 'Controller not found. Wake it in the required mode and disconnect other hosts.')
    if args.list_switch:
        for address, adapter, name in devices: print(f'{address}\t{adapter}\t{name}')
        return
    choice = 0
    if len(devices) > 1:
        for i, (address, adapter, name) in enumerate(devices, 1): print(f'{i}. {name} ({address}), {adapter}', file=sys.stderr)
        if not sys.stdin.isatty(): raise SystemExit('Multiple controllers found; pass explicit addresses.')
        print('Номер / Number: ', file=sys.stderr, end='', flush=True)
        try: choice = int(input()) - 1
        except ValueError: raise SystemExit('Invalid selection')
        if not 0 <= choice < len(devices): raise SystemExit('Invalid selection')
    print(devices[choice][0]); print(devices[choice][1])


if __name__ == '__main__':
    main()
