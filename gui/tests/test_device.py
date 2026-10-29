"""Protocol fixtures from the official SDK and failure-path integration checks."""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import device
import lighting
import motors
from protocol import AccessStatus, DeviceInfo, DeviceError, command_packet, normalize_reply


def reply(command, data):
    value = bytearray(32)
    value[:3] = bytes([0x5a, 0xa5, command])
    value[3:3 + len(data)] = data
    value[-1] = sum(value[2:-1]) & 255
    return bytes(value)


def info_frame(version=0x7141, model=130):
    value = bytearray(reply(1, bytes([1, 0, model, 2])))
    value[11] = 4
    value[15:17] = version.to_bytes(2, 'big')
    value[17:19] = b'\x04\x83'
    value[-1] = sum(value[2:-1]) & 255
    return bytes(value)


def config():
    raw=bytearray(320)
    raw[:2]=b'\x00\x03';raw[5:9]=bytes([15,75,10,5])
    raw[9:20]=bytes(range(11))  # GripSync and reserved bytes must survive.
    return lighting.Config('receiver',0,bytes(raw))


class DeviceTests(unittest.TestCase):
    def test_official_nullable_access_packet(self):
        # SDK positions 5..9: preserve four fields and enable only permission.
        self.assertEqual(command_packet(0x11,b'\xff\xff\xff\xff\x01'),
                         bytes.fromhex('005aa51107ffffffff0115')+bytes(21))
        with self.assertRaises(ValueError):command_packet(1,bytes(27))

    def test_status_with_and_without_report_id_and_corruption(self):
        raw=reply(0x10,b'\x01\x00\x01\x00\x00\x00\x01SDL')
        for frame in (raw,b'\x00'+raw):
            status=AccessStatus.parse(normalize_reply(frame))
            self.assertTrue(status.enabled);self.assertEqual(status.owner,'SDL')
        damaged=bytearray(raw);damaged[9]^=1
        with self.assertRaises(DeviceError):normalize_reply(damaged)
        self.assertIsNone(normalize_reply(b'\x5a\xa5'))

    def test_motor_edits_preserve_all_other_profile_bytes(self):
        raw=bytearray(840);raw[:2]=b'\x02\x03'
        raw[145]=0;raw[154]=1
        before=motors.Settings('receiver',0,bytes(raw))
        after=before.changed((60,60,1,1),(True,False))
        changed={i for i,(a,b) in enumerate(zip(before.raw,after.raw)) if a!=b}
        self.assertEqual(changed,{149,153,160,174})
        self.assertEqual(after.gains,(60,60,1,1))
        with self.assertRaises(DeviceError):motors.Settings('receiver',0,bytes(840))

    def test_trigger_controls_preserve_micro_and_reserved_fields(self):
        raw=bytearray(840);raw[:2]=b'\x02\x03';raw[154]=1
        raw[162:169]=bytes(range(7));raw[176:183]=bytes(range(7,14))
        before=motors.Settings('receiver',6,bytes(raw))
        after=before.changed((50,60,20,30),(True,True),((1,0,255,1,1),(2,0,255,1,1)))
        allowed={145,149,153,154,160,174,*range(155,160),*range(169,174)}
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(before.raw,after.raw))))
        self.assertEqual(after.raw[162:169],before.raw[162:169])
        self.assertEqual(after.raw[176:183],before.raw[176:183])
        self.assertEqual(after.trigger_settings[0],(1,0,255,1,1,20))
        with self.assertRaises(DeviceError):
            before.changed((1,1,1,1),(True,True),((1,255,0,1,1),(2,0,255,1,1)))

    def test_wire_profile_bank_is_not_folded_on_read(self):
        receiver=object.__new__(lighting.Receiver);receiver.device='receiver'
        with patch.object(receiver,'send'),patch.object(receiver,'response',return_value=reply(0xa1,b'\0\0\x06')):
            self.assertEqual(receiver.current_profile(),6)
        original=config()
        banked=lighting.Config(original.device,6,original.raw)
        self.assertEqual(banked.changed('flow',50,15,[]).profile,6)
        frames=[reply(0xa7,bytes([16,i,6])+original.raw[i*20:(i+1)*20]) for i in range(16)]
        with patch.object(receiver,'current_profile',return_value=6),patch.object(receiver,'send') as send,patch.object(receiver,'response',side_effect=frames):
            self.assertEqual(receiver.read(),banked)
            send.assert_called_once_with(0xa7,bytes([6,20]))

    def test_motor_transaction_preserves_bank_and_checks_readback(self):
        raw=bytearray(840);raw[:2]=b'\x02\x03'
        before=motors.Settings('receiver',6,bytes(raw))
        after=before.changed((10,20,30,40),(True,True))
        class FakeReceiver:
            device='receiver'
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def information(self):return {'firmware_value':0x7154,'access':AccessStatus(True,'',(1,0,0,0,1))}
            def current_profile(self):return 6
            def request(self,*args):pass
        fake=FakeReceiver()
        with tempfile.TemporaryDirectory() as directory,patch.object(motors,'Receiver',return_value=fake),patch.object(motors,'read_session',side_effect=[before,after]),patch.object(fake,'request') as request:
            self.assertEqual(motors.apply(before,after,directory),after)
            headers=[call.args for call in request.call_args_list if call.args[0]==0xa4]
            self.assertTrue(headers)
            self.assertTrue(all(payload[0]==6 for command,payload in headers))
            self.assertEqual(len(list(Path(directory).glob('*.json'))),1)
        with tempfile.TemporaryDirectory() as directory,patch.object(motors,'Receiver',return_value=fake),patch.object(motors,'read_session',return_value=after),patch.object(fake,'request') as request:
            with self.assertRaisesRegex(DeviceError,'rgb_stale'):motors.apply(before,after,directory)
            request.assert_not_called()

    def test_captured_7153_heartbeat_trailer(self):
        # Actual receiver reply, unlike configuration replies its trailer is not
        # sum(bytes[2:31]). Retain strict model/header validation for this case.
        raw=bytes.fromhex('5aa50101008202000000000345010071530467351700000000000010261f0034')
        info=DeviceInfo.parse(normalize_reply(raw))
        self.assertEqual(info.firmware,0x7153)
        self.assertEqual(info.battery_level,3)
        damaged=bytearray(raw);damaged[5]=149
        with self.assertRaises(DeviceError):normalize_reply(damaged)

    def test_information_is_model_checked_and_battery_is_discrete(self):
        info=DeviceInfo.parse(info_frame())
        self.assertEqual(info.firmware,0x7141)
        self.assertEqual(info.battery_level,4)
        with self.assertRaises(DeviceError):DeviceInfo.parse(info_frame(model=149))

    def test_refactored_firmware_never_writes_sdk_access_setter(self):
        session=object.__new__(device.Session)
        session.information=lambda:{'access_writable':False}
        with patch.object(session,'send') as send:
            with self.assertRaisesRegex(DeviceError,'access_unsupported'):session.enable_access()
            send.assert_not_called()

    def test_access_button_can_enable_and_disable_only_permission(self):
        for enabled in (False,True):
            session=object.__new__(device.Session)
            original=AccessStatus(not enabled,'',(1,0,0,0,int(not enabled)))
            changed=AccessStatus(enabled,'',(1,0,0,0,int(enabled)))
            states=[{'access_writable':True,'access':original}, {'access':changed}]
            with patch.object(session,'information',side_effect=states),patch.object(session,'send') as send,patch.object(device.time,'sleep'):
                result=session.set_access(enabled)
                send.assert_called_once_with(0x11,b'\xff\xff\xff\xff'+bytes([enabled]))
                self.assertEqual(result['access'].enabled,enabled)

    def test_motor_stop_is_sent_if_wait_fails(self):
        class FakeSession:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def access_status(self):return AccessStatus(True,'',(0,0,0,0,1))
            def send(self,*args):calls.append(args)
        calls=[]
        with patch.object(device,'Session',FakeSession),patch.object(device.time,'sleep',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):device.test_motors(20,30,40,50)
        self.assertEqual(calls,[(0x12,bytes([20,30,40,50])),(0x12,bytes(4))])

    def test_rgb_editor_preserves_other_fields_and_roundtrips_ten_channels(self):
        before=config()
        frames=[['#%02x0000'%i for i in range(10)],['#00%02x00'%i for i in range(10)]]
        after=before.custom(frames,60,20,'breathing')
        self.assertEqual(after.keyframes,frames)
        self.assertEqual(after.raw[9:20],before.raw[9:20])
        self.assertEqual(after.frames[1],[(0,0,0)]*10)
        with tempfile.TemporaryDirectory() as directory:
            first=lighting.backup(before,directory);second=lighting.backup(before,directory)
            self.assertNotEqual(first,second)

    def test_stale_rgb_or_changed_profile_cannot_send_any_write(self):
        before=config();after=before.custom([['#ff0000']*10],75,15)
        receiver=object.__new__(lighting.Receiver);receiver.device='receiver'
        receiver.read=lambda:after
        with patch.object(receiver,'send') as send:
            with self.assertRaisesRegex(DeviceError,'rgb_stale'):receiver.write(before,after)
            send.assert_not_called()

    def test_rgb_commit_preserves_version_and_sends_full_transaction(self):
        before=config();after=before.changed('solid',65,20,['#123456'])
        mapping=bytearray(840);mapping[:2]=b'\x02\x03';mapping[225:227]=b'\x12\xab'
        receiver=object.__new__(lighting.Receiver);receiver.device='receiver'
        info={'firmware_value':0x7154,'access':AccessStatus(True,'',(1,0,0,0,1))}
        with patch.object(receiver,'read',side_effect=[before,after,after]),patch.object(receiver,'mapping',return_value=bytes(mapping)),patch.object(receiver,'information',return_value=info),patch.object(receiver,'current_profile',return_value=0),patch.object(receiver,'request',return_value=reply(0xaa,b'\x01\0')) as request,patch.object(lighting.time,'sleep'):
            self.assertEqual(receiver.write(before,after),after)
            calls=request.call_args_list
            self.assertEqual(calls[0].args,(0xa8,bytes([0,0,16,20])))
            self.assertEqual([c.args[1] for c in calls[1:17]],
                             [bytes([i])+after.raw[i*20:(i+1)*20] for i in range(16)])
            self.assertEqual(calls[-1].args,(0xaa,b'\x12\xab'))

    def test_rgb_changed_mapping_blocks_flash_commit(self):
        before=config();after=before.changed('solid',60,15,['#abcdef'])
        receiver=object.__new__(lighting.Receiver);receiver.device='receiver'
        info={'firmware_value':0x7154,'access':AccessStatus(True,'',(1,0,0,0,1))}
        with patch.object(receiver,'read',side_effect=[before,after]),patch.object(receiver,'mapping',side_effect=[bytes(840),bytes([1])*840]),patch.object(receiver,'information',return_value=info),patch.object(receiver,'current_profile',return_value=0),patch.object(receiver,'request') as request:
            with self.assertRaisesRegex(DeviceError,'rgb_stale'):receiver.write(before,after)
            self.assertFalse(any(c.args[0]==0xaa for c in request.call_args_list))
        receiver.device='other receiver'
        with patch.object(receiver,'send') as send:
            with self.assertRaisesRegex(DeviceError,'rgb_profile'):receiver.write(before,after)
            send.assert_not_called()


if __name__=='__main__':unittest.main()
