from __future__ import annotations
from .i18n import tr






import ctypes
import os
import logging
from ctypes import wintypes

from .models import Event, ValidationError

LOG = logging.getLogger("macroflow.background")


class NativeWindowMessages:
    def __init__(self, target):
        if os.name != "nt":
            raise ValidationError(tr('Sending input to a background window requires Windows.'))
        from .windows import is_elevated_process
        if is_elevated_process(target.pid) and not is_elevated_process(os.getpid()):
            raise ValidationError(tr('The target is running with higher privileges than Nexo.'))
        self.target = target
        self.last_keyboard_receiver = None
        self.reported_send = False
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.api.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.api.GetClassNameW.restype = ctypes.c_int
        self.api.IsWindowVisible.argtypes = [wintypes.HWND]
        self.api.IsWindowEnabled.argtypes = [wintypes.HWND]
        self.child_callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.api.EnumChildWindows.argtypes = [wintypes.HWND, self.child_callback_type, wintypes.LPARAM]
        self.api.IsWindow.argtypes = [wintypes.HWND]
        self.api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.api.GetAncestor.restype = wintypes.HWND
        self.api.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.c_void_p]
        self.api.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.api.PostMessageW.restype = wintypes.BOOL
        self.api.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.api.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.api.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.api.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.api.ChildWindowFromPointEx.argtypes = [wintypes.HWND, wintypes.POINT, wintypes.UINT]
        self.api.ChildWindowFromPointEx.restype = wintypes.HWND
        self.api.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        self.api.GetKeyboardLayout.restype = wintypes.HANDLE
        self.api.VkKeyScanExW.argtypes = [wintypes.WCHAR, wintypes.HANDLE]
        self.api.VkKeyScanExW.restype = ctypes.c_short
        self.api.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.HANDLE]
        self.api.MapVirtualKeyExW.restype = wintypes.UINT

    def alive(self):
        pid = wintypes.DWORD()
        self.api.GetWindowThreadProcessId(self.target.hwnd, ctypes.byref(pid))
        return bool(self.api.IsWindow(self.target.hwnd) and pid.value == self.target.pid)

    def owned(self, hwnd):
        pid = wintypes.DWORD()
        self.api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return bool(self.api.IsWindow(hwnd) and pid.value == self.target.pid and
                    self.api.GetAncestor(hwnd, 2) == self.target.hwnd)

    def keyboard_receiver(self):
        class GUIThreadInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                        *[(name, wintypes.HWND) for name in ("active", "focus", "capture", "menu", "move", "caret")],
                        ("rect", wintypes.RECT)]
        info = GUIThreadInfo()
        info.cbSize = ctypes.sizeof(info)
        thread = self.api.GetWindowThreadProcessId(self.target.hwnd, None)
        if self.api.GetGUIThreadInfo(thread, ctypes.byref(info)) and info.focus and self.owned(info.focus):
            self.last_keyboard_receiver = info.focus
            return info.focus
        if self.last_keyboard_receiver and self.owned(self.last_keyboard_receiver) and self.api.IsWindowVisible(self.last_keyboard_receiver) and self.api.IsWindowEnabled(self.last_keyboard_receiver):
            return self.last_keyboard_receiver


        editors = []
        def inspect(hwnd, unused):
            name = self.class_name(hwnd).lower()
            if self.owned(hwnd) and self.api.IsWindowVisible(hwnd) and self.api.IsWindowEnabled(hwnd) and (name == 'edit' or name.startswith('richedit')):
                editors.append(hwnd)
            return True
        callback = self.child_callback_type(inspect)
        self.api.EnumChildWindows(self.target.hwnd, callback, 0)
        if len(editors) > 1:
            raise ValidationError(tr('The target has several text controls. Focus the editor you want to use before starting the macro.'))
        receiver = editors[0] if editors else self.target.hwnd
        self.last_keyboard_receiver = receiver if editors else None
        LOG.info("background_receiver root=%s receiver=%s class=%s discovered_editors=%s", self.target.hwnd, receiver, self.class_name(receiver), len(editors))
        return receiver

    def class_name(self, hwnd):
        buffer = ctypes.create_unicode_buffer(256)
        self.api.GetClassNameW(hwnd, buffer, len(buffer))
        return buffer.value

    def resolve_key(self, token):
        if token.startswith("char:"):
            if ord(token[5:]) > 65535:
                raise ValidationError(tr('This character cannot be sent as a background key press.'))
            thread = self.api.GetWindowThreadProcessId(self.target.hwnd, None)
            code = self.api.VkKeyScanExW(token[5:], self.api.GetKeyboardLayout(thread))
            if code == -1 or code >> 8:
                raise ValidationError(tr('This character needs modifiers or is not on the target keyboard. Record the physical keys or use focused mode.'))
            return code & 255
        from .recording import token_vk
        code = token_vk(token)
        if not code:
            raise ValidationError(tr('This key is not supported by background messages.'))
        return code

    def post(self, hwnd, message, wp, lp):
        if not self.alive() or not self.owned(hwnd):
            raise ValidationError(tr('The target window closed or changed. Select it again.'))
        ctypes.set_last_error(0)
        if not self.api.PostMessageW(hwnd, message, wp, lp):
            error = ctypes.get_last_error()
            detail = tr('Insufficient permissions (UIPI).') if error == 5 else tr('Windows error {0}.', error)
            LOG.warning("background_send_failed root=%s receiver=%s message=%s winerror=%s", self.target.hwnd, hwnd, message, error)
            raise ValidationError(tr('Could not send message 0x{0:04X} to target HWND {1}. {2}', message, hwnd, detail))
        if not self.reported_send:
            LOG.info("background_message_accepted root=%s receiver=%s class=%s processing_unverified=True", self.target.hwnd, hwnd, self.class_name(hwnd))
            self.reported_send = True

    def key(self, hwnd, vk, down, repeated=False, alt=False):
        thread = self.api.GetWindowThreadProcessId(hwnd, None)
        scan = self.api.MapVirtualKeyExW(vk, 4, self.api.GetKeyboardLayout(thread))
        extended = (scan >> 8) in (0xE0, 0xE1) or vk in (33, 34, 35, 36, 37, 38, 39, 40, 45, 46, 163, 165)
        lp = 1 | ((scan & 255) << 16) | (int(extended) << 24) | (int(alt) << 29)
        if repeated or not down:
            lp |= 1 << 30
        if not down:
            lp |= 1 << 31
        message = (0x104 if down else 0x105) if alt or vk in (18, 164, 165) else (0x100 if down else 0x101)
        self.post(hwnd, message, {160: 16, 161: 16, 162: 17, 163: 17, 164: 18, 165: 18}.get(vk, vk), lp)

    def mouse_receiver(self, x, y):
        rect = wintypes.RECT()
        if not self.api.GetWindowRect(self.target.hwnd, ctypes.byref(rect)) or not (rect.left <= x < rect.right and rect.top <= y < rect.bottom):
            raise ValidationError(tr('A coordinate falls outside the selected window. Check its position and the macro.'))
        hwnd = self.target.hwnd
        for _ in range(16):
            point = wintypes.POINT(x, y)
            if not self.api.ScreenToClient(hwnd, ctypes.byref(point)):
                raise ValidationError(tr('Could not convert the coordinate to the target window.'))
            child = self.api.ChildWindowFromPointEx(hwnd, point, 7)
            if not child or child == hwnd or not self.owned(child):
                return hwnd
            hwnd = child
        return hwnd

    def position(self):
        rect = wintypes.RECT()
        point = wintypes.POINT()
        if not self.api.GetClientRect(self.target.hwnd, ctypes.byref(rect)):
            raise ValidationError(tr('The selected window is no longer available.'))
        point.x, point.y = rect.right // 2, rect.bottom // 2
        if not self.api.ClientToScreen(self.target.hwnd, ctypes.byref(point)):
            raise ValidationError(tr('Could not get the center of the target.'))
        return point.x, point.y

    def mouse(self, hwnd, event, flags):
        point = wintypes.POINT(event.x, event.y)
        if event.kind == "scroll":
            lp = (point.x & 65535) | ((point.y & 65535) << 16)
            for delta, message in ((event.dy, 0x20A), (event.dx, 0x20E)):
                if delta:
                    self.post(hwnd, message, flags | (((delta * 120) & 65535) << 16), lp)
            return
        if not self.api.ScreenToClient(hwnd, ctypes.byref(point)):
            raise ValidationError(tr('Could not convert the coordinate to the target window.'))
        lp = (point.x & 65535) | ((point.y & 65535) << 16)
        if event.kind == "move":
            message, wp = 0x200, flags
        else:
            base = {"left": 0x201, "right": 0x204, "middle": 0x207, "x1": 0x20B, "x2": 0x20B}[event.button]
            message = base + int(event.kind == "mouse_up")
            wp = flags | ((1 if event.button == "x1" else 2) << 16 if event.button in ("x1", "x2") else 0)
        self.post(hwnd, message, wp, lp)


class WindowMessageDriver:

    def __init__(self, target, transport=None):
        self.transport = transport or NativeWindowMessages(target)
        self.held_keys, self.held_buttons = {}, {}
        self.last_position = None

    def check_target(self):
        if not self.transport.alive():
            raise ValidationError(tr('The selected window closed. The macro was stopped.'))

    def position(self):
        return self.last_position or self.transport.position()

    def flags(self):
        result = sum({"left": 1, "right": 2, "middle": 16, "x1": 32, "x2": 64}[button] for button in self.held_buttons)
        codes = [value[1] for value in self.held_keys.values()]
        return result | (4 if any(v in (16, 160, 161) for v in codes) else 0) | (8 if any(v in (17, 162, 163) for v in codes) else 0)

    def dispatch(self, event):
        self.check_target()
        if event.kind == "wait":
            return
        if event.kind.startswith("key_"):
            down = event.kind == "key_down"
            previous = self.held_keys.get(event.key)
            if not down and previous is None:
                return
            hwnd, vk = previous or (self.transport.keyboard_receiver(), self.transport.resolve_key(event.key))
            alt = any(value[1] in (18, 164, 165) for value in self.held_keys.values())
            self.transport.key(hwnd, vk, down, previous is not None, alt)
            if down:
                self.held_keys[event.key] = hwnd, vk
            else:
                self.held_keys.pop(event.key, None)
            return
        x, y = (event.x, event.y) if event.x is not None else self.position()
        self.last_position = x, y
        receiver = self.transport.mouse_receiver(x, y)
        if event.kind == "mouse_down":
            self.held_buttons[event.button] = receiver, event
        elif event.kind == "mouse_up":
            previous = self.held_buttons.pop(event.button, None)
            if previous is None:
                return
            receiver = previous[0]
        elif self.held_buttons:
            receiver = next(iter(self.held_buttons.values()))[0]
        if event.x is None:
            from dataclasses import replace
            event = replace(event, x=x, y=y)
        self.transport.mouse(receiver, event, self.flags())

    def release_all(self):
        if not self.transport.alive():
            self.held_keys.clear()
            self.held_buttons.clear()
            return
        errors = []
        for key in reversed(list(self.held_keys)):
            try:
                self.dispatch(Event("key_up", key=key))
            except Exception as error:
                errors.append(error)
        for button, (hwnd, original) in list(self.held_buttons.items()):
            try:
                self.held_buttons.pop(button)
                x, y = self.last_position or (original.x, original.y)
                self.transport.mouse(hwnd, Event("mouse_up", button=button, x=x, y=y), self.flags())
            except Exception as error:
                errors.append(error)
        if errors:
            raise ValidationError(tr('Windows did not confirm all input release messages for the target.'))

    def suspend(self):
        state = list(self.held_keys), [item[1] for item in self.held_buttons.values()]
        self.release_all()
        return state

    def restore(self, state):
        for key in state[0]:
            self.dispatch(Event("key_down", key=key))
        for event in state[1]:
            self.dispatch(event)
