from __future__ import annotations

import ctypes
import os
import threading
from ctypes import wintypes

from .models import ValidationError

MODIFIERS = {"ctrl": 2, "alt": 1, "shift": 4, "win": 8}
ACTIONS = {"record_start", "record_stop", "record_pause", "play", "stop", "click", "emergency"}


def parse_hotkey(text):
    from .triggers import parse_binding
    binding = parse_binding(text)
    if not isinstance(binding.key, int):
        raise ValidationError("Los controles globales requieren una tecla del teclado.")
    return sum(MODIFIERS[m.lower()] for m in binding.modifiers), binding.key


def validate_hotkeys(mapping):
    if not isinstance(mapping, dict) or set(mapping) != ACTIONS:
        raise ValidationError("Deben configurarse los siete atajos.")
    seen = set()
    for value in mapping.values():
        chord = parse_hotkey(value)
        if chord in seen:
            raise ValidationError('Dos acciones tienen el mismo atajo.')
        seen.add(chord)
    return mapping


def reserved_keys(mapping):
    return {parse_hotkey(value)[1] for value in mapping.values()}


class GlobalHotkeys:


    def __init__(self, callback):
        self.callback = callback
        self.thread = None
        self.thread_id = None
        self.error = None

    def start(self, mapping, *, extra=None):
        validate_hotkeys(mapping)
        combined = dict(mapping)
        seen = {parse_hotkey(value) for value in mapping.values()}
        for action, value in (extra or {}).items():
            chord = parse_hotkey(value)
            if not action.startswith('macro:') or chord in seen:
                raise ValidationError('El activador nativo de la macro está duplicado.')
            seen.add(chord)
            combined[action] = value
        if os.name != "nt":
            raise ValidationError("Los atajos globales de esta edición requieren Windows.")
        self.stop()
        ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, args=(combined, ready), name="Nexo-hotkeys", daemon=True)
        self.thread.start()
        if not ready.wait(5):
            self.stop()
            raise ValidationError("Windows no respondió al registrar los atajos.")
        if self.error:
            self.stop()
            raise ValidationError(self.error)

    def _run(self, mapping, ready):
        user32 = ctypes.windll.user32
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        registered = {}
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        try:
            for identifier, (action, value) in enumerate(mapping.items(), 1):
                modifiers, vk = parse_hotkey(value)
                if not user32.RegisterHotKey(None, identifier, modifiers | 0x4000, vk):
                    self.error = f"El atajo {value} está ocupado por Windows u otra aplicación. Cámbialo en Configuración."
                    return
                registered[identifier] = action
            ready.set()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and int(msg.wParam) in registered:
                    self.callback(registered[int(msg.wParam)])
        finally:
            for identifier in registered:
                user32.UnregisterHotKey(None, identifier)
            ready.set()
            self.thread_id = None

    def stop(self):
        if self.thread and self.thread.is_alive():
            if self.thread_id:
                ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
            if threading.current_thread() is not self.thread:
                self.thread.join(3)
        self.thread = None
