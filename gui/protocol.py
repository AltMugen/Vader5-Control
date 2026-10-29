"""NewXInput wire format shared by the platform transports.

Offsets refer to reports after stripping the HID report ID. Commands follow
Space Station's SDK, not the different internal main-MCU mailbox protocol.
"""
from dataclasses import dataclass


class DeviceError(RuntimeError):
    def __init__(self, key, detail=''):
        self.key, self.detail = key, detail
        super().__init__(key + (': ' + detail if detail else ''))


def command_packet(command, payload=b'', report_id=0):
    if not 0 <= command <= 255 or len(payload) > 26:
        raise ValueError('Command payload exceeds the 32-byte HID report')
    packet = bytearray(32)
    packet[0:5] = bytes([report_id, 0x5a, 0xa5, command, len(payload) + 2])
    packet[5:5 + len(payload)] = payload
    packet[5 + len(payload)] = sum(packet[3:5 + len(payload)]) & 255
    return bytes(packet)


def normalize_reply(data):
    # Some platforms include the HID report ID, others omit it.
    if len(data) == 33 and data[1:3] == b'\x5a\xa5':
        data = data[1:]
    if len(data) != 32 or data[:2] != b'\x5a\xa5':
        return None
    if sum(data[2:-1]) & 255 != data[-1]:
        # The 7.1.5.3 heartbeat has a non-checksum trailer (captured on hardware).
        # Only this heartbeat format bypasses the additive checksum.
        if data[2] != 0x01:
            raise DeviceError('rgb_checksum')
        DeviceInfo.parse(data)
    return bytes(data)


@dataclass(frozen=True)
class AccessStatus:
    enabled: bool
    owner: str
    flags: tuple

    @classmethod
    def parse(cls, reply):
        if len(reply) != 32 or reply[2] != 0x10 or any(v not in (0, 1) for v in reply[5:10]):
            raise DeviceError('device_format')
        tag = reply[10:30].rstrip(b'\x00')
        if any(b < 32 or b > 126 for b in tag):
            raise DeviceError('device_format')
        return cls(reply[9] == 1, tag.decode('ascii'), tuple(reply[5:10]))


def firmware_string(value):
    return '.'.join(str((value >> shift) & 15) for shift in (12, 8, 4, 0)) if value else None


def rumble_payload(left, right, trigger_left=0, trigger_right=0):
    values = (left, right, trigger_left, trigger_right)
    if any(not isinstance(v, int) or not 0 <= v <= 255 for v in values):
        raise ValueError('Motor levels must be integers in 0..255')
    return bytes(values)


@dataclass(frozen=True)
class DeviceInfo:
    firmware: int
    receiver_firmware: int
    connection: int
    battery_level: int | None
    charging: bool

    @classmethod
    def parse(cls, reply):
        if (len(reply) != 32 or reply[2] != 1 or reply[3] == 0 or reply[4] != 0 or
                reply[5] not in (130, 144, 145) or reply[6] not in (1, 2)):
            raise DeviceError('device_format')
        firmware = int.from_bytes(reply[15:17], 'big')
        if not firmware or any(((firmware >> shift) & 15) > 9 for shift in (0, 4, 8, 12)):
            raise DeviceError('device_format')
        level = reply[11] & 15
        return cls(firmware, int.from_bytes(reply[17:19], 'big'), reply[6],
                   level if 0 <= level <= 5 else None, reply[11] >> 4 == 1)
