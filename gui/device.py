"""Short-lived Linux HID sessions, independent of SDL controller visibility.

Only the known Vader 5 receiver vendor interface is selected. Windows can
reuse protocol.py while supplying its own HID transport. No service is started.
"""
import os
if os.name != 'nt':
    import fcntl
from pathlib import Path
import select
import time
from protocol import AccessStatus, DeviceInfo, DeviceError, command_packet, normalize_reply, firmware_string, rumble_payload


def endpoints():
    if os.name == 'nt':
        from hid_windows import endpoints as windows_endpoints
        return windows_endpoints()
    result = []
    for entry in sorted(Path('/sys/class/hidraw').glob('*')):
        try:
            hid = entry / 'device'
            if ('HID_ID=0003:000037D7:00002401' in (hid / 'uevent').read_text(encoding='utf-8') and
                    (hid / 'report_descriptor').read_bytes().startswith(b'\x06\xa0\xff')):
                result.append((str(hid.resolve()), '/dev/' + entry.name))
        except OSError:
            continue
    return result


class Session:
    def __init__(self, device=None):
        self.fd = self.lock = None
        self.transport = None
        candidates = endpoints()
        if device:
            candidates = [c for c in candidates if c[0] == device]
        if not candidates:
            raise DeviceError('rgb_missing')
        if len(candidates) != 1:
            raise DeviceError('rgb_multiple')
        self.device, path = candidates[0]
        if os.name == 'nt':
            from hid_windows import Transport
            self.transport = Transport(path)
            return
        runtime = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp'))
        try:
            # Serialize vendor operations across processes.
            self.lock = os.open(runtime / ('vader5-rgb-%d.lock' % os.getuid()),
                                os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        except BlockingIOError as e:
            self.close()
            raise DeviceError('rgb_busy') from e
        except PermissionError as e:
            self.close()
            raise DeviceError('rgb_permission') from e
        except OSError:
            self.close()
            raise

    def close(self):
        if getattr(self, 'transport', None):
            self.transport.close(); self.transport = None
        for fd in (self.fd, self.lock):
            if fd is not None:
                os.close(fd)
        self.fd = self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, command, payload=b''):
        packet = command_packet(command, payload)
        if self.transport is not None:
            self.transport.send(packet)
            return
        if os.write(self.fd, packet) != len(packet):
            raise DeviceError('rgb_write')

    def response(self, command, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.transport is not None:
                data = self.transport.receive(max(0, deadline-time.monotonic()))
                if not data:
                    break
            elif not select.select([self.fd], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            else:
                try:
                    data = os.read(self.fd, 64)
                except BlockingIOError:
                    continue
            if not data:
                raise DeviceError('rgb_missing')
            # Ignore unrelated input reports before checking their checksum.
            candidate = data[1:] if len(data) == 33 else data
            if len(candidate) != 32 or candidate[:3] != bytes([0x5a, 0xa5, command]):
                continue
            reply = normalize_reply(data)
            if reply is not None:
                return reply
        raise DeviceError('rgb_timeout', '%02X' % command)

    def request(self, command, payload=b'', timeout=2):
        self.send(command, payload)
        return self.response(command, timeout)

    def access_status(self):
        return AccessStatus.parse(self.request(0x10))

    def information(self):
        access = self.access_status()
        reply = self.request(0x01)
        info = DeviceInfo.parse(reply)
        version = info.firmware
        return {'device': self.device, 'access': access,
                'firmware_value': version, 'firmware': firmware_string(version),
                'connection': {1: 'USB', 2: 'USB receiver'}[info.connection],
                'receiver_firmware': firmware_string(info.receiver_firmware),
                'battery_level': info.battery_level, 'charging': info.charging,
                # 7.2 refactored main MCU differs from the external SDK setter.
                # Do not send a write for that branch until its transport is traced.
                'access_writable': 0x7141 <= version < 0x7200}

    def set_access(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("Access state must be boolean")
        before = self.information()
        if not before['access_writable']:
            raise DeviceError('access_unsupported')
        if before['access'].owner:
            raise DeviceError('device_owned', before['access'].owner)
        if before['access'].enabled != enabled:
            # Official SDK nullable fields: preserve controller/raw/keyboard/mouse.
            self.send(0x11, b'\xff\xff\xff\xff' + bytes([enabled]))
            time.sleep(.08)
        after = self.information()
        if (after['access'].enabled != enabled or
                after['access'].flags[:4] != before['access'].flags[:4]):
            raise DeviceError('access_verify')
        return after

    def enable_access(self):
        return self.set_access(True)


def read_information():
    with Session() as session:
        return session.information()


def set_access(enabled):
    with Session() as session:
        return session.set_access(enabled)


def enable_access():
    return set_access(True)


def test_motors(left, right, trigger_left=0, trigger_right=0, duration=.3):
    payload = rumble_payload(left, right, trigger_left, trigger_right)
    if not 0 < duration <= 1:
        raise ValueError('Test pulse must be at most one second')
    with Session() as session:
        status = session.access_status()
        if status.owner:
            raise DeviceError('device_owned', status.owner)
        try:
            session.send(0x12, payload)
            time.sleep(duration)
        finally:
            session.send(0x12, bytes(4))
