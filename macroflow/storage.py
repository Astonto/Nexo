from __future__ import annotations
from .i18n import tr

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from .models import MAX_FILE_BYTES, Macro, ValidationError, now_iso


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def read_json(path: Path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValidationError(tr('File too large (maximum 32 MB).'))
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle, parse_constant=lambda _: (_ for _ in ()).throw(ValidationError(tr('Invalid JSON number.'))))
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise ValidationError(tr('The JSON file is damaged or has an invalid structure.')) from exc


class Library:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.errors = []

    def path_for(self, macro_id):

        from uuid import UUID
        try:
            canonical = str(UUID(macro_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValidationError(tr('Invalid identifier.')) from exc
        return self.folder / f"{canonical}.json"

    def all(self):
        macros = []
        self.errors = []
        for path in self.folder.glob("*.json"):
            try:
                macro = Macro.from_dict(read_json(path))
                if self.path_for(macro.id).name != path.name:
                    raise ValidationError(tr('The identifier does not match the file.'))
                macros.append(macro)
            except (OSError, ValidationError):
                self.errors.append(path.name)
        return sorted(macros, key=lambda m: m.modified, reverse=True)

    def save(self, macro):
        macro.validate()
        macro.modified = now_iso()
        atomic_json(self.path_for(macro.id), macro.to_dict())

    def load(self, macro_id):
        return Macro.from_dict(read_json(self.path_for(macro_id)))

    def duplicate(self, macro):
        duplicate = Macro.from_dict(macro.to_dict())
        duplicate.id = str(uuid4())
        duplicate.name = macro.name[:110] + tr(' — copy')
        duplicate.trigger = ""
        duplicate.enabled = False
        self.save(duplicate)
        return duplicate

    def delete(self, macro_id):
        self.path_for(macro_id).unlink(missing_ok=True)

    def import_file(self, path):
        macro = Macro.from_dict(read_json(Path(path)))
        macro.id = str(uuid4())
        macro.enabled = False
        macro.trigger = ""
        self.save(macro)
        return macro

    def export_file(self, macro, path):
        atomic_json(Path(path), macro.to_dict())
