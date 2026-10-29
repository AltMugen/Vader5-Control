"""Vader 5 receiver RGB configuration, using the vendor NewXInput protocol.

Uses A7/A8/A9 followed by the legacy AA profile commit. AA also persists
the active mapping and macro buffers; their contents are not edited here.
Each operation opens and closes its HID handle; no background service.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import time
from device import Session
from protocol import DeviceError

MODES = {'flow': 1, 'breathing': 2, 'gradient': 3, 'solid': 5, 'off': 6, 'default': 7}


LightingError = DeviceError

@dataclass(frozen=True)
class Config:
    device: str
    profile: int
    raw: bytes

    def __post_init__(self):
        if (len(self.raw) != 320 or self.raw[:2] != b'\x00\x03' or
                self.raw[7] != 10 or self.raw[8] not in MODES.values() or
                self.raw[3] > self.raw[4] or self.raw[4] >= 10 or
                self.raw[6] > 100 or not 0 <= self.profile < 8):
            raise LightingError('rgb_format')

    @property
    def effect(self):
        return next(k for k, v in MODES.items() if v == self.raw[8])

    @property
    def frames(self):
        return [[tuple(self.raw[20 + frame * 30 + led * 3:23 + frame * 30 + led * 3])
                 for led in range(10)] for frame in range(10)]

    @property
    def colors(self):
        count = self.raw[4] + 1
        indices = range(0, count, 2) if self.effect == 'breathing' else range(count)
        colors = ['#%02x%02x%02x' % self.frames[i][0] for i in indices]
        return colors[:1] if self.effect == 'solid' else colors[:5]

    def changed(self, effect, brightness, period, colors):
        if effect not in MODES or not 0 <= brightness <= 100 or not 1 <= period <= 255:
            raise LightingError('rgb_format')
        raw = bytearray(self.raw)
        raw[2:7] = bytes([0, 0, 0, period, brightness])
        raw[8] = MODES[effect]
        frames = [[[0, 0, 0] for _ in range(10)] for _ in range(10)]
        if effect in ('flow', 'default'):
            presets = json.loads((Path(__file__).parent / 'assets/lighting-presets.json').read_text(encoding='utf-8'))
            key = '3' if effect == 'flow' else str(self.profile % 4)
            if key not in presets:
                raise LightingError('rgb_format')
            preset = presets[key]
            frames, raw[3], raw[4] = preset['frames'], preset['start'], preset['end']
        elif effect != 'off':
            minimum = 2 if effect == 'gradient' else 1
            if not minimum <= len(colors) <= 5:
                raise LightingError('rgb_colors')
            try:
                values = [list(bytes.fromhex(c.removeprefix('#'))) for c in colors]
            except ValueError as e:
                raise LightingError('rgb_colors') from e
            if any(len(c) != 3 for c in values):
                raise LightingError('rgb_colors')
            if effect == 'solid':
                values = values[:1]
            for i, color in enumerate(values):
                frame = i * 2 if effect == 'breathing' else i
                frames[frame] = [color[:] for _ in range(10)]
            raw[4] = len(values) * (2 if effect == 'breathing' else 1) - 1
        raw[20:] = bytes(c for frame in frames for led in frame for c in led)
        return Config(self.device, self.profile, bytes(raw))

    def custom(self, frames, brightness, period, transition='smooth'):
        """Encode independent channels using the existing gradient/breath engine.

        One gradient frame holds a static per-channel palette. Breathing uses
        alternate black frames, as the official mapper does, leaving 5 keyframes.
        """
        maximum = 5 if transition == 'breathing' else 10
        if (transition not in ('smooth', 'breathing') or
                not 1 <= len(frames) <= maximum or
                not isinstance(brightness, int) or not 0 <= brightness <= 100 or
                not isinstance(period, int) or not 1 <= period <= 255):
            raise LightingError('rgb_frames')
        values = []
        try:
            for frame in frames:
                if len(frame) != 10:
                    raise ValueError('10 channels required')
                colors = [bytes.fromhex(c.removeprefix('#')) for c in frame]
                if any(len(c) != 3 for c in colors):
                    raise ValueError('RGB colors required')
                values.append(b''.join(colors))
                if transition == 'breathing':
                    values.append(bytes(30))
        except (AttributeError, ValueError, TypeError) as e:
            raise LightingError('rgb_frames') from e
        raw = bytearray(self.raw)
        raw[2:7] = bytes([0, 0, len(values) - 1, period, brightness])
        raw[8] = MODES['breathing' if transition == 'breathing' else 'gradient']
        raw[20:] = b''.join(values).ljust(300, b'\x00')
        return Config(self.device, self.profile, bytes(raw))

    @property
    def keyframes(self):
        indices = range(self.raw[3], self.raw[4] + 1,
                        2 if self.effect == 'breathing' else 1)
        return [['#%02x%02x%02x' % color for color in self.frames[i]] for i in indices]

    @property
    def independent_channels(self):
        return any(len(set(frame)) > 1 for frame in self.keyframes)


class Receiver(Session):
    def mapping(self, profile):
        self.send(0xa3, bytes([profile, 20]))
        parts = {}
        for _ in range(84):
            reply = self.response(0xa3)
            if reply[3] != 42 or reply[4] >= 42 or reply[5] != profile:
                raise LightingError('rgb_format')
            parts[reply[4]] = reply[6:26]
            if len(parts) == 42:
                raw = b''.join(parts[i] for i in range(42))
                if raw[:2] != b'\x02\x03' or self.current_profile() != profile:
                    raise LightingError('rgb_profile')
                return raw
        raise LightingError('rgb_format')

    def current_profile(self):
        for attempt in range(3):
            self.send(0xa1)
            try:
                value = self.response(0xa1, .7)[5]
                break
            except LightingError as e:
                if e.key != 'rgb_timeout' or attempt == 2:
                    raise
        if value > 7:
            raise LightingError('rgb_profile')
        return value

    def read(self):
        profile = self.current_profile()
        self.send(0xa7, bytes([profile, 20]))
        parts = {}
        for _ in range(32):
            reply = self.response(0xa7)
            if reply[3] != 16 or reply[4] >= 16 or reply[5] != profile:
                raise LightingError('rgb_format')
            parts[reply[4]] = reply[6:26]
            if len(parts) == 16:
                config = Config(self.device, profile, b''.join(parts[i] for i in range(16)))
                if self.current_profile() != profile:
                    raise LightingError('rgb_profile')
                return config
        raise LightingError('rgb_format')

    def write(self, before, after, backup_dir=None):
        if before.device != self.device or before.profile != after.profile:
            raise LightingError('rgb_profile')
        current = self.read()
        if current != before:
            raise LightingError('rgb_stale')
        info = self.information()
        if not 0x7141 <= info['firmware_value'] < 0x7200:
            raise LightingError('rgb_unsupported')
        if info['access'].owner:
            raise LightingError('device_owned', info['access'].owner)
        mapping = self.mapping(before.profile)
        if backup_dir is not None:
            directory = Path(backup_dir)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / ('mapping-before-rgb-%d-profile%d.json' % (time.time_ns(), before.profile + 1))
            with path.open('x', encoding='utf-8') as stream:
                json.dump({'device': self.device, 'profile': before.profile, 'raw': mapping.hex()}, stream, indent=2)
        if self.current_profile() != before.profile:
            raise LightingError('rgb_profile')
        # Complete transaction: the MCU notifies its LED coprocessor at the end.
        # Keep reserved RGB fields from the read snapshot.
        self.request(0xa8, bytes([before.profile, 0, 16, 20]))
        for index in range(16):
            self.request(0xa9, bytes([index]) + after.raw[index * 20:(index + 1) * 20])
        result = self.read()
        if result != after:
            raise LightingError('rgb_verify')
        if self.mapping(before.profile) != mapping:
            raise LightingError('rgb_stale')
        # Preserve the two version bytes exactly; AA writes both back verbatim.
        # Its firmware callback also requests delivery to the LED coprocessor.
        ack = self.request(0xaa, mapping[225:227], timeout=10)
        if ack[4] != 0:
            raise LightingError('rgb_save')
        time.sleep(.15)
        result = self.read()
        if result != after or self.mapping(before.profile) != mapping:
            raise LightingError('rgb_verify')
        return result


def backup(config, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('rgb-%s-%d-profile%d.json' %
                        (time.strftime('%Y%m%d-%H%M%S'), time.time_ns(), config.profile + 1))
    with path.open('x', encoding='utf-8') as f:
        json.dump({'device': config.device, 'profile': config.profile,
                   'raw': config.raw.hex()}, f, indent=2)
    return path


def read_config():
    with Receiver() as receiver:
        return receiver.read()


def apply_config(before, after, backup_dir):
    backup(before, backup_dir)
    with Receiver(before.device) as receiver:
        return receiver.write(before, after, backup_dir=backup_dir)
