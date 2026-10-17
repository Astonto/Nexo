from __future__ import annotations
from .i18n import tr

import os
import queue
import threading
import time
from dataclasses import replace

from .models import Event, MAX_EVENTS
from .windows import PrivacyProbe, foreground_process
from .triggers import Binding, MOD_VKS, parse_binding


def key_token(key):
    from pynput import keyboard
    if isinstance(key, keyboard.Key):
        return "key:" + key.name
    if getattr(key, "vk", None) is not None:
        return "vk:" + str(key.vk)
    if getattr(key, "char", None) and ord(key.char) >= 32:
        return "char:" + key.char
    return None


def token_vk(token):
    if token.startswith("vk:"):
        return int(token[3:])
    if token.startswith("key:"):
        from pynput import keyboard
        value = getattr(keyboard.Key, token[4:], None)
        return getattr(getattr(value, "value", None), "vk", None)
    return None


def modifier_token(token):
    return token.startswith(("key:ctrl", "key:alt", "key:shift", "key:cmd")) or token_vk(token) in (16, 17, 18, 160, 161, 162, 163, 164, 165, 91, 92)


class Recorder:
    def __init__(self, capture_moves=False, reserved=None, notify=lambda *args: None, privacy_factory=PrivacyProbe,
                 *, controls=None, mode="timed", fixed_interval=1.0, physical_modifiers=None, input_target=None):
        self.input_target = input_target
        self.capture_moves = capture_moves
        self.reserved = reserved or set()
        self.controls = {parse_binding(value) for value in (controls or {}).values()}
        self.mode, self.fixed_interval = mode, fixed_interval
        self.physical_keys = {}
        self.physical_modifiers = physical_modifiers
        self.ignored_keys = set()
        self.notify = notify
        self.privacy_factory = privacy_factory
        self.lock = threading.RLock()
        self.events = []
        self.fixed_starts = []
        self.undo_capture = None
        self.pending_modifiers = []
        self.held_keys = set()
        self.held_buttons = {}
        self.paused = False
        self.started = self.last_time = time.monotonic()
        self.pause_time = 0.0
        self.pause_start = None
        self.last_move_time = 0.0
        self.last_move = None
        self.epoch = 0
        self.queue = queue.Queue(maxsize=8192)
        self.stopped = threading.Event()
        self.ready = threading.Event()
        self.keyboard = self.mouse = self.worker = None
        self.error = None
        self.privacy_reason = ""

    @property
    def duration(self):
        with self.lock:
            return (self.pause_start or time.monotonic()) - self.started - self.pause_time

    def snapshot(self):
        with self.lock:
            return list(self.events)

    def feed(self, event, injected=False):

        own = foreground_process() == os.getpid()
        if injected or self.stopped.is_set() or self.paused:
            return
        if self.input_target and not self.input_target.allows(event):
            with self.lock:
                self.epoch += 1
                self._close_inputs(time.monotonic())
                self.physical_keys.clear()
            return
        if own and not (self.mode == "fixed" and event.kind.startswith("key_")):
            return
        if self.mode == "fixed" and not event.kind.startswith("key_"):
            return
        if event.kind == "move":
            now = time.monotonic()
            if not self.capture_moves or now - self.last_move_time < 0.02:
                return
            if self.last_move and abs(event.x - self.last_move[0]) + abs(event.y - self.last_move[1]) < 3:
                return
            self.last_move_time, self.last_move = now, (event.x, event.y)
        try:
            modifiers = self.physical_modifiers() if self.physical_modifiers and event.kind.startswith("key_") else None
            self.queue.put_nowait((event, time.monotonic(), self.epoch, own, modifiers))
        except queue.Full:
            self.error = tr('The capture buffer overflowed. Recording stopped to avoid an incomplete sequence.')
            self.stopped.set()

    def start(self):
        from pynput import keyboard, mouse
        self.worker = threading.Thread(target=self._consume, name="Nexo-recorder", daemon=True)
        self.worker.start()
        if not self.ready.wait(10):
            self.stop()
            raise RuntimeError(tr('Could not start recording protection.'))

        def key_event(key, pressed, injected=False):
            token = key_token(key)
            if token:
                self.feed(Event("key_down" if pressed else "key_up", key=token), injected)

        self.keyboard = keyboard.Listener(on_press=lambda k, injected=False: key_event(k, True, injected),
                                          on_release=lambda k, injected=False: key_event(k, False, injected))
        self.mouse = mouse.Listener(on_move=lambda x, y, injected=False: self.feed(Event("move", x=x, y=y), injected),
                                    on_click=lambda x, y, b, p, injected=False: self.feed(Event("mouse_down" if p else "mouse_up", button=b.name, x=x, y=y), injected),
                                    on_scroll=lambda x, y, dx, dy, injected=False: self.feed(Event("scroll", x=x, y=y, dx=dx, dy=dy), injected))
        self.started = self.last_time = time.monotonic()
        self.keyboard.start()
        self.mouse.start()
        self.keyboard.wait()
        self.mouse.wait()

    def _append(self, event, stamp):
        if len(self.events) >= MAX_EVENTS - 64:
            self.error = tr('The 100,000-event limit was reached; the recording will be saved.')
            self.stopped.set()
            return
        self.events.append(replace(event, delay=max(0, stamp - self.last_time)).validate())
        self.last_time = max(stamp, self.last_time)
        if event.kind == "key_down":
            self.held_keys.add(event.key)
        elif event.kind == "key_up":
            self.held_keys.discard(event.key)
        elif event.kind == "mouse_down":
            self.held_buttons[event.button] = (event.x, event.y)
        elif event.kind == "mouse_up":
            self.held_buttons.pop(event.button, None)

    def _consume(self):
        probe = None
        try:
            probe = self.privacy_factory()
            self.ready.set()
            while not self.stopped.is_set() or not self.queue.empty():
                try:
                    event, stamp, epoch, own, *physical = self.queue.get(timeout=0.1)
                except queue.Empty:
                    continue


                allowed = (own and self.mode == "fixed") or (probe.allowed() if event.kind.startswith("key_") else True)
                with self.lock:
                    if self.paused or epoch != self.epoch:
                        continue
                    if event.kind.startswith("key_"):
                        vk = token_vk(event.key)
                        if event.kind == "key_down":
                            self.physical_keys[event.key] = vk
                        else:
                            self.physical_keys.pop(event.key, None)


                        if physical and physical[0] is not None:
                            actual = set(physical[0])
                            if vk in MOD_VKS:
                                actual.add(vk) if event.kind == "key_down" else actual.discard(vk)
                            self.physical_keys = {key: value for key, value in self.physical_keys.items()
                                                  if value not in MOD_VKS or value in actual}
                            for value in actual:
                                if value not in self.physical_keys.values():
                                    self.physical_keys[f"vk:{value}"] = value
                        mods = frozenset(MOD_VKS[v] for v in self.physical_keys.values() if v in MOD_VKS)
                        control = Binding(mods, vk) in self.controls
                        if control or vk in self.reserved or event.key in self.ignored_keys:
                            if event.kind == "key_down":
                                self.ignored_keys.add(event.key)
                            else:
                                self.ignored_keys.discard(event.key)
                            self.pending_modifiers.clear()
                            if control:
                                self._close_keys(stamp)
                            continue
                        if not allowed:
                            self.privacy_reason = probe.reason
                            self.pending_modifiers.clear()

                            self._close_keys(stamp)
                            continue
                        self.privacy_reason = ""
                        if self.mode == "fixed":
                            if event.kind == "key_down" and not modifier_token(event.key):
                                self._fixed_press(event)
                            continue
                        if event.kind == "key_down" and modifier_token(event.key):
                            self.pending_modifiers.append((event, stamp))
                            continue
                        if event.kind == "key_down":
                            pending_keys = {item.key for item, _ in self.pending_modifiers}
                            for key, value in self.physical_keys.items():
                                if value in MOD_VKS and value not in self.reserved and key not in self.held_keys and key not in pending_keys:
                                    self.pending_modifiers.append((Event("key_down", key=key), stamp))
                    if event.kind != "move":
                        for pending, timestamp in self.pending_modifiers:
                            self._append(pending, timestamp)
                        self.pending_modifiers.clear()
                    if event.kind == "key_up" and event.key not in self.held_keys:
                        continue
                    if event.kind == "mouse_up" and event.button not in self.held_buttons:
                        continue
                    self._append(event, stamp)
        except Exception:
            self.error = tr('Capture was interrupted. Check the device and Windows permissions.')
            self.stopped.set()
        finally:
            self.ready.set()
            if probe:
                probe.close()

    def _close_keys(self, stamp):
        for key in list(self.held_keys):
            self._append(Event("key_up", key=key), stamp)

    def _fixed_press(self, event):
        self.undo_capture = None
        self.fixed_starts.append(len(self.events))
        modifiers = [token for token, vk in self.physical_keys.items()
                     if vk in MOD_VKS and vk not in self.reserved]
        presses = [Event("key_down", key=token) for token in modifiers] + [event]
        releases = [Event("key_up", key=event.key)] + [Event("key_up", key=token) for token in reversed(modifiers)]
        stamp = self.last_time + (self.fixed_interval if self.events else 0)
        for item in presses + releases:
            self._append(item, stamp)

    @property
    def can_undo_reset(self):
        return self.undo_capture is not None and not self.events

    def reset_capture(self, undo=False):
        with self.lock:
            if self.mode != "fixed" or self.stopped.is_set():
                return False
            self.epoch += 1
            if undo:
                if not self.can_undo_reset:
                    return False
                self.events, self.fixed_starts = self.undo_capture
                self.undo_capture = None
                self.set_fixed_interval(self.fixed_interval)
            else:
                self.undo_capture = (list(self.events), list(self.fixed_starts)) if self.events else None
                self.events.clear()
                self.fixed_starts.clear()
                self.last_time = time.monotonic()
            return True

    def set_fixed_interval(self, interval):
        from .models import number
        number(interval, tr('Keystroke interval'), 0.01, 86400)
        with self.lock:
            self.fixed_interval = interval
            for position, index in enumerate(self.fixed_starts):
                if index < len(self.events):
                    self.events[index] = replace(self.events[index], delay=interval if position else 0)
            self.last_time = self.started + sum(event.delay for event in self.events)

    def _close_inputs(self, stamp):
        self.pending_modifiers.clear()
        self._close_keys(stamp)
        for button, (x, y) in list(self.held_buttons.items()):
            self._append(Event("mouse_up", button=button, x=x, y=y), stamp)

    def pause(self, paused=True):
        with self.lock:
            if self.paused == paused:
                return
            self.epoch += 1
            self.physical_keys.clear()
            self.ignored_keys.clear()
            now = time.monotonic()
            if paused:
                self._close_inputs(now)
                self.pause_start = now
            else:
                pause_length = now - self.pause_start
                self.pause_time += pause_length
                self.last_time += pause_length
                self.pause_start = None
            self.paused = paused

    def stop(self):
        for listener in (self.keyboard, self.mouse):
            if listener:
                listener.stop()
        self.stopped.set()
        for listener in (self.keyboard, self.mouse):
            if listener and listener is not threading.current_thread():
                listener.join(2)
        if self.worker and self.worker is not threading.current_thread():
            self.worker.join(3)
        with self.lock:
            self._close_inputs(self.pause_start or time.monotonic())


class PositionPicker:
    def __init__(self, callback):
        self.callback, self.listener = callback, None

    def start(self):
        from pynput import mouse
        def click_filter(message, data):
            if data.flags & 3:
                return False
            if message == 0x201:
                self.callback(int(data.pt.x), int(data.pt.y))
                self.listener.suppress_event()
            if message == 0x202:
                self.listener.stop()
                self.listener.suppress_event()
            return False
        self.listener = mouse.Listener(win32_event_filter=click_filter)
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener.join(2)
            self.listener = None
