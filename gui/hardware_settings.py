"""Hardware flags verified in Main 7.1.5.4 and official NewXInput SDK.

Rate/precision and unsupported SDK toggles are deliberately not writable here.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import time
from device import Session
from protocol import DeviceError

FLAGS = {'quick_switch':1,'mapping':4,'debounce':5,'auto_center':6,'rebound':7}


@dataclass(frozen=True)
class State:
    device: str
    raw: bytes

    def __post_init__(self):
        if len(self.raw)!=32 or self.raw[:3]!=b'\x5a\xa5\x03':raise DeviceError('input_format')

    def supported(self,name):return bool(self.raw[5] & (1 << (FLAGS[name]-1)))
    def enabled(self,name):return bool(self.raw[6] & (1 << (FLAGS[name]-1)))

    @property
    def sleep(self):
        # AF50 converts stored FF to 0. Factory 0 is indistinguishable here.
        return 0 if self.raw[9]==255 else self.raw[9]


def read_session(session):return State(session.device,session.request(0x03))


def read():
    with Session() as session:return read_session(session)


def apply(before,flags,sleep,directory):
    if (not set(flags)<=set(FLAGS) or any(type(v) is not bool for v in flags.values()) or
            (sleep is not None and (type(sleep) is not int or not 0<=sleep<=254))):raise DeviceError('input_format')
    with Session(before.device) as session:
        info=session.information()
        if not 0x7141<=info['firmware_value']<0x7200:raise DeviceError('input_format')
        if info['access'].owner:raise DeviceError('device_owned',info['access'].owner)
        if read_session(session)!=before:raise DeviceError('rgb_stale')
        if any(not before.supported(name) for name in flags):raise DeviceError('input_format')
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        with (directory/('hardware-%d.json'%time.time_ns())).open('x', encoding='utf-8') as f:
            json.dump({'device':before.device,'status':before.raw.hex(),
                       'flags':{k:before.enabled(k) for k in FLAGS},'sleep_minutes':before.sleep},f,indent=2)
        for name,value in flags.items():
            if value==before.enabled(name):continue
            command=FLAGS[name]
            reply=session.request(0x13,bytes([command,value]))
            if reply[5]!=command:raise DeviceError('input_verify')
            if read_session(session).enabled(name)!=value:raise DeviceError('input_verify')
        # Explicit zero must be sent even if status is zero: status cannot
        # distinguish factory fallback from disabled idle sleep.
        if sleep is not None and (sleep!=before.sleep or sleep==0):
            session.request(0x17,bytes([sleep]))
        result=read_session(session)
        untouched_mask=sum(1 << (value-1) for key,value in FLAGS.items() if key not in flags)
        if (result.raw[6]^before.raw[6]) & untouched_mask:raise DeviceError('input_verify')
        if (sleep is not None and result.sleep!=sleep) or any(result.enabled(k)!=v for k,v in flags.items()):raise DeviceError('input_verify')
        return result
