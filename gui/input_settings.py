"""Legacy V3.2 analog settings. Offsets mirror Space Station's V30/V31 codec.

Only A3/A4/A5 are used; no profile switching, calibration or flash commit.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import time
from lighting import Receiver
from protocol import DeviceError

STICK_OFFSETS = frozenset((*range(109,123), *range(790,814)))
TRIGGER_OFFSETS = frozenset(range(123,137))


def build_stick_curve(center,end,power=1):
    """Nine-point radial template; differs from Space Station presets.

    Negative levels allow an interpolated zero crossing between sample points.
    MCU storage limits the negative tail to -50; 9 samples approximate corners.
    """
    if (type(center) is not int or type(end) is not int or
            not 0<=center<end<=100 or power not in (.5,1,2)):
        raise DeviceError('input_format')
    result=[]
    for i in range(9):
        value=(i*12.5-center)/(end-center)
        level=value*100 if value<0 else min(value,1)**power*100
        result.append(max(-50,min(100,round(level))))
    return tuple(result)


def build_trigger_curve(center,end):
    """Linear trigger template using P1/P2; keep MCU Zero/End at 0/255.

    This avoids the extra output rescale and the clamp End=max(End,P2.X).
    """
    if type(center) is not int or type(end) is not int or not 0<=center<end<=100:
        raise DeviceError('input_format')
    return (3,0,round(center*255/100),0,round(end*255/100),255,255)


def signed_field(value):
    return value if value <= 127 else 127-value


def encode_signed(value):
    if type(value) is not int or not -128 <= value <= 127:
        raise DeviceError('input_format')
    return value if value >= 0 else 127-value


@dataclass(frozen=True)
class Profile:
    device: str
    profile: int
    raw: bytes

    def __post_init__(self):
        if len(self.raw)!=840 or self.raw[:2]!=b'\x02\x03' or not 0<=self.profile<8:
            raise DeviceError('input_format')

    def stick(self,side):
        base=109+7*side;extra=790+12*side
        return {'center':signed_field(self.raw[base+1]), 'end':signed_field(self.raw[base+6]),
                'points':tuple(v-50 for v in self.raw[extra+1:extra+10]),
                'shape':self.raw[extra+10], 'edge':signed_field(self.raw[extra+11]),
                'type':self.raw[extra]}

    def changed_sticks(self,values):
        if len(values)!=2:raise DeviceError('input_format')
        raw=bytearray(self.raw)
        for side,value in enumerate(values):
            original=self.stick(side)
            base=109+side*7;extra=790+side*12
            if (len(value['points'])!=9 or any(type(v) is not int or not -50<=v<=205 for v in value['points']) or
                    value['shape'] not in (0,1) or not value['center']<value['end']):
                raise DeviceError('input_format')
            raw[base+1]=encode_signed(value['center'])
            raw[base+6]=encode_signed(value['end'])
            raw[extra+10]=value['shape'];raw[extra+11]=encode_signed(value['edge'])
            if tuple(value['points'])!=original['points']:
                raw[base]=raw[extra]=3  # SDK Custom; preserve old two-point payload.
                raw[extra+1:extra+10]=bytes(v+50 for v in value['points'])
        return Profile(self.device,self.profile,bytes(raw))

    def trigger(self,side):
        return tuple(self.raw[123+side*7:130+side*7])

    def changed_triggers(self,values):
        if len(values)!=2:raise DeviceError('input_format')
        raw=bytearray(self.raw)
        for side,values_for_side in enumerate(values):
            if (len(values_for_side)!=7 or any(type(v) is not int or not 0<=v<=255 for v in values_for_side) or
                    values_for_side[0] not in (0,1,2,3) or values_for_side[3]>values_for_side[5] or
                    not values_for_side[1]<values_for_side[6] or
                    not values_for_side[1]<=values_for_side[2]<=values_for_side[4]<=values_for_side[6]):
                raise DeviceError('input_format')
            raw[123+side*7:130+side*7]=bytes(values_for_side)
        return Profile(self.device,self.profile,bytes(raw))


def read_session(session):
    profile=session.current_profile()
    session.send(0xa3,bytes([profile,20]));parts={}
    for _ in range(84):
        r=session.response(0xa3)
        if r[3]!=42 or r[4]>=42 or r[5]!=profile:raise DeviceError('input_format')
        parts[r[4]]=r[6:26]
        if len(parts)==42:
            if session.current_profile()!=profile:raise DeviceError('rgb_profile')
            return Profile(session.device,profile,b''.join(parts[i] for i in range(42)))
    raise DeviceError('input_format')


def read():
    with Receiver() as session:return read_session(session)


def backup(profile,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/('input-%d-bank%d.json'%(time.time_ns(),profile.profile))
    with path.open('x', encoding='utf-8') as f:
        json.dump({'device':profile.device,'profile':profile.profile,'raw':profile.raw.hex()},f,indent=2)
    return path


def apply(before,after,directory,allowed):
    if allowed not in (STICK_OFFSETS,TRIGGER_OFFSETS):raise DeviceError('input_format')
    if (before.device,before.profile)!=(after.device,after.profile):raise DeviceError('rgb_profile')
    if any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(before.raw,after.raw))):
        raise DeviceError('input_format')
    with Receiver(before.device) as session:
        info=session.information()
        if not 0x7141<=info['firmware_value']<0x7200:raise DeviceError('input_format')
        if info['access'].owner:raise DeviceError('device_owned',info['access'].owner)
        if read_session(session)!=before:raise DeviceError('rgb_stale')
        backup(before,directory)
        for i in range(42):
            chunk=after.raw[i*20:i*20+20]
            if chunk==before.raw[i*20:i*20+20]:continue
            if session.current_profile()!=before.profile:raise DeviceError('rgb_profile')
            session.request(0xa4,bytes([before.profile,i,1,20]))
            session.request(0xa5,bytes([0])+chunk)
        result=read_session(session)
        if result!=after:raise DeviceError('input_verify')
        return result
