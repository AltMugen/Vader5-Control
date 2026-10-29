import ctypes as C
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import backend
import bluetooth_setup
from protocol import DeviceError


class BluetoothSetupTests(unittest.TestCase):
    def test_nonblocking_start_keeps_connection_worker_alive(self):
        reader=backend.InputReader()
        library=Mock();library.SDL_Init.return_value=True
        with patch.object(backend,'active',return_value=False),patch.object(backend,'steam_running',return_value=False),patch.object(backend.C,'CDLL',return_value=library),patch.object(backend.time,'monotonic',return_value=100),patch.object(reader,'_open_available') as available:
            reader.start(wait=False)
            self.assertTrue(reader.waiting)
            self.assertEqual(reader.connect_deadline,115)
            available.assert_not_called()
            library.SDL_QuitSubSystem.assert_not_called()
        reader.close()

    def test_selection_is_saved_in_driver_format(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'vader5/bluetooth'
            with patch.object(bluetooth_setup, 'config_path', return_value=target):
                bluetooth_setup.save_selection({'address':'aa:bb:cc:dd:ee:01',
                                                'adapter':'11:22:33:44:55:66'})
            self.assertEqual(target.read_text(), 'AA:BB:CC:DD:EE:01\n11:22:33:44:55:66\n')
            if os.name != 'nt':
                self.assertEqual(target.stat().st_mode & 0o077, 0)

    def test_invalid_address_does_not_replace_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'bluetooth'
            target.write_text('original')
            with patch.object(bluetooth_setup, 'config_path', return_value=target):
                with self.assertRaises(DeviceError):
                    bluetooth_setup.save_selection({'address':'aa:bb:cc:dd:ee:ff\nmalformed'})
            self.assertEqual(target.read_text(), 'original')

    def test_windows_selection_does_not_require_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'bluetooth'
            with patch.object(bluetooth_setup, 'config_path', return_value=target):
                bluetooth_setup.save_selection({'address':'AA:BB:CC:DD:EE:01'})
            self.assertEqual(target.read_text(), 'AA:BB:CC:DD:EE:01\n\n')

    def test_name_matching_excludes_other_models(self):
        self.assertTrue(bluetooth_setup.controller_name('Flydigi Vader 5 Pro'))
        self.assertFalse(bluetooth_setup.controller_name('Flydigi Vader 4 Pro'))
        self.assertFalse(bluetooth_setup.controller_name('Flydigi Vader 5 Pro Fake'))

    def test_waiting_timeout_closes_sdl(self):
        reader = backend.InputReader()
        reader.sdl = Mock()
        reader.waiting = True
        reader.bluetooth_address = 'aa:bb:cc:dd:ee:01'
        reader.connect_deadline = 0
        with patch.object(reader, '_open_available', return_value=False):
            with self.assertRaisesRegex(DeviceError, 'bt_timeout'):
                reader.poll()
        self.assertFalse(reader.waiting)
        reader.sdl.SDL_QuitSubSystem.assert_called_once()

    def test_selected_bluetooth_is_not_replaced_by_usb(self):
        reader = backend.InputReader()
        reader.sdl = Mock()
        reader.bluetooth_address = 'aa:bb:cc:dd:ee:01'
        def gamepads(count):
            C.cast(count, C.POINTER(C.c_int)).contents.value = 2
            return [10, 20]
        reader.sdl.SDL_GetGamepads.side_effect = gamepads
        reader.sdl.SDL_GetGamepadNameForID.return_value = b'Flydigi Vader 5 Pro'
        reader.sdl.SDL_GetGamepadPathForID.side_effect = [b'USB', b'AA:BB:CC:DD:EE:01']
        reader.sdl.SDL_OpenGamepad.return_value = 123
        reader.sdl.SDL_GamepadHasSensor.return_value = False
        self.assertTrue(reader._open_available())
        reader.sdl.SDL_OpenGamepad.assert_called_once_with(20)
