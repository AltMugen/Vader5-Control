import ctypes as C
from pathlib import Path
import importlib.util
import sys
import types
import unittest
from unittest.mock import Mock, patch

import hid_windows
from protocol import command_packet, DeviceError


class WindowsTransportTests(unittest.TestCase):
    def test_vendor_usage_selects_new_interface_and_deduplicates(self):
        keyboard = hid_windows.HIDInfo(path=b'keyboard', usage_page=1, usage=6, interface_number=1)
        vendor = hid_windows.HIDInfo(path=b'vendor', usage_page=0xffa0, usage=1, interface_number=2)
        duplicate = hid_windows.HIDInfo(path=b'vendor', usage_page=0xffa0, usage=1, interface_number=2)
        keyboard.next = C.pointer(vendor);vendor.next = C.pointer(duplicate)
        lib = Mock();lib.SDL_hid_enumerate.return_value = C.pointer(keyboard)
        with patch.object(hid_windows, 'library', return_value=lib):
            self.assertEqual(hid_windows.endpoints(), [('vendor','vendor')])
        lib.SDL_hid_free_enumeration.assert_called_once()

    def test_windows_output_keeps_report_id_and_32_data_bytes(self):
        transport = object.__new__(hid_windows.Transport)
        transport.handle = 123;transport.lib = Mock()
        seen = []
        def write(handle, buf, count):
            seen.append((handle,C.string_at(buf,count)))
            return count
        transport.lib.SDL_hid_write.side_effect = write
        packet = command_packet(0x12, bytes([10,20,0,0]))
        transport.send(packet)
        self.assertEqual(seen, [(123,packet+b'\0')])
        transport.lib.SDL_hid_write.return_value = -1
        transport.lib.SDL_hid_write.side_effect = None
        with self.assertRaisesRegex(DeviceError,'rgb_write'):transport.send(packet)

    def test_steam_registry_location_on_non_system_drive(self):
        registry = types.SimpleNamespace(HKEY_CURRENT_USER=1,HKEY_LOCAL_MACHINE=2,
            KEY_WOW64_64KEY=256,KEY_WOW64_32KEY=512,KEY_READ=1)
        class Handle:
            def __enter__(self):return self
            def __exit__(self,*args):pass
        registry.OpenKey=lambda *args:Handle()
        registry.QueryValueEx=lambda handle,key:(r'E:\Games\Steam' if key=='SteamPath' else '',1)
        path=Path(__file__).resolve().parents[1]/'platform_windows.py'
        spec=importlib.util.spec_from_file_location('windows_test_platform',path)
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'winreg':registry}):spec.loader.exec_module(module)
        with patch.dict('os.environ',{},clear=True),patch.object(Path,'is_file',return_value=True):
            self.assertEqual(str(module.steam_directory()),r'E:\Games\Steam')

    def test_tasklist_localized_output_does_not_require_utf8(self):
        path=Path(__file__).resolve().parents[1]/'platform_windows.py'
        spec=importlib.util.spec_from_file_location('windows_tasklist_test',path)
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'winreg':types.SimpleNamespace()}):spec.loader.exec_module(module)
        result=types.SimpleNamespace(returncode=0,stdout=b'\x88 No tasks found\r\n',stderr=b'')
        with patch.object(module.subprocess,'CREATE_NO_WINDOW',0,create=True),patch.object(module.subprocess,'run',return_value=result):
            self.assertFalse(module.steam_running())
            result.stdout=b'"steam.exe","123","Console","1","100 K"\r\n'
            self.assertTrue(module.steam_running())

if __name__ == '__main__':unittest.main()
