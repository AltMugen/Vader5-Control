"""Windows vendor HID transport via the bundled SDL HIDAPI (no USB driver install)."""
import ctypes as C
from pathlib import Path
import threading
from protocol import DeviceError

_library = None
_guard = threading.Lock()


class HIDInfo(C.Structure):
    pass


HIDInfo._fields_ = [('path', C.c_char_p), ('vendor_id', C.c_ushort),
    ('product_id', C.c_ushort), ('serial_number', C.c_wchar_p),
    ('release_number', C.c_ushort), ('manufacturer_string', C.c_wchar_p),
    ('product_string', C.c_wchar_p), ('usage_page', C.c_ushort),
    ('usage', C.c_ushort), ('interface_number', C.c_int),
    ('interface_class', C.c_int), ('interface_subclass', C.c_int),
    ('interface_protocol', C.c_int), ('bus_type', C.c_int),
    ('next', C.POINTER(HIDInfo))]


def library():
    global _library
    with _guard:
        if _library is None:
            dll = Path(__file__).resolve().parent / 'SDL3.dll'
            lib = C.CDLL(str(dll))
            for name, result, args in (
                ('SDL_hid_init', C.c_int, []),
                ('SDL_hid_enumerate', C.POINTER(HIDInfo), [C.c_ushort, C.c_ushort]),
                ('SDL_hid_free_enumeration', None, [C.POINTER(HIDInfo)]),
                ('SDL_hid_open_path', C.c_void_p, [C.c_char_p]),
                ('SDL_hid_close', None, [C.c_void_p]),
                ('SDL_hid_write', C.c_int, [C.c_void_p, C.c_void_p, C.c_size_t]),
                ('SDL_hid_read_timeout', C.c_int, [C.c_void_p, C.c_void_p, C.c_size_t, C.c_int])):
                fn = getattr(lib, name); fn.restype = result; fn.argtypes = args
            if lib.SDL_hid_init() < 0:
                raise DeviceError('rgb_missing')
            _library = lib
        return _library


def endpoints():
    lib = library()
    head = lib.SDL_hid_enumerate(0x37d7, 0x2401)
    result = []
    try:
        item = head
        while item:
            info = item.contents
            # Usage survives the interface-number change in newer receiver firmware.
            if info.path and info.usage_page == 0xffa0 and info.usage == 1:
                path = info.path.decode('utf-8')
                result.append((path, path))
            item = info.next
    finally:
        lib.SDL_hid_free_enumeration(head)
    return sorted(set(result))


class Transport:
    def __init__(self, path):
        self.lib = library()
        self.handle = self.mutex = None
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [C.c_void_p, C.c_bool, C.c_wchar_p]
        self.kernel.CreateMutexW.restype = C.c_void_p
        self.kernel.ReleaseMutex.argtypes = [C.c_void_p]
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.mutex = self.kernel.CreateMutexW(None, True, 'Local\\Vader5Control-VendorHID')
        if not self.mutex:
            raise C.WinError(C.get_last_error())
        if C.get_last_error() == 183:
            self.kernel.CloseHandle(self.mutex); self.mutex = None
            raise DeviceError('rgb_busy')
        self.handle = self.lib.SDL_hid_open_path(path.encode('utf-8'))
        if not self.handle:
            self.close()
            raise DeviceError('rgb_permission')

    def send(self, packet):
        # Windows HID includes report-ID0 before the 32 output data bytes.
        packet = packet.ljust(33, b'\0')
        buf = C.create_string_buffer(packet)
        if self.lib.SDL_hid_write(self.handle, buf, len(packet)) != len(packet):
            raise DeviceError('rgb_write')

    def receive(self, timeout):
        buf = C.create_string_buffer(64)
        count = self.lib.SDL_hid_read_timeout(self.handle, buf, 64, max(1, int(timeout*1000)))
        if count < 0:
            raise DeviceError('rgb_missing')
        return buf.raw[:count]

    def close(self):
        if self.handle:
            self.lib.SDL_hid_close(self.handle); self.handle = None
        if self.mutex:
            self.kernel.ReleaseMutex(self.mutex)
            self.kernel.CloseHandle(self.mutex); self.mutex = None
