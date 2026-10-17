from __future__ import annotations
from .i18n import tr

import logging
import threading
import time
from collections import deque

from .models import Macro, ValidationError
from .playback import Cancelled, PynputDriver, TargetDriver, RunControl, countdown, play_events, run_clicker
from .recording import Recorder
from .windows import monitor_rects

LOG = logging.getLogger("macroflow")


class Engine:
    def __init__(self, notify=lambda *args: None, driver_factory=PynputDriver):
        self.notify = notify
        self.driver_factory = driver_factory
        self.lock = threading.RLock()
        self.control = None
        self.recorder = None
        self.thread = None
        self.task = "idle"
        self.phase = "idle"
        self.active_id = None
        self.active_mode = None
        self.queue = deque()
        self.policy = "block"
        self.last_progress = 0.0
        self.shutting_down = False
        self.enabled = True
        self.input_target = None
        self.input_delivery = "background"
        self.activation_request = None

    def make_driver(self, control):
        if self.input_target and self.input_delivery == "background":
            from .background import WindowMessageDriver
            driver = WindowMessageDriver(self.input_target)
            driver.check_target()
            self.notify("warning", {"message": tr("Target found. Background messages will be sent; the application's response has not been verified.")})
            control.target_guard = driver.check_target
            return driver
        if self.input_delivery == "activate":
            if not self.input_target:
                raise ValidationError(tr('Select a target window to use Activate window.'))
            if self.activation_request is None:
                self.input_target.activate(control)
            else:
                self.input_target.activate(control, request=self.activation_request)
        driver = self.driver_factory()
        if self.input_target:
            driver = TargetDriver(driver, self.input_target)
            if self.input_delivery == "activate":
                driver.armed = True
            control.target_guard = driver.check_target
        return driver

    @property
    def busy(self):
        with self.lock:
            return self.task != "idle"

    def _notify(self, name, data):
        if name in ("progress", "clicks"):
            now = time.monotonic()
            final = name == "progress" and (data["index"] == data["total"] or data.get("seek"))
            if now - self.last_progress < 0.04 and not final:
                return
            self.last_progress = now
        self.notify(name, data)

    def _launch(self, task, work, seconds, macro_id=None, mode=None, event_count=0):
        with self.lock:
            if not self.enabled:
                raise ValidationError(tr('Nexo is locked. Turn off the lock switch to continue.'))
            if self.busy or self.shutting_down:
                raise ValidationError(tr('Another task is running. Stop it before continuing.'))
            self.task, self.phase = task, "countdown" if seconds else "running"
            self.active_id, self.active_mode = macro_id, mode
            self.control = control = RunControl()
            control.event_count = event_count

            def run():
                error = None
                result = None
                try:
                    if seconds:
                        countdown(control, seconds, self._notify)
                    control.wait()
                    with self.lock:
                        self.phase = "running"
                    self.notify("state", {"task": task, "phase": "running"})
                    result = work(control)
                except Cancelled:
                    pass
                except Exception as exc:

                    LOG.error("automation_failure type=%s task=%s", type(exc).__name__, task)
                    error = str(exc) if isinstance(exc, ValidationError) else tr('A device error interrupted the task. Check permissions and try again.')
                finally:
                    with self.lock:
                        self.task, self.phase = "idle", "idle"
                        self.active_id = self.active_mode = None
                        self.recorder = None
                    self.notify("finished", {"task": task, "result": result, "error": error})


            self.thread = threading.Thread(target=run, name=f"Nexo-{task}", daemon=True)
            self.notify("state", {"task": task, "phase": self.phase})
            self.thread.start()

    def record(self, *, seconds=3, capture_moves=False, reserved=None, controls=None, mode="timed", fixed_interval=1.0, physical_modifiers=None):
        def work(control):
            recorder = Recorder(capture_moves, reserved, controls=controls, mode=mode, fixed_interval=fixed_interval,
                                physical_modifiers=physical_modifiers, input_target=self.input_target)
            self.recorder = recorder
            try:
                recorder.start()
                while not control.cancelled and not recorder.stopped.is_set():
                    with control.condition:
                        control.condition.wait(0.05)
                if recorder.error:
                    self.notify("warning", {"message": recorder.error})
            finally:
                recorder.stop()
            return {"events": recorder.snapshot(), "display_signature": monitor_rects()}
        self._launch("record", work, seconds)

    def play(self, macro, *, seconds=3, speed=None, repetitions=None, selected=None, activation=None):
        snapshot = Macro.from_dict(macro.to_dict())
        events = list(selected) if selected is not None else snapshot.events
        if not events:
            raise ValidationError(tr('Add or record events before playing.'))
        chosen_speed = snapshot.speed if speed is None else speed
        chosen_reps = snapshot.repetitions if repetitions is None else repetitions
        def work(control):
            return play_events(events, self.make_driver(control), control, speed=chosen_speed,
                               repetitions=chosen_reps, repeat_interval=snapshot.repeat_interval, notify=self._notify)
        self._launch("play", work, seconds, snapshot.id, activation, len(events))

    def click(self, options, seconds=3):
        options.validate()
        self._launch("click", lambda control: run_clicker(options, self.make_driver(control), control, self._notify), seconds)

    def trigger(self, macro, seconds=0):
        with self.lock:
            if not self.enabled:
                return 'blocked'
            if macro.activation == "toggle" and self.active_id == macro.id:
                self.stop(clear_queue=False)
                return "stopped"
            queued = next((item for item in self.queue if item[0].id == macro.id), None)
            if queued and macro.activation == "toggle":
                self.queue.remove(queued)
                return "unqueued"
            if self.busy:
                if self.task != "play" or self.policy == "block":
                    return "blocked"
                if len(self.queue) >= 32:
                    return "queue_full"
                if not queued:
                    self.queue.append((Macro.from_dict(macro.to_dict()), seconds))
                return "queued"
            repetitions = macro.repetitions if macro.activation == "once" else 0
            self.play(macro, seconds=seconds, repetitions=repetitions, activation=macro.activation)
            return "started"

    def release_trigger(self, macro_id):
        with self.lock:
            self.queue = deque(item for item in self.queue if not (item[0].id == macro_id and item[0].activation == "hold"))
            if self.active_id == macro_id and self.active_mode == "hold":
                self.stop(clear_queue=False)

    def next_queued(self):
        with self.lock:
            if self.enabled and self.queue and not self.busy and not self.shutting_down:
                macro, seconds = self.queue.popleft()
                return self.trigger(macro, seconds)

    def set_enabled(self, enabled):
        with self.lock:
            self.enabled = bool(enabled)
            if not self.enabled:
                self.stop()

    def stop(self, clear_queue=True):
        with self.lock:
            if clear_queue:
                self.queue.clear()
            if self.control:
                self.control.cancel()
            if self.task != "idle":
                self.phase = "stopping"

    def pause(self):
        with self.lock:
            if self.task == "idle" or self.phase in ("countdown", "stopping"):
                return
            paused = not self.control.paused
            self.control.pause(paused)
            if self.recorder:
                self.recorder.pause(paused)
            self.phase = "paused" if paused else "running"
            self.notify("state", {"task": self.task, "phase": self.phase})

    def seek(self, delta=0, restart=False):
        with self.lock:
            if self.task == "play" and self.phase in ("running", "paused") and self.control:
                self.control.seek(delta, restart)

    def reset_recording(self, undo=False):
        with self.lock:
            return self.recorder.reset_capture(undo) if self.recorder else False

    def set_record_interval(self, interval):
        with self.lock:
            if self.recorder and self.recorder.mode == "fixed":
                self.recorder.set_fixed_interval(interval)

    def close(self):
        self.shutting_down = True
        self.stop()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(5)
        return not self.thread or not self.thread.is_alive()
