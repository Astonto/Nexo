from __future__ import annotations
from .i18n import tr

import ctypes
import os
import logging
from ctypes import wintypes


def enable_dpi_awareness():
    if os.name == "nt":
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass


def monitor_rects():
    if os.name != "nt":
        return []
    rectangles = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def collect(monitor, dc, rect, data):
        r = rect.contents
        rectangles.append([r.left, r.top, r.right, r.bottom])
        return True
    callback = callback_type(collect)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, 0)
    return sorted(rectangles)


def point_on_screen(x, y):
    rectangles = monitor_rects()
    return not rectangles or any(l <= x < r and t <= y < b for l, t, r, b in rectangles)


def foreground_process():
    if os.name != "nt":
        return 0
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pid = wintypes.DWORD()
    hwnd = user32.GetForegroundWindow()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def application_windows():

    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, data):
        length = user32.GetWindowTextLengthW(hwnd)
        if user32.IsWindowVisible(hwnd) and length:
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != os.getpid():
                windows.append((int(hwnd), pid.value, title.value))
        return True
    callback = callback_type(collect)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows(callback, 0)
    return sorted(windows, key=lambda item: item[2].casefold())


class InputTarget:

    def __init__(self, hwnd=0, pid=0):
        self.hwnd, self.pid = hwnd, pid

    def activate(self, control, *, api=None, timeout=1.0, request=None):

        import time
        from .models import ValidationError
        if not self.hwnd:
            raise ValidationError(tr('Select a target window to use Activate window.'))
        api = api or ctypes.WinDLL('user32', use_last_error=True)
        api.IsWindow.argtypes = [wintypes.HWND]
        api.IsIconic.argtypes = [wintypes.HWND]
        api.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        api.SetForegroundWindow.argtypes = [wintypes.HWND]
        api.GetForegroundWindow.restype = wintypes.HWND
        api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        def valid():
            pid = wintypes.DWORD()
            api.GetWindowThreadProcessId(self.hwnd, ctypes.byref(pid))
            return api.IsWindow(self.hwnd) and pid.value == self.pid
        control.wait()
        if not valid():
            raise ValidationError(tr('The target window closed or changed. Select it again.'))
        def ask_windows():
            if not valid():
                raise ValidationError(tr('The target window closed or changed.'))
            logging.getLogger("macroflow.activation").info("activation_request target=%s pid=%s foreground_before=%s", self.hwnd, self.pid, api.GetForegroundWindow())

            api.ShowWindowAsync(self.hwnd, 9 if api.IsIconic(self.hwnd) else 5)
            accepted = api.SetForegroundWindow(self.hwnd)
            logging.getLogger("macroflow.activation").info("activation_call accepted=%s foreground_after=%s", bool(accepted), api.GetForegroundWindow())
        if request is not None:
            request(ask_windows, control)
        else:
            ask_windows()
        deadline = time.monotonic() + timeout
        while True:
            control.wait()
            if not valid():
                raise ValidationError(tr('The target window closed during activation.'))
            if api.GetForegroundWindow() == self.hwnd and not api.IsIconic(self.hwnd):
                return
            if time.monotonic() >= deadline:
                logging.getLogger("macroflow.activation").warning("activation_timeout target=%s foreground=%s", self.hwnd, api.GetForegroundWindow())
                raise ValidationError(tr('Windows did not allow window activation. Activate it manually and try again; no input was sent.'))
            control.wait(.02)

    def allows(self, event=None):
        if not self.hwnd:
            return True
        if os.name != "nt":
            return False
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        if user32.GetForegroundWindow() != self.hwnd or foreground_process() != self.pid:
            return False
        if event is not None and event.x is not None:
            rect = wintypes.RECT()
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
                return False
            return rect.left <= event.x < rect.right and rect.top <= event.y < rect.bottom
        return True


def is_elevated_process(pid):
    if os.name != "nt" or not pid:
        return False
    kernel32, advapi32 = ctypes.windll.kernel32, ctypes.windll.advapi32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    process = kernel32.OpenProcess(0x1000, False, pid)
    if not process:
        return True
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(process, 8, ctypes.byref(token)):
            return True
        elevated, size = wintypes.DWORD(), wintypes.DWORD()
        if not advapi32.GetTokenInformation(token, 20, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(size)):
            return True
        return bool(elevated.value)
    finally:
        if token:
            kernel32.CloseHandle(token)
        kernel32.CloseHandle(process)


def target_allowed():
    pid = foreground_process()
    return not pid or pid == os.getpid() or not is_elevated_process(pid) or is_elevated_process(os.getpid())


class PrivacyProbe:






    def __init__(self):
        self.automation = None
        self.initialized = False
        self.reason = ""
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            self.initialized = True
            module = comtypes.client.GetModule("UIAutomationCore.dll")
            self.automation = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=module.IUIAutomation)
        except Exception:
            self.reason = tr('Field protection unavailable; keyboard input skipped.')

    def allowed(self):
        if foreground_process() == os.getpid():
            self.reason = tr('Nexo controls excluded.')
            return False
        if self.automation is None:
            self.reason = tr('Could not verify the field; keyboard input skipped.')
            return False
        try:
            focused = self.automation.GetFocusedElement()
            if not focused:
                self.reason = tr('No verifiable field; keyboard input skipped.')
                return False
            password = focused.GetCurrentPropertyValue(30019)
            if password is None or bool(password):
                self.reason = tr('Protected field; keyboard input skipped.')
                return False
            self.reason = ""
            return True
        except Exception:
            self.reason = tr('Could not verify the field; keyboard input skipped.')
            return False

    def close(self):
        self.automation = None
        if self.initialized:
            import comtypes
            comtypes.CoUninitialize()
