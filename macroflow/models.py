from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

MAX_EVENTS = 100_000
MAX_FILE_BYTES = 32 * 1024 * 1024
KINDS = ("key_down", "key_up", "mouse_down", "mouse_up", "move", "scroll", "wait")
LABELS = {"key_down": "Pulsar tecla", "key_up": "Soltar tecla", "mouse_down": "Pulsar botón",
          "mouse_up": "Soltar botón", "move": "Mover cursor", "scroll": "Rueda", "wait": "Pausa"}
KEY_NAMES = set("alt alt_l alt_r alt_gr backspace caps_lock cmd cmd_l cmd_r ctrl ctrl_l ctrl_r delete down end enter esc home insert left menu num_lock page_down page_up pause print_screen right scroll_lock shift shift_l shift_r space tab up media_play_pause media_volume_mute media_volume_down media_volume_up media_next media_previous".split())
KEY_NAMES.update(f"f{i}" for i in range(1, 25))


class ValidationError(ValueError):
    pass


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValidationError(f"{name}: debe estar entre {low} y {high}.")
    return value


def integer(value, name, low, high):
    number(value, name, low, high)
    if not isinstance(value, int):
        raise ValidationError(f"{name}: se necesita un número entero.")
    return value


def valid_key(value):
    if not isinstance(value, str):
        raise ValidationError("Tecla inválida.")
    if value.startswith("char:") and len(value[5:]) == 1 and ord(value[5:]) >= 32:
        return value
    if value.startswith("key:") and value[4:] in KEY_NAMES:
        return value
    if re.fullmatch(r"vk:\d{1,3}", value) and 1 <= int(value[3:]) <= 255:
        return value
    raise ValidationError("Usa una letra, key:enter, key:ctrl_l, key:f6 o vk:65.")


def normalize_key(value):
    if len(value) == 1:
        return "char:" + value
    if ":" not in value:
        value = "key:" + value.strip().lower()
    return valid_key(value)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    delay: float = 0.0
    key: str | None = None
    button: str | None = None
    x: int | None = None
    y: int | None = None
    dx: int = 0
    dy: int = 0

    def validate(self):
        if self.kind not in KINDS:
            raise ValidationError("Tipo de evento desconocido.")
        number(self.delay, "Tiempo de espera", 0, 86400)
        if self.kind.startswith("key_"):
            valid_key(self.key)
        elif self.key is not None:
            raise ValidationError("Este evento no admite una tecla.")
        if self.kind.startswith("mouse_"):
            if self.button not in ("left", "right", "middle", "x1", "x2"):
                raise ValidationError("Botón de ratón inválido.")
        elif self.button is not None:
            raise ValidationError("Este evento no admite un botón.")
        if self.kind in ("mouse_down", "mouse_up", "move", "scroll"):
            integer(self.x, "X", -1_000_000, 1_000_000)
            integer(self.y, "Y", -1_000_000, 1_000_000)
        elif self.x is not None or self.y is not None:
            raise ValidationError("Este evento no admite coordenadas.")
        integer(self.dx, "Rueda horizontal", -1000, 1000)
        integer(self.dy, "Rueda vertical", -1000, 1000)
        if self.kind != "scroll" and (self.dx or self.dy):
            raise ValidationError("Desplazamiento solo disponible en eventos de rueda.")
        return self

    def to_dict(self):
        self.validate()
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) - set(cls.__dataclass_fields__):
            raise ValidationError("Estructura de evento inválida.")
        try:
            return cls(**data).validate()
        except (TypeError, KeyError) as exc:
            raise ValidationError("Faltan datos del evento.") from exc


@dataclass
class Macro:
    name: str = "Nueva macro"
    category: str = "General"
    events: list[Event] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    modified: str = field(default_factory=now_iso)
    display_signature: list = field(default_factory=list)
    trigger: str = ""
    activation: str = "once"
    repetitions: int = 1
    speed: float = 1.0
    repeat_interval: float = 0.05
    enabled: bool = False

    @property
    def duration(self):
        return sum(e.delay for e in self.events)

    def validate(self):
        for value, label, maximum in ((self.name, "Nombre", 120), (self.category, "Categoría", 80)):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
                raise ValidationError(f"{label}: escribe entre 1 y {maximum} caracteres sin saltos de línea.")
        try:
            if str(UUID(self.id)) != self.id:
                raise ValueError()
            datetime.fromisoformat(self.modified)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationError("Identificador o fecha inválidos.") from exc
        if not isinstance(self.events, list) or len(self.events) > MAX_EVENTS:
            raise ValidationError(f"Máximo {MAX_EVENTS:,} eventos por macro.")
        for event in self.events:
            if not isinstance(event, Event):
                raise ValidationError("Evento inválido.")
            event.validate()
        if not isinstance(self.trigger, str):
            raise ValidationError("Atajo inválido.")
        if self.trigger:
            from .triggers import parse_binding
            parse_binding(self.trigger)
        if self.activation not in ("once", "hold", "toggle") or not isinstance(self.enabled, bool):
            raise ValidationError("Modo de activación o estado inválido.")
        if self.enabled and not self.trigger:
            raise ValidationError("Asigna un atajo antes de activar la macro.")
        integer(self.repetitions, "Repeticiones", 1, 10_000_000)
        number(self.speed, "Velocidad", 0.1, 10)
        number(self.repeat_interval, "Intervalo entre repeticiones", 0.01, 86400)
        if not isinstance(self.display_signature, list) or len(self.display_signature) > 32:
            raise ValidationError("Información de pantalla inválida.")
        for rect in self.display_signature:
            if not isinstance(rect, list) or len(rect) != 4:
                raise ValidationError("Información de monitor inválida.")
            for val in rect:
                integer(val, "Monitor", -1_000_000, 1_000_000)
        return self

    def to_dict(self):
        self.validate()
        return {"format": "macroflow", "version": 1, "id": self.id, "name": self.name,
                "category": self.category, "modified": self.modified,
                "display_signature": self.display_signature, "events": [e.to_dict() for e in self.events],
                "trigger": self.trigger, "activation": self.activation, "repetitions": self.repetitions,
                "speed": self.speed, "repeat_interval": self.repeat_interval, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, data):
        allowed = {"format", "version", "id", "name", "category", "modified", "display_signature", "events",
                   "trigger", "activation", "repetitions", "speed", "repeat_interval", "enabled"}
        if not isinstance(data, dict) or set(data) - allowed or data.get("format") != "macroflow" or type(data.get("version")) is not int or data.get("version") != 1:
            raise ValidationError("No es un archivo Nexo versión 1.")
        if not isinstance(data.get("events"), list) or len(data["events"]) > MAX_EVENTS:
            raise ValidationError("Lista de eventos inválida o demasiado grande.")
        try:
            return cls(name=data["name"], category=data["category"], id=data["id"], modified=data["modified"],
                       display_signature=data.get("display_signature", []),
                       events=[Event.from_dict(e) for e in data["events"]],
                       **{key: data[key] for key in ("trigger", "activation", "repetitions", "speed", "repeat_interval", "enabled") if key in data}).validate()
        except (KeyError, TypeError) as exc:
            raise ValidationError("Faltan campos de la macro.") from exc


def interval_seconds(hours=0, minutes=0, seconds=0, milliseconds=0):
    number(hours, "Horas", 0, 24)
    number(minutes, "Minutos", 0, 59)
    number(seconds, "Segundos", 0, 59)
    number(milliseconds, "Milisegundos", 0, 999)
    result = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    return number(result, "Intervalo (segundos)", 0.001, 90000)


def scaled_delay(delay, speed):
    number(delay, "Tiempo", 0, 86400)
    number(speed, "Velocidad", 0.1, 10)
    return delay / speed


@dataclass(frozen=True)
class ClickOptions:
    button: str = "left"
    double: bool = False
    interval: float = 0.1
    interval_max: float | None = None
    position: tuple[int, int] | None = None
    repetitions: int = 0
    duration: float = 0
    key: str = ""

    def validate(self):
        if self.key:
            from .triggers import parse_binding
            if not isinstance(parse_binding(self.key).key, int):
                raise ValidationError("El repetidor de teclado necesita una tecla.")
        if self.button not in ("left", "right", "middle", "x1", "x2") or not isinstance(self.double, bool):
            raise ValidationError("Tipo de clic inválido.")
        number(self.interval, "Intervalo", 0.001, 90000)
        if self.interval_max is not None:
            number(self.interval_max, "Intervalo máximo", self.interval, 90000)
        integer(self.repetitions, "Repeticiones", 0, 10_000_000)
        number(self.duration, "Duración máxima", 0, 86400 * 7)
        if self.position is not None:
            if len(self.position) != 2:
                raise ValidationError("Posición inválida.")
            for v in self.position:
                integer(v, "Coordenada", -1_000_000, 1_000_000)
        return self
