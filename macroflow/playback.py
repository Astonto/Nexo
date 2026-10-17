from __future__ import annotations

import random
import threading
import time

from .models import ClickOptions, Event, ValidationError, integer, number, scaled_delay


class Cancelled(Exception):
    pass


class SeekRequested(Exception):
    pass


class RunControl:
    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.cancelled = False
        self.paused = False
        self.started = time.monotonic()
        self.pause_started = None
        self.pause_total = 0.0
        self.current_index = 0
        self.event_count = 0
        self.pending_seek = None
        self.target_guard = None

    @property
    def elapsed(self):
        with self.condition:
            return (self.pause_started or time.monotonic()) - self.started - self.pause_total

    def reset_clock(self):
        with self.condition:
            self.started = time.monotonic()
            self.pause_total = 0.0
            self.pause_started = self.started if self.paused else None

    def cancel(self):
        with self.condition:
            self.cancelled = True
            self.condition.notify_all()

    def seek(self, delta=0, restart=False):
        with self.condition:
            if self.cancelled or self.event_count == 0:
                return
            base = self.pending_seek[0] if self.pending_seek else self.current_index
            target = 0 if restart else max(0, min(self.event_count - 1, base + delta))
            self.pending_seek = target, restart
            self.condition.notify_all()

    def take_seek(self):
        with self.condition:
            command = self.pending_seek
            self.pending_seek = None
            return command

    def pause(self, value=True):
        with self.condition:
            if value and not self.paused:
                self.pause_started = time.monotonic()
            elif not value and self.paused:
                self.pause_total += time.monotonic() - self.pause_started
                self.pause_started = None
            self.paused = value
            self.condition.notify_all()

    def wait(self, seconds=0, on_pause=None, on_resume=None):
        remaining = seconds
        observed_pause = False
        with self.condition:
            while True:
                if self.cancelled:
                    raise Cancelled()
                if self.pending_seek is not None:
                    raise SeekRequested()
                if self.target_guard and not self.paused:
                    self.target_guard()
                if self.paused:
                    if not observed_pause and on_pause:
                        on_pause()
                    observed_pause = True
                    self.condition.wait()
                    continue
                if observed_pause:
                    if on_resume:
                        on_resume()
                    observed_pause = False
                if remaining <= 0:
                    return
                start = time.monotonic()
                self.condition.wait(min(remaining, .05) if self.target_guard else remaining)

                end = self.pause_started if self.paused and self.pause_started else time.monotonic()
                remaining -= max(0, end - start)


class PynputDriver:
    def __init__(self):
        from pynput import keyboard, mouse
        self.keyboard_module, self.mouse_module = keyboard, mouse
        self.keyboard, self.mouse = keyboard.Controller(), mouse.Controller()
        self.held_keys, self.held_buttons = {}, {}

    def resolve_key(self, value):
        if value.startswith("key:"):
            return getattr(self.keyboard_module.Key, value[4:])
        if value.startswith("vk:"):
            return self.keyboard_module.KeyCode.from_vk(int(value[3:]))
        return self.keyboard_module.KeyCode.from_char(value[5:])

    def dispatch(self, event):
        from .windows import point_on_screen, target_allowed
        if not target_allowed():
            raise ValidationError("El destino tiene permisos superiores o no permite acceso. Nexo se detuvo sin eludir restricciones de Windows.")
        if event.x is not None:
            if not point_on_screen(event.x, event.y):
                raise ValidationError("Una coordenada está fuera de los monitores actuales. Revisa el editor.")
            self.mouse.position = (event.x, event.y)
        if event.kind == "key_down":
            self.held_keys[event.key] = None
            self.keyboard.press(self.resolve_key(event.key))
        elif event.kind == "key_up":
            if event.key in self.held_keys:
                self.keyboard.release(self.resolve_key(event.key))
                self.held_keys.pop(event.key, None)
        elif event.kind == "mouse_down":
            self.held_buttons[event.button] = None
            self.mouse.press(getattr(self.mouse_module.Button, event.button))
        elif event.kind == "mouse_up":
            if event.button in self.held_buttons:
                self.mouse.release(getattr(self.mouse_module.Button, event.button))
                self.held_buttons.pop(event.button, None)
        elif event.kind == "scroll":
            self.mouse.scroll(event.dx, event.dy)

    def release_all(self):
        errors = []
        for key in reversed(list(self.held_keys)):
            try:
                self.keyboard.release(self.resolve_key(key))
                self.held_keys.pop(key, None)
            except Exception:
                errors.append("tecla")
        for button in reversed(list(self.held_buttons)):
            try:
                self.mouse.release(getattr(self.mouse_module.Button, button))
                self.held_buttons.pop(button, None)
            except Exception:
                errors.append("botón")
        if errors:
            raise RuntimeError("Windows no confirmó la liberación de todas las entradas.")

    def suspend(self):
        state = (list(self.held_keys), list(self.held_buttons))
        self.release_all()
        return state

    def restore(self, state):
        for key in state[0]:
            self.dispatch(Event("key_down", key=key))
        for button in state[1]:
            x, y = self.mouse.position
            self.dispatch(Event("mouse_down", button=button, x=x, y=y))

    def position(self):
        return self.mouse.position


class TargetDriver:
    def __init__(self, driver, target):
        self.driver, self.target = driver, target
        self.armed = False

    def check_target(self):
        if self.armed and not self.target.allows():
            raise ValidationError("La ventana seleccionada perdió el foco. Ejecución detenida y entradas liberadas.")

    def __getattr__(self, name):
        return getattr(self.driver, name)

    def dispatch(self, event):
        if not self.target.allows(event):
            raise ValidationError("La ventana seleccionada perdió el foco, se cerró o la acción queda fuera de ella. Se detuvo la ejecución y se liberaron las entradas.")
        self.armed = True
        self.driver.dispatch(event)

    def restore(self, state):
        if not self.target.allows():
            raise ValidationError("Activa la ventana seleccionada antes de reanudar.")
        self.driver.restore(state)


def countdown(control, seconds, notify):
    deadline = control.elapsed + seconds
    while control.elapsed < deadline:
        remaining = deadline - control.elapsed
        notify("countdown", {"remaining": remaining})
        control.wait(min(0.1, remaining))
    control.wait()
    control.reset_clock()


def play_events(events, driver, control, *, speed=1.0, repetitions=1, repeat_interval=0.01, notify=lambda *args: None):
    number(speed, "Velocidad", 0.1, 10)
    integer(repetitions, "Repeticiones", 0, 10_000_000)
    number(repeat_interval, "Intervalo entre repeticiones", 0.01, 86400)
    if not events:
        raise ValidationError("La macro no contiene eventos.")
    for event in events:
        event.validate()
    total = len(events)
    control.event_count = total
    completed = 0
    index = 0
    suspended = None

    def on_pause():
        nonlocal suspended
        suspended = driver.suspend()

    def on_resume():
        nonlocal suspended
        if suspended is not None:
            driver.restore(suspended)
            suspended = None

    try:
        notify("progress", {"index": 0, "total": total, "iterations": 0, "elapsed": control.elapsed})
        while repetitions == 0 or completed < repetitions:
            try:
                while index < total:
                    with control.condition:
                        control.current_index = index
                    event = events[index]
                    control.wait(scaled_delay(event.delay, speed), on_pause, on_resume)

                    with control.condition:
                        if control.cancelled:
                            raise Cancelled()
                        if control.pending_seek is not None:
                            raise SeekRequested()
                        driver.dispatch(event)
                        index += 1
                        control.current_index = index
                    notify("progress", {"index": index, "total": total, "iterations": completed,
                                        "elapsed": control.elapsed})
                driver.release_all()
                completed += 1
                notify("progress", {"index": total, "total": total, "iterations": completed, "elapsed": control.elapsed})
                if repetitions == 0 or completed < repetitions:
                    control.wait(repeat_interval, on_pause, on_resume)
                index = 0
            except SeekRequested:
                driver.release_all()
                suspended = None
                command = control.take_seek()
                if command is None:
                    continue
                index, restart = command
                with control.condition:
                    control.current_index = index
                if restart:
                    completed = 0
                    control.reset_clock()
                notify("progress", {"index": index, "total": total, "iterations": completed,
                                    "elapsed": control.elapsed, "seek": True})
    finally:
        driver.release_all()
    return completed


def run_clicker(options: ClickOptions, driver, control, notify=lambda *args: None, rng=random.uniform):
    options.validate()
    key_events = []
    if options.key:
        from .triggers import MOD_ORDER, parse_binding
        binding = parse_binding(options.key)
        modifiers = {"Ctrl": 0xA2, "Alt": 0xA4, "Shift": 0xA0, "Win": 0x5B}
        key_events = [Event("key_down", key=f"vk:{modifiers[m]}") for m in MOD_ORDER if m in binding.modifiers]
        key_events.append(Event("key_down", key=f"vk:{binding.key}"))
    count = 0
    actions = 0
    try:
        while not options.repetitions or actions < options.repetitions:
            control.wait()
            if options.duration and control.elapsed >= options.duration:
                break
            x, y = (0, 0) if options.key else (options.position or driver.position())
            for _ in range(2 if options.double and not options.key else 1):
                if options.duration and control.elapsed >= options.duration:
                    break
                with control.condition:
                    if control.cancelled:
                        raise Cancelled()
                    for event in key_events or [Event("mouse_down", button=options.button, x=x, y=y)]:
                        driver.dispatch(event)
                try:
                    control.wait(0.005)
                finally:
                    driver.release_all()
                count += 1
                if options.double and not options.key:
                    control.wait(0.04)
            actions += 1
            notify("clicks", {"clicks": count, "actions": actions, "elapsed": control.elapsed})
            if options.repetitions and actions >= options.repetitions:
                break
            delay = rng(options.interval, options.interval_max) if options.interval_max is not None else options.interval
            if options.duration:
                delay = min(delay, max(0, options.duration - control.elapsed))
            control.wait(delay)
    finally:
        driver.release_all()
    return count
