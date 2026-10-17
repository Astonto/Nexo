from __future__ import annotations
from .i18n import tr

import ctypes
import os
import threading
from dataclasses import dataclass

from .models import ValidationError

MOD_VKS = {0x10: "Shift", 0xA0: "Shift", 0xA1: "Shift", 0x11: "Ctrl", 0xA2: "Ctrl", 0xA3: "Ctrl",
           0x12: "Alt", 0xA4: "Alt", 0xA5: "Alt", 0x5B: "Win", 0x5C: "Win"}
NAMED = {"pause": 0x13, "space": 0x20, "tab": 0x09, "enter": 0x0D, "esc": 0x1B,
         "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
         "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28}
NAMED.update({f"f{i}": 0x70 + i - 1 for i in range(1, 25)})
NAMED.update({"capslock": 0x14, "printscreen": 0x2C, "backspace": 0x08,
              "numlock": 0x90, "scrolllock": 0x91})
MOD_ORDER = ("Ctrl", "Alt", "Shift", "Win")


@dataclass(frozen=True)
class Binding:
    modifiers: frozenset[str]
    key: int | str

    @property
    def label(self):
        prefix = [m for m in MOD_ORDER if m in self.modifiers]
        if isinstance(self.key, str):
            last = self.key.upper()
        elif 0x30 <= self.key <= 0x39 or 0x41 <= self.key <= 0x5A:
            last = chr(self.key)
        else:
            last = next((name.capitalize() for name, vk in NAMED.items() if vk == self.key), f"VK{self.key}")
        return "+".join(prefix + [last])


def keyboard_layout():
    if os.name != 'nt':
        return 0
    get_layout = ctypes.windll.user32.GetKeyboardLayout
    get_layout.argtypes = [ctypes.c_uint]
    get_layout.restype = ctypes.c_void_p
    return get_layout(0) or 0


def layout_character(key, layout):
    mapper = ctypes.windll.user32.MapVirtualKeyExW
    mapper.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
    mapper.restype = ctypes.c_uint
    value = mapper(key, 2, layout) & 0xffff
    return chr(value).upper() if value >= 32 and value != 127 else ''


def key_label(key):
    mouse_names = {'mbutton': tr('Middle mouse button'), 'mouseleft': tr('Left mouse button'), 'mouseright': tr('Right mouse button')}
    if key in mouse_names:
        return mouse_names[key]
    if key in MOD_VKS:
        return MOD_VKS[key]
    labels = {0x1B: "Esc", 0x2E: tr('Del'), 0x2D: "Insert", 0x2C: tr('Print Screen'), 0x14: tr('Caps Lock')}
    if key in labels:
        return labels[key]
    if isinstance(key, int) and (0xBA <= key <= 0xE2 or 0x60 <= key <= 0x6F) and os.name == "nt":
        character = layout_character(key, keyboard_layout())
        if character:
            return character
        scan = ctypes.windll.user32.MapVirtualKeyW(key, 0)
        buffer = ctypes.create_unicode_buffer(80)
        if ctypes.windll.user32.GetKeyNameTextW(scan << 16, buffer, 80):
            return buffer.value
    return Binding(frozenset(), key).label


def excluded_key_codes(entries):
    codes = {entry["key"] for entry in entries if entry["enabled"]}
    for generic, variants in ((17, {162, 163}), (16, {160, 161}), (18, {164, 165})):
        if generic in codes:
            codes.update(variants)
    return codes


def display_binding(text):
    if not text:
        return ""
    binding = parse_binding(text, allow_reserved=True)
    return " + ".join([m for m in MOD_ORDER if m in binding.modifiers] + [key_label(binding.key)])


def parse_binding(text, *, allow_reserved=False):
    if not isinstance(text, str) or len(text) > 80:
        raise ValidationError(tr('Invalid shortcut.'))


    parts = [p.strip().lower() for p in text.split("+")]
    if text.endswith("+"):
        parts = [p.strip().lower() for p in text[:-1].rstrip("+").split("+") if p.strip()] + ["+"]
    mods = []
    for p in parts[:-1]:
        if p.capitalize() not in MOD_ORDER or p.capitalize() in mods:
            raise ValidationError(tr('Invalid shortcut. Examples: A, F6, Ctrl+G or X1.'))
        mods.append(p.capitalize())
    last = parts[-1]
    if last in ("x1", "x2", "mbutton", "mouseleft", "mouseright"):
        key = last
    elif len(last) == 1 and last.isascii() and last.isalnum():
        key = ord(last.upper())
    elif last in NAMED:
        key = NAMED[last]
    elif last.startswith("vk") and last[2:].isdigit() and 1 <= int(last[2:]) <= 254:
        key = int(last[2:])
        if key in MOD_VKS:
            raise ValidationError(tr('Add a key to the modifier.'))
    elif len(last) == 1 and ord(last) >= 32 and os.name == "nt":
        scan_key = ctypes.windll.user32.VkKeyScanW
        scan_key.argtypes = [ctypes.c_wchar]
        scan_key.restype = ctypes.c_short
        code = scan_key(last)
        if code == -1:
            raise ValidationError(tr('Press Assign and use the physical key on your keyboard.'))
        key = code & 255
        for bit, modifier in ((1, "Shift"), (2, "Ctrl"), (4, "Alt")):
            if (code >> 8) & bit and modifier not in mods:
                mods.append(modifier)
    else:
        raise ValidationError(tr('Use A–Z, 0–9, F1–F24, Pause, a navigation key, X1 or X2.'))
    binding = Binding(frozenset(mods), key)
    if not allow_reserved and (key == 0x7B or ("Win" in mods) or (key == 0x2E and {"Ctrl", "Alt"}.issubset(mods)) or (key == 0x09 and "Alt" in mods)):
        raise ValidationError(tr('That shortcut is reserved by Windows. Choose another trigger.'))
    return binding


def validate_bindings(macros, controls):
    seen = {parse_binding(value): tr('global control') for value in controls.values()}
    for macro in macros:
        if not macro.trigger:
            continue
        binding = parse_binding(macro.trigger)
        if binding in seen:
            raise ValidationError(tr('Shortcut {0} conflicts with {1}.', binding.label, seen[binding]))
        seen[binding] = tr('another macro ({0})', macro.name)


def check_os_binding(text):

    binding = parse_binding(text)
    if os.name != "nt" or isinstance(binding.key, str):
        return
    from .hotkeys import MODIFIERS
    mods = sum(MODIFIERS[m.lower()] for m in binding.modifiers)
    if not ctypes.windll.user32.RegisterHotKey(None, 0x6F00, mods | 0x4000, binding.key):
        raise ValidationError(tr('{0} is registered by Windows or another application.', binding.label))
    ctypes.windll.user32.UnregisterHotKey(None, 0x6F00)


class InputRouter:






    def __init__(self, callback, macro_allowed=lambda: True):
        self.callback = callback
        self.macro_allowed = macro_allowed
        self.lock = threading.RLock()
        self.controls = {}
        self.native_macros = set()
        self.macros = {}
        self.down = set()
        self.active = {}
        self.consumed = set()
        self.capture = None
        self.capture_all_mouse = False
        self.capture_mouse_guard = None
        self.suspended = False
        self.hold_active = None
        self.hold_binding = None
        self.ignored_hold_modifiers = frozenset()
        self.keyboard = self.mouse = None

    def set_suspended(self, suspended):
        with self.lock:
            self.suspended = bool(suspended)
            self.active.clear()
            self.down.clear()
            self.consumed.clear()
            self.capture = None
            self.capture_all_mouse = False
            self.hold_active = None
            self.hold_binding = None

    def configure(self, macros, controls, *, ignored_hold_modifiers=()):
        validate_bindings(macros, controls)
        with self.lock:
            self.ignored_hold_modifiers = frozenset(ignored_hold_modifiers)
            self.controls = {parse_binding(text): action for action, text in controls.items()}
            self.macros = {parse_binding(m.trigger): (m.id, m.activation) for m in macros if m.enabled and m.trigger}
            self.active.clear()
            self.down.clear()
            self.consumed.clear()
            self.hold_active = None
            self.hold_binding = None

    def process(self, key, pressed, injected=False):
        if injected:
            return False
        with self.lock:
            if self.suspended:
                return False
            if not pressed:
                self.down.discard(key)
                held_modifiers = {MOD_VKS[k] for k in self.down if k in MOD_VKS}
                if self.hold_active is not None and (key == self.hold_active or not self.hold_binding.modifiers.issubset(held_modifiers)):
                    self.hold_active = None
                    self.hold_binding = None
                    self.callback('keyboard_repeat_release', '')
                for active_key, (identifier, mode, binding) in list(self.active.items()):
                    modifiers = {MOD_VKS[k] for k in self.down if k in MOD_VKS}
                    if key == active_key or not binding.modifiers.issubset(modifiers):
                        if mode == "hold":
                            self.callback("macro_release", identifier)
                        self.active.pop(active_key, None)
                if key in self.consumed:
                    self.consumed.discard(key)
                    return True
                return False
            if key in self.down:
                return key in self.consumed
            self.down.add(key)
            if key in MOD_VKS:
                return False
            modifiers = frozenset(MOD_VKS[k] for k in self.down if k in MOD_VKS)
            binding = Binding(modifiers, key)
            action = self.controls.get(binding)
            if action == "emergency":
                self.callback("emergency", "")
                self.consumed.add(key)
                return True
            if self.capture:
                if key in ('mouseleft', 'mouseright') and (not self.capture_all_mouse or (self.capture_mouse_guard and not self.capture_mouse_guard())):
                    return False
                capture = self.capture
                self.capture = None
                capture(binding.label)
                self.consumed.add(key)
                return True
            hold_binding = None
            if not action and binding not in self.macros:
                for candidate, candidate_action in self.controls.items():
                    if candidate_action == 'keyboard_repeat_press' and candidate.key == key and candidate.modifiers.issubset(modifiers) and (modifiers - candidate.modifiers).issubset(self.ignored_hold_modifiers):
                        action = candidate_action
                        hold_binding = candidate
                        break
            if action:
                if action == 'keyboard_repeat_press':
                    if not self.macro_allowed():
                        return False
                    self.hold_active = key
                    self.hold_binding = hold_binding or binding
                self.callback(action, "")
                self.consumed.add(key)
                return True
            macro = self.macros.get(binding)
            if macro and self.macro_allowed():
                identifier, mode = macro
                self.active[key] = (identifier, mode, binding)
                self.consumed.add(key)
                if identifier in self.native_macros:


                    return False
                self.callback("macro_press", identifier)
                return True
            return False

    def physical_modifiers(self):
        with self.lock:
            return frozenset(key for key in self.down if key in MOD_VKS)

    def start(self):
        from pynput import keyboard, mouse

        def keyboard_filter(message, data):
            if data.flags & 0x12:
                return False
            pressed = message in (0x100, 0x104)
            if self.process(int(data.vkCode), pressed):
                self.keyboard.suppress_event()
            return False

        def mouse_filter(message, data):
            if data.flags & 3:
                return False
            fixed_buttons = {0x201: 'mouseleft', 0x202: 'mouseleft', 0x204: 'mouseright', 0x205: 'mouseright', 0x207: 'mbutton', 0x208: 'mbutton'}
            if message in (0x20B, 0x20C) or message in fixed_buttons:
                key = fixed_buttons.get(message) or ('x1' if data.mouseData >> 16 == 1 else 'x2')
                if self.process(key, message in (0x20B, 0x207, 0x201, 0x204)):
                    self.mouse.suppress_event()
            return False

        self.keyboard = keyboard.Listener(win32_event_filter=keyboard_filter)
        self.mouse = mouse.Listener(win32_event_filter=mouse_filter)
        self.keyboard.start()
        self.mouse.start()
        self.keyboard.wait()
        self.mouse.wait()

    def stop(self):
        for listener in (self.keyboard, self.mouse):
            if listener:
                listener.stop()
        for listener in (self.keyboard, self.mouse):
            if listener and listener is not threading.current_thread():
                listener.join(2)
        self.keyboard = self.mouse = None
