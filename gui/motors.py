"""Motor fields in the Space Station legacy V3 profile, verified on F5 7.1.5.3.

Write changed 20-byte blocks only. Do not use these offsets for refactored V5
profiles. Flash commit is deliberately separate and not exposed here.
"""
from dataclasses import dataclass
from pathlib import Path
import json,time
from lighting import Receiver
from protocol import DeviceError


@dataclass(frozen=True)
class Settings:
    device: str
    profile: int
    raw: bytes

    def __post_init__(self):
        if (len(self.raw)!=840 or self.raw[:2]!=b'\x02\x03' or
                not 0<=self.profile<8 or self.raw[145] not in (0,255) or
                self.raw[154] not in (0,1) or any(self.raw[i]>100 for i in (149,153,160,174))):
            raise DeviceError('motor_format')

    @property
    def gains(self):return tuple(self.raw[i] for i in (149,153,160,174))

    @property
    def enabled(self):return (self.raw[145]==0,self.raw[154]==0)

    @property
    def trigger_settings(self):
        # Linear and Micro are independent seven-byte records per trigger.
        return tuple(tuple(self.raw[i:i+6]) for i in (155,169))

    def changed(self,gains,enabled,triggers=None):
        if len(gains)!=4 or any(not isinstance(v,int) or not 0<=v<=100 for v in gains):
            raise DeviceError('motor_format')
        raw=bytearray(self.raw)
        for i,v in zip((149,153,160,174),gains):raw[i]=v
        if len(enabled)!=2 or any(type(v) is not bool for v in enabled):
            raise DeviceError('motor_format')
        if triggers is not None:
            if len(triggers)!=2:
                raise DeviceError('motor_format')
            for base, values in zip((155,169),triggers):
                if (len(values)!=5 or values[0] not in (0,1,2,255) or
                        any(type(v) is not int or not 0<=v<=255 for v in values) or
                        values[1]>values[2]):
                    raise DeviceError('motor_format')
                raw[base:base+5]=bytes(values)
        raw[145]=0 if enabled[0] else 255
        raw[154]=0 if enabled[1] else 1
        return Settings(self.device,self.profile,bytes(raw))


def read_session(session):
    profile=session.current_profile()
    session.send(0xa3,bytes([profile,20]));parts={}
    for _ in range(84):
        r=session.response(0xa3)
        if r[3]!=42 or r[4]>=42 or r[5]!=profile:raise DeviceError('motor_format')
        parts[r[4]]=r[6:26]
        if len(parts)==42:
            if session.current_profile()!=profile:raise DeviceError('rgb_profile')
            return Settings(session.device,profile,b''.join(parts[i] for i in range(42)))
    raise DeviceError('motor_format')


def read():
    with Receiver() as s:return read_session(s)


def backup(settings,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/('motors-%d-profile%d.json'%(time.time_ns(),settings.profile+1))
    with path.open('x', encoding='utf-8') as f:json.dump({'device':settings.device,'profile':settings.profile,'raw':settings.raw.hex()},f,indent=2)
    return path


def apply(before,after,directory):
    if (before.device,before.profile)!=(after.device,after.profile):raise DeviceError('rgb_profile')
    allowed={145,149,153,154,160,174,*range(155,160),*range(169,174)}
    if any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(before.raw,after.raw))):
        raise DeviceError('motor_format')
    with Receiver(before.device) as s:
        info=s.information()
        if not 0x7141<=info['firmware_value']<0x7200:raise DeviceError('motor_format')
        if info['access'].owner:raise DeviceError('device_owned',info['access'].owner)
        current=read_session(s)
        if current!=before:raise DeviceError('rgb_stale')
        backup(before,directory)
        chunks=[i for i in range(42) if before.raw[i*20:i*20+20]!=after.raw[i*20:i*20+20]]
        for i in chunks:
            if s.current_profile()!=before.profile:raise DeviceError('rgb_profile')
            s.request(0xa4,bytes([before.profile,i,1,20]))
            s.request(0xa5,bytes([0])+after.raw[i*20:i*20+20])
        result=read_session(s)
        if result!=after:raise DeviceError('motor_verify')
        return result
