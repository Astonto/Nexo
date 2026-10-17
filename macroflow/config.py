from __future__ import annotations

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
HOTKEY_LABELS = {"record_start": "Iniciar grabación", "record_stop": "Detener grabación", "record_pause": "Pausar / reanudar grabación",
                 "play": "Iniciar reproducción", "stop": "Detener reproducción", "click": "Iniciar / detener autoclicker",
                 "emergency": "Parada de emergencia"}
DEFAULTS = {"theme": "dark", "accent": "#ff1744", "language": "es", "countdown": 3,
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
        raise ValidationError("Configuración desconocida.")
    result = deepcopy(DEFAULTS)
    result.update(data)
    if isinstance(result["hotkeys"], dict) and "record" in result["hotkeys"]:

        result["hotkeys"] = dict(result["hotkeys"])
        result["hotkeys"]["record_start"] = result["hotkeys"].pop("record")
        result["hotkeys"].setdefault("record_stop", DEFAULT_HOTKEYS["record_stop"])
    if result["theme"] not in ("dark", "light") or result["language"] != "es":
        raise ValidationError("Tema o idioma inválido.")
    if not isinstance(result["accent"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", result["accent"]):
        raise ValidationError("Color inválido. Usa #RRGGBB.")
    result['accent'] = result['accent'].lower()
    number(result["countdown"], "Cuenta regresiva", 0, 30)
    number(result["speed"], "Velocidad", 0.1, 10)
    if result["record_mode"] not in ("timed", "fixed"):
        raise ValidationError("Modo de captura inválido.")
    number(result["fixed_interval"], "Intervalo de pulsaciones", 0.01, 86400)
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
            raise ValidationError('Activador de repetición inválido.')
        if hold:
            from .triggers import parse_binding
            clicker['hold_button'] = parse_binding(hold).label
    if not isinstance(clicker, dict) or set(clicker) != set(CLICKER_DEFAULTS):
        raise ValidationError("Configuración del autoclicker inválida.")
    for key, choices in (("kind", ("mouse", "keyboard")), ("button", ("left", "right", "middle", "x1", "x2")), ("position", ("current", "fixed"))):
        if clicker[key] not in choices:
            raise ValidationError("Opción del autoclicker inválida.")
    for key in ("double", "variable", "infinite", "ignore_ctrl", "ignore_alt", "ignore_shift", "ignore_win"):
        if type(clicker[key]) is not bool:
            raise ValidationError("Estado del autoclicker inválido.")
    for key, low, high in (("hours", 0, 24), ("minutes", 0, 59), ("seconds", 0, 59), ("milliseconds", 0, 999),
                           ("x", -1_000_000, 1_000_000), ("y", -1_000_000, 1_000_000), ("repetitions", 1, 10_000_000), ("countdown", 0, 30)):
        from .models import integer
        integer(clicker[key], key, low, high)
    number(clicker["interval_max"], "Intervalo máximo", .001, 90000)
    number(clicker["duration"], "Duración", 0, 604800)
    if not isinstance(clicker["key"], str):
        raise ValidationError("Tecla del autoclicker inválida.")
    if clicker["key"]:
        from .triggers import parse_binding
        parse_binding(clicker["key"])
    restrictions = result["excluded_keys"]
    if not isinstance(restrictions, list) or len(restrictions) > 254:
        raise ValidationError("Lista de teclas excluidas inválida.")
    seen = set()
    for entry in restrictions:
        if (not isinstance(entry, dict) or set(entry) != {"key", "enabled"}
                or type(entry["key"]) is not int or not 1 <= entry["key"] <= 254
                or type(entry["enabled"]) is not bool or entry["key"] in seen):
            raise ValidationError("Tecla excluida inválida o duplicada.")
        seen.add(entry["key"])
    for key in ("macro_folder", "last_macro"):
        if not isinstance(result[key], str) or len(result[key]) > 1000:
            raise ValidationError("Ruta o identificador inválido.")
    if result["minimize"] not in ("keep", "pause"):
        raise ValidationError("Comportamiento al minimizar inválido.")
    if result["concurrency"] not in ("block", "queue"):
        raise ValidationError("Política de ejecución inválida.")
    for key in ("confirm_delete", "capture_moves", "sidebar_collapsed", "minimize_on_close"):
        if not isinstance(result[key], bool):
            raise ValidationError("Preferencia inválida.")
    size = result["window_size"]
    if not isinstance(size, list) or len(size) != 2:
        raise ValidationError("Tamaño de ventana inválido.")
    for value in size:
        number(value, "Tamaño de ventana", 400, 10000)
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
            self.warning = "No se pudo leer la configuración. Se cargaron valores predeterminados; el archivo original se conserva como settings.invalid.json."
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
