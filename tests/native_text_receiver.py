
import ctypes
import os
import threading
import time
from ctypes import wintypes


class TextReceiver:
    def __init__(self):
        self.messages = []
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        assert self.ready.wait(5)
        if self.error:
            raise self.error

    def run(self):
        try:
            api = self.api = ctypes.WinDLL('user32', use_last_error=True)
            api.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
            api.CreateWindowExW.restype = wintypes.HWND
            api.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            api.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            api.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            api.CallWindowProcW.restype = ctypes.c_ssize_t
            api.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            api.SendMessageW.restype = ctypes.c_ssize_t
            api.DestroyWindow.argtypes = [wintypes.HWND]
            api.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            api.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
            api.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
            api.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
            api.DispatchMessageW.restype = ctypes.c_ssize_t
            self.hwnd = api.CreateWindowExW(0x08000000, 'STATIC', 'Nexo QA: receptor propio', 0x00CF0000, 30, 30, 400, 180, None, None, None, None)
            self.edit = api.CreateWindowExW(0, 'EDIT', '', 0x50000004, 8, 8, 360, 100, self.hwnd, None, None, None)
            assert self.hwnd and self.edit
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            previous = {}
            def receive(hwnd, msg, wp, lp):
                if 0x100 <= msg <= 0x109:
                    self.messages.append((int(hwnd), msg, int(wp), int(lp)))
                return api.CallWindowProcW(previous[hwnd], hwnd, msg, wp, lp)
            self.callback = callback_type(receive)
            for hwnd in (self.hwnd, self.edit):
                previous[hwnd] = api.SetWindowLongPtrW(hwnd, -4, ctypes.cast(self.callback, ctypes.c_void_p).value)
            api.ShowWindow(self.hwnd, 4)
            self.ready.set()
            message = wintypes.MSG()
            while not self.stop.is_set():
                while api.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    api.TranslateMessage(ctypes.byref(message))
                    api.DispatchMessageW(ctypes.byref(message))
                time.sleep(.001)
            for hwnd in (self.edit, self.hwnd):
                api.SetWindowLongPtrW(hwnd, -4, previous[hwnd])
            api.DestroyWindow(self.hwnd)
        except Exception as exc:
            self.error = exc
            self.ready.set()

    def text(self):
        buffer = ctypes.create_unicode_buffer(4096)
        self.api.SendMessageW(self.edit, 0xD, 4096, ctypes.addressof(buffer))
        return buffer.value

    def close(self):
        self.stop.set()
        self.thread.join(3)
        assert not self.thread.is_alive()
