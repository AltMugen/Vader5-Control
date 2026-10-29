"""Space Station layout fixtures and safety gates for analog/hardware edits."""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import input_settings as settings
import hardware_settings as hardware
from protocol import AccessStatus,DeviceError


def profile():
    raw=bytearray(840);raw[:2]=b'\x02\x03'
    raw[109:123]=bytes([0,5,63,63,127,127,127]*2)
    raw[123:137]=bytes([0,0,0,0,255,255,255]*2)
    raw[790:814]=bytes([0,45,58,71,84,97,110,123,137,150,0,0]*2)
    raw[145:183]=bytes(range(38))
    return settings.Profile('fixture',5,bytes(raw))


def status(flags=0x79,sleep=15):
    raw=bytearray(32);raw[:3]=b'\x5a\xa5\x03';raw[5]=0x79;raw[6]=flags;raw[9]=sleep
    return hardware.State('fixture',bytes(raw))


class InputTests(unittest.TestCase):
    def test_untouched_captured_profile_roundtrip(self):
        before=profile()
        self.assertEqual(before.changed_sticks([before.stick(i) for i in range(2)]),before)
        self.assertEqual(before.changed_triggers([before.trigger(i) for i in range(2)]),before)
        self.assertEqual(before.stick(0)['points'][0],-5)
        self.assertEqual(before.stick(0)['points'][-1],100)

    def test_custom_curve_deadzone_and_shape_preserve_all_other_bytes(self):
        before=profile();left,right=[before.stick(i) for i in range(2)]
        left.update(points=(0,2,6,14,25,39,56,77,100),center=2,shape=1,edge=-3)
        after=before.changed_sticks([left,right])
        self.assertEqual(after.stick(0),dict(left,type=3))
        self.assertEqual(after.raw[109],3);self.assertEqual(after.raw[790],3)
        self.assertEqual(after.raw[116:123],before.raw[116:123])
        self.assertEqual(after.raw[802:814],before.raw[802:814])
        self.assertTrue(all(a==b or i in settings.STICK_OFFSETS for i,(a,b) in enumerate(zip(before.raw,after.raw))))
        self.assertEqual(after.raw[145:183],before.raw[145:183])

    def test_curve_builder_encodes_dead_zone_and_saturation(self):
        self.assertEqual(settings.build_stick_curve(0,100),(0,12,25,38,50,62,75,88,100))
        points=settings.build_stick_curve(25,75)
        self.assertTrue(all(value<=0 for value in points[:3]))
        self.assertEqual(points[4],50)
        self.assertEqual(points[6:],(100,100,100))
        self.assertTrue(all(a<=b for a,b in zip(points,points[1:])))
        with self.assertRaises(DeviceError):settings.build_stick_curve(75,25)

    def test_trigger_template_avoids_zero_rescale_and_shortens_travel(self):
        self.assertEqual(settings.build_trigger_curve(0,100),(3,0,0,0,255,255,255))
        self.assertEqual(settings.build_trigger_curve(20,80),(3,0,51,0,204,255,255))
        before=profile();after=before.changed_triggers([settings.build_trigger_curve(20,80),before.trigger(1)])
        self.assertTrue(all(a==b or i in settings.TRIGGER_OFFSETS for i,(a,b) in enumerate(zip(before.raw,after.raw))))
        with self.assertRaises(DeviceError):settings.build_trigger_curve(80,20)

    def test_invalid_curve_and_trigger_ranges_are_rejected(self):
        before=profile();values=[before.stick(i) for i in range(2)]
        values[0]['points']=(0,)*8
        with self.assertRaises(DeviceError):before.changed_sticks(values)
        with self.assertRaises(DeviceError):before.changed_triggers([(3,20,10,0,255,255,255),before.trigger(1)])
        for value in range(-128,128):self.assertEqual(settings.signed_field(settings.encode_signed(value)),value)

    def test_input_write_is_narrow_and_stale_state_is_never_written(self):
        before=profile();values=[before.stick(i) for i in range(2)];values[0]['shape']=1
        after=before.changed_sticks(values)
        class Session:
            device='fixture'
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def current_profile(self):return 5
            def information(self):return {'firmware_value':0x7154,'access':AccessStatus(True,'',(1,0,0,0,1))}
            def request(self,*args):pass
        session=Session()
        with tempfile.TemporaryDirectory() as directory,patch.object(settings,'Receiver',return_value=session),patch.object(settings,'read_session',side_effect=[before,after]),patch.object(session,'request') as request:
            self.assertEqual(settings.apply(before,after,directory,settings.STICK_OFFSETS),after)
            self.assertEqual([c.args[0] for c in request.call_args_list],[0xa4,0xa5])
            self.assertEqual(request.call_args_list[0].args[1],bytes([5,40,1,20]))
            self.assertEqual(len(list(Path(directory).glob('input-*.json'))),1)
        for version,owner in ((0x7226,''),(0x7154,'SDL')):
            with tempfile.TemporaryDirectory() as directory,patch.object(settings,'Receiver',return_value=session),patch.object(session,'information',return_value={'firmware_value':version,'access':AccessStatus(True,owner,(1,0,0,0,1))}),patch.object(session,'request') as request:
                with self.assertRaises(DeviceError):settings.apply(before,after,directory,settings.STICK_OFFSETS)
                request.assert_not_called()
        with tempfile.TemporaryDirectory() as directory,patch.object(settings,'Receiver',return_value=session),patch.object(settings,'read_session',return_value=after),patch.object(session,'request') as request:
            with self.assertRaisesRegex(DeviceError,'rgb_stale'):settings.apply(before,after,directory,settings.STICK_OFFSETS)
            request.assert_not_called()

    def test_hardware_support_and_sleep_encodings(self):
        state=status()
        self.assertTrue(all(state.supported(k) for k in hardware.FLAGS))
        self.assertEqual(status(sleep=255).sleep,0)
        self.assertEqual(status(sleep=0).sleep,0)
        self.assertFalse(status(flags=0).enabled('debounce'))

    def test_hardware_writes_only_changed_supported_flags_and_verifies(self):
        before=status();after=status(flags=0x69,sleep=255)
        class Session:
            device='fixture'
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def information(self):return {'firmware_value':0x7154,'access':AccessStatus(True,'',(1,0,0,0,1))}
            def request(self,command,payload):
                reply=bytearray(32);reply[5]=payload[0];return bytes(reply)
        session=Session()
        with tempfile.TemporaryDirectory() as directory,patch.object(hardware,'Session',return_value=session),patch.object(hardware,'read_session',side_effect=[before,status(flags=0x69),after]),patch.object(session,'request',wraps=session.request) as request:
            result=hardware.apply(before,{'debounce':False,'rebound':True},0,directory)
            self.assertEqual(result,after)
            self.assertEqual([c.args for c in request.call_args_list],[(0x13,b'\x05\x00'),(0x17,b'\x00')])
        with tempfile.TemporaryDirectory() as directory,patch.object(hardware,'Session',return_value=session),patch.object(hardware,'read_session',return_value=after),patch.object(session,'request') as request:
            with self.assertRaisesRegex(DeviceError,'rgb_stale'):hardware.apply(before,{},0,directory)
            request.assert_not_called()

    def test_sleep_zero_is_explicit_and_none_preserves_factory_state(self):
        before=status(sleep=0)
        class Session:
            device='fixture'
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def information(self):return {'firmware_value':0x7154,'access':AccessStatus(True,'',(1,0,0,0,1))}
            def request(self,*args):return bytes(32)
        session=Session()
        for value,expected in ((None,[]),(0,[(0x17,b'\x00')])):
            with tempfile.TemporaryDirectory() as directory,patch.object(hardware,'Session',return_value=session),patch.object(hardware,'read_session',return_value=before),patch.object(session,'request') as request:
                hardware.apply(before,{},value,directory)
                self.assertEqual([c.args for c in request.call_args_list],expected)

if __name__=='__main__':unittest.main()
