from __future__ import annotations
from .i18n import tr

import os
import re
import sys
from copy import deepcopy
from pathlib import Path

from .models import ValidationError, number
from .storage import atomic_json, read_json

DEFAULT_HOTKEYS = {"record_start": "Ctrl+Alt+F6", "record_stop": "Ctrl+Alt+F5", "record_pause": "Ctrl+Alt+F7", "play": "Ctrl+Alt+F8",
                   "stop": "Ctrl+Alt+F9", "click": "Ctrl+Alt+F10", "emergency": "Pause"}
CLICKER_DEFAULTS = {"kind": "mouse", "button": "left", "double": False, "position": "current", "x": 0, "y": 0,
                    "key": "V", "hours": 0, "minutes": 0, "seconds": 0, "milliseconds": 100,
                    "variable": False, "interval_max": .5, "repetitions": 100, "infinite": False,
                    "duration": 0.0, "countdown": 3, "hold_button": "", "ignore_ctrl": False, "ignore_alt": False, "ignore_shift": False, "ignore_win": False}
HOTKEY_LABELS = {"record_start": tr('Start recording'), "record_stop": tr('Stop recording'), "record_pause": tr('Pause / resume recording'),
                 "play": tr('Start playback'), "stop": tr('Stop playback'), "click": tr('Start / stop autoclicker'),
                 "emergency": tr('Emergency stop')}
DEFAULTS = {"theme": "dark", "accent": "#ff1744", "language": "en", "countdown": 3,
            "speed": 1.0, "macro_folder": "", "minimize": "keep", "minimize_on_close": True, "confirm_delete": True,
            "capture_moves": False, "hotkeys": DEFAULT_HOTKEYS, "last_macro": "", "window_size": [1240, 820],
            "concurrency": "block", "record_mode": "timed", "fixed_interval": 1.0, "sidebar_collapsed": False, "clicker": CLICKER_DEFAULTS,
            "excluded_keys": [{"key": key, "enabled": True} for key in (27, 46, 44, 45, 20)]}


def data_directory():
    override = os.environ.get("NEXO_DATA_DIR") or os.environ.get("MACROFLOW_DATA_DIR")
    if override:
        return Path(override).resolve()
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    portable = base / "Nexo-data"
    try:
        portable.mkdir(parents=True, exist_ok=True)
        probe = portable / ".write-check"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return portable
    except OSError:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Nexo"


def validate_settings(data):
    from .hotkeys import validate_hotkeys
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValidationError(tr('Unknown setting.'))
    result = deepcopy(DEFAULTS)
    result.update(data)
    if isinstance(result["hotkeys"], dict) and "record" in result["hotkeys"]:

        result["hotkeys"] = dict(result["hotkeys"])
        result["hotkeys"]["record_start"] = result["hotkeys"].pop("record")
        result["hotkeys"].setdefault("record_stop", DEFAULT_HOTKEYS["record_stop"])
    if result["theme"] not in ("dark", "light") or result["language"] not in ("es", "en"):
        raise ValidationError(tr('Invalid theme or language.'))
    if not isinstance(result["accent"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", result["accent"]):
        raise ValidationError(tr('Invalid color. Use #RRGGBB.'))
    result['accent'] = result['accent'].lower()
    number(result["countdown"], tr('Countdown'), 0, 30)
    number(result["speed"], tr('Speed'), 0.1, 10)
    if result["record_mode"] not in ("timed", "fixed"):
        raise ValidationError(tr('Invalid capture mode.'))
    number(result["fixed_interval"], tr('Keystroke interval'), 0.01, 86400)
    clicker = result["clicker"]
    if isinstance(clicker, dict):
        clicker = dict(clicker)
        clicker.setdefault('hold_button', '')
        for modifier in ('ctrl', 'alt', 'shift', 'win'):
            clicker.setdefault('ignore_' + modifier, False)
        result['clicker'] = clicker
    if isinstance(clicker, dict):
        hold = clicker.get('hold_button', '')
        if not isinstance(hold, str):
            raise ValidationError(tr('Invalid hold trigger.'))
        if hold:
            from .triggers import parse_binding
            clicker['hold_button'] = parse_binding(hold).label
    if not isinstance(clicker, dict) or set(clicker) != set(CLICKER_DEFAULTS):
        raise ValidationError(tr('Invalid autoclicker settings.'))
    for key, choices in (("kind", ("mouse", "keyboard")), ("button", ("left", "right", "middle", "x1", "x2")), ("position", ("current", "fixed"))):
        if clicker[key] not in choices:
            raise ValidationError(tr('Invalid autoclicker option.'))
    for key in ("double", "variable", "infinite", "ignore_ctrl", "ignore_alt", "ignore_shift", "ignore_win"):
        if type(clicker[key]) is not bool:
            raise ValidationError(tr('Invalid autoclicker state.'))
    for key, low, high in (("hours", 0, 24), ("minutes", 0, 59), ("seconds", 0, 59), ("milliseconds", 0, 999),
                           ("x", -1_000_000, 1_000_000), ("y", -1_000_000, 1_000_000), ("repetitions", 1, 10_000_000), ("countdown", 0, 30)):
        from .models import integer
        integer(clicker[key], key, low, high)
    number(clicker["interval_max"], tr('Maximum interval'), .001, 90000)
    number(clicker["duration"], tr('Duration'), 0, 604800)
    if not isinstance(clicker["key"], str):
        raise ValidationError(tr('Invalid autoclicker key.'))
    if clicker["key"]:
        from .triggers import parse_binding
        parse_binding(clicker["key"])
    restrictions = result["excluded_keys"]
    if not isinstance(restrictions, list) or len(restrictions) > 254:
        raise ValidationError(tr('Invalid excluded keys list.'))
    seen = set()
    for entry in restrictions:
        if (not isinstance(entry, dict) or set(entry) != {"key", "enabled"}
                or type(entry["key"]) is not int or not 1 <= entry["key"] <= 254
                or type(entry["enabled"]) is not bool or entry["key"] in seen):
            raise ValidationError(tr('Invalid or duplicate excluded key.'))
        seen.add(entry["key"])
    for key in ("macro_folder", "last_macro"):
        if not isinstance(result[key], str) or len(result[key]) > 1000:
            raise ValidationError(tr('Invalid path or identifier.'))
    if result["minimize"] not in ("keep", "pause"):
        raise ValidationError(tr('Invalid minimize behavior.'))
    if result["concurrency"] not in ("block", "queue"):
        raise ValidationError(tr('Invalid execution policy.'))
    for key in ("confirm_delete", "capture_moves", "sidebar_collapsed", "minimize_on_close"):
        if not isinstance(result[key], bool):
            raise ValidationError(tr('Invalid preference.'))
    size = result["window_size"]
    if not isinstance(size, list) or len(size) != 2:
        raise ValidationError(tr('Invalid window size.'))
    for value in size:
        number(value, tr('Window size'), 400, 10000)
    validate_hotkeys(result["hotkeys"])
    return result


class Settings:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "settings.json"
        self.warning = ""
        try:
            data = read_json(self.path) if self.path.exists() else deepcopy(DEFAULTS)
            if isinstance(data, dict) and str(data.get('accent', '')).lower() in {'#444444', '#555555', '#707070'}:
                data['accent'] = DEFAULTS['accent']
            self.data = validate_settings(data)
        except (OSError, ValidationError):
            self.data = deepcopy(DEFAULTS)
            self.warning = tr('Could not read settings. Defaults were loaded; the original file was kept as settings.invalid.json.')
            try:
                self.path.replace(self.directory / "settings.invalid.json")
            except OSError:
                pass

    @property
    def macro_folder(self):
        return Path(self.data["macro_folder"]).expanduser() if self.data["macro_folder"] else self.directory / "macros"

    def save(self, data=None):
        validated = validate_settings(data if data is not None else self.data)
        atomic_json(self.path, validated)
        self.data = validated
