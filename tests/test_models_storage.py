import json
from dataclasses import replace

import pytest

from macroflow.config import DEFAULTS, Settings, validate_settings
from macroflow.models import ClickOptions, Event, Macro, ValidationError, interval_seconds, scaled_delay
from macroflow.storage import Library, atomic_json, read_json


def test_roundtrip_every_event_and_macro_binding():
    macro = Macro(name="Edición", trigger="Ctrl+G", activation="toggle", enabled=True, speed=2.0, repeat_interval=.12,
                  display_signature=[[-1920, 0, 0, 1080], [0, 0, 1920, 1080]], events=[
                      Event("key_down", .15, key="key:ctrl_l"), Event("key_down", key="vk:67"),
                      Event("key_up", key="vk:67"), Event("key_up", key="key:ctrl_l"),
                      Event("move", .1, x=-100, y=50), Event("mouse_down", button="x1", x=-100, y=50),
                      Event("mouse_up", button="x1", x=-100, y=50), Event("scroll", x=200, y=200, dx=-2, dy=3), Event("wait", 2)])
    restored = Macro.from_dict(json.loads(json.dumps(macro.to_dict())))
    assert restored == macro
    assert restored.duration == pytest.approx(2.25)


@pytest.mark.parametrize("event", [Event("code"), Event("wait", float("nan")), Event("wait", float("inf")), Event("wait", -1),
                                    Event("key_down", key="__import__('os')"), Event("mouse_down", button="bad", x=0, y=0),
                                    Event("move", x=True, y=2), Event("move", x=1.1, y=2), Event("move", x=0),
                                    Event("scroll", x=0, y=0, dy=1001), Event("wait", x=0, y=0), Event("wait", dx=1)])
def test_invalid_event_rejected(event):
    with pytest.raises(ValidationError):
        event.validate()


@pytest.mark.parametrize("key", ["char:a", "char:ñ", "key:enter", "key:ctrl_l", "key:f24", "vk:255"])
def test_valid_keys(key):
    Event("key_down", key=key).validate()


@pytest.mark.parametrize("patch", [{"version": True}, {"format": "pickle"}, {"events": "code"}, {"__class__": "subprocess"}, {"id": "../../escape"}, {"enabled": True}, {"activation": "exec"}, {"speed": 0}, {"repeat_interval": -1}])
def test_import_schema_rejects_invalid(patch):
    data = Macro().to_dict()
    data.update(patch)
    with pytest.raises(ValidationError):
        Macro.from_dict(data)


def test_persist_reload_import_duplicate(tmp_path):
    library = Library(tmp_path / "library")
    macro = Macro(name="Original", trigger="A", enabled=True, events=[Event("wait", .2)])
    library.save(macro)
    assert library.load(macro.id) == macro
    duplicate = library.duplicate(macro)
    assert duplicate.id != macro.id and duplicate.events == macro.events
    assert not duplicate.enabled and not duplicate.trigger
    path = tmp_path / "export.json"
    library.export_file(macro, path)
    imported = library.import_file(path)
    assert not imported.enabled and not imported.trigger
    assert imported.id != macro.id
    library.delete(imported.id)
    assert len(library.all()) == 2


def test_corrupt_files_are_kept(tmp_path):
    library = Library(tmp_path)
    corrupt = tmp_path / "broken.json"
    corrupt.write_text('{"events":', encoding="utf-8")
    assert library.all() == []
    assert library.errors == ["broken.json"] and corrupt.exists()
    with pytest.raises(ValidationError):
        library.import_file(corrupt)


def test_invalid_nonfinite_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"x": NaN}', encoding="utf-8")
    with pytest.raises(ValidationError):
        read_json(path)


def test_atomic_failure_preserves_previous(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    atomic_json(path, {"previous": True})
    def fail(*args):
        raise OSError("simulated full disk")
    monkeypatch.setattr("macroflow.storage.os.replace", fail)
    with pytest.raises(OSError):
        atomic_json(path, {"previous": False})
    assert read_json(path) == {"previous": True}
    assert list(tmp_path.glob("*.tmp")) == []


def test_path_traversal_rejected(tmp_path):
    with pytest.raises(ValidationError):
        Library(tmp_path).path_for("../../secret")


def test_settings_recovery_and_persistence(tmp_path):
    settings = Settings(tmp_path)
    settings.data["theme"] = "light"
    settings.data["concurrency"] = "queue"
    settings.save()
    assert Settings(tmp_path).data["theme"] == "light"
    settings.path.write_text("broken", encoding="utf-8")
    restored = Settings(tmp_path)
    assert restored.warning and restored.data["theme"] == "dark"
    assert (tmp_path / "settings.invalid.json").read_text() == "broken"


def test_default_resource_matches_code():
    from pathlib import Path
    path = Path(__file__).parents[1] / "resources" / "defaults.json"
    assert read_json(path) == DEFAULTS


def test_intervals_and_speed():
    assert interval_seconds(1, 2, 3, 4) == pytest.approx(3723.004)
    assert scaled_delay(1, .1) == 10
    assert scaled_delay(1, 10) == .1
    with pytest.raises(ValidationError):
        interval_seconds(milliseconds=0)
    with pytest.raises(ValidationError):
        scaled_delay(1, 0)
    with pytest.raises(ValidationError):
        ClickOptions(interval=.2, interval_max=.1).validate()
