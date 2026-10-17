import threading
import time

import pytest

from macroflow.models import ClickOptions, Event, ValidationError
from macroflow.playback import Cancelled, RunControl, countdown, play_events, run_clicker


def spawn(callback):
    errors = []
    def run():
        try:
            callback()
        except Cancelled:
            pass
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    return thread, errors


def test_order_repetitions_and_release(driver):
    events = [Event("key_down", key="key:ctrl_l"), Event("mouse_down", button="left", x=1, y=2)]
    count = play_events(events, driver, RunControl(), repetitions=3)
    assert count == 3 and driver.events == events * 3
    assert not driver.held_keys and not driver.held_buttons
    assert driver.releases >= 3


def test_infinite_repeat_cancels(driver):
    control = RunControl()
    thread, errors = spawn(lambda: play_events([Event("wait")], driver, control, repetitions=0))
    time.sleep(.06)
    control.cancel()
    thread.join(1)
    assert not thread.is_alive() and not errors and len(driver.events) >= 2


def test_cancel_long_delay_immediate_and_releases(driver):
    control = RunControl()
    thread, errors = spawn(lambda: play_events([Event("key_down", key="char:a"), Event("wait", 8000)], driver, control))
    deadline = time.monotonic() + 1
    while not driver.held_keys and time.monotonic() < deadline:
        time.sleep(.002)
    start = time.monotonic()
    control.cancel()
    thread.join(.5)
    assert time.monotonic() - start < .5 and not thread.is_alive()
    assert not driver.held_keys and not driver.held_buttons and not errors


def test_pause_resume_excludes_paused_duration(driver):
    control = RunControl()
    thread, errors = spawn(lambda: play_events([Event("key_down", key="char:a"), Event("wait", .16), Event("key_up", key="char:a")], driver, control))
    time.sleep(.035)
    control.pause(True)
    time.sleep(.035)
    assert driver.suspensions == 1 and not driver.held_keys
    elapsed = control.elapsed
    time.sleep(.08)
    assert abs(control.elapsed - elapsed) < .015
    assert len(driver.events) == 1
    control.pause(False)
    thread.join(1)
    assert not thread.is_alive() and not errors and driver.restorations == 1
    assert not driver.held_keys


def test_cancel_while_paused_does_not_restore(driver):
    control = RunControl()
    thread, errors = spawn(lambda: play_events([Event("key_down", key="char:a"), Event("wait", 10)], driver, control))
    time.sleep(.03)
    control.pause()
    time.sleep(.03)
    control.cancel()
    thread.join(1)
    assert driver.restorations == 0 and not driver.held_keys and not errors


def test_release_on_driver_failure(driver):
    original = driver.dispatch
    def dispatch(event):
        original(event)
        if len(driver.events) == 2:
            raise RuntimeError("device failure")
    driver.dispatch = dispatch
    with pytest.raises(RuntimeError):
        play_events([Event("key_down", key="char:a"), Event("move", x=2, y=2)], driver, RunControl())
    assert not driver.held_keys and not driver.held_buttons


def test_scaled_timing(driver):
    start = time.monotonic()
    play_events([Event("wait", .2)], driver, RunControl(), speed=4)
    assert .04 <= time.monotonic() - start < .4


def test_repeat_interval(driver):
    start = time.monotonic()
    play_events([Event("wait")], driver, RunControl(), repetitions=3, repeat_interval=.03)
    assert time.monotonic() - start >= .055


def test_click_count_double_and_variable(driver):
    ranges = []
    def rng(low, high):
        ranges.append((low, high))
        return low
    result = run_clicker(ClickOptions(double=True, interval=.01, interval_max=.02, repetitions=3), driver, RunControl(), rng=rng)
    assert result == 6 and len([e for e in driver.events if e.kind == "mouse_down"]) == 6
    assert ranges == [(.01, .02), (.01, .02)]
    assert not driver.held_buttons


def test_click_duration_interrupts_long_interval(driver):
    start = time.monotonic()
    count = run_clicker(ClickOptions(interval=500, duration=.07), driver, RunControl())
    assert count == 1 and .06 <= time.monotonic() - start < .4


def test_clicker_stop_releases_button(driver):
    control = RunControl()
    thread, errors = spawn(lambda: run_clicker(ClickOptions(interval=500), driver, control))
    time.sleep(.03)
    control.cancel()
    thread.join(.5)
    assert not thread.is_alive() and not driver.held_buttons and not errors


def test_countdown_cancel():
    control = RunControl()
    updates = []
    thread, errors = spawn(lambda: countdown(control, 30, lambda *args: updates.append(args)))
    time.sleep(.02)
    control.cancel()
    thread.join(.5)
    assert not thread.is_alive() and updates and not errors


def test_invalid_playback_options(driver):
    with pytest.raises(ValidationError):
        play_events([], driver, RunControl())
    with pytest.raises(ValidationError):
        play_events([Event("wait")], driver, RunControl(), repetitions=-1)


def test_seek_forward_interrupts_wait_and_releases_held_input(driver):
    control = RunControl()
    events = [Event("key_down", key="char:a"), Event("wait", 8000), Event("key_down", key="char:b"), Event("key_up", key="char:b")]
    thread, errors = spawn(lambda: play_events(events, driver, control))
    deadline = time.monotonic() + 1
    while control.current_index != 1 and time.monotonic() < deadline:
        time.sleep(.002)
    control.seek(1)
    thread.join(.5)
    assert not thread.is_alive() and not errors
    assert [e.kind for e in driver.events] == ["key_down", "key_down", "key_up"]
    assert driver.releases >= 2 and not driver.held_keys


def test_seek_back_while_paused_and_restart(driver):
    control = RunControl()
    changes = []
    events = [Event("key_down", key="char:a"), Event("key_up", key="char:a"), Event("wait", 8000)]
    thread, errors = spawn(lambda: play_events(events, driver, control, notify=lambda name, data: changes.append(data)))
    deadline = time.monotonic() + 1
    while control.current_index != 2 and time.monotonic() < deadline:
        time.sleep(.002)
    control.pause()
    control.seek(-1)
    time.sleep(.03)
    assert control.current_index == 1 and len(driver.events) == 2
    control.seek(restart=True)
    time.sleep(.03)
    assert control.current_index == 0 and control.elapsed < .02
    control.pause(False)
    time.sleep(.03)
    assert len(driver.events) == 4
    assert any(item.get("seek") for item in changes)
    control.cancel()
    thread.join(.5)
    assert not thread.is_alive() and not errors and not driver.held_keys


def test_emergency_overrides_pending_seek(driver):
    control = RunControl()
    control.event_count = 2
    control.seek(1)
    control.cancel()
    with pytest.raises(Cancelled):
        play_events([Event("wait", 10), Event("wait")], driver, control)
    assert driver.events == []
