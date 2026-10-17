from __future__ import annotations

import os
import sys
from pathlib import Path


def application_directory():
    return Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent


def user_data_directory():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Nexo'


def data_directory():
    override = os.environ.get('NEXO_DATA_DIR') or os.environ.get('MACROFLOW_DATA_DIR')
    if override:
        return Path(override).resolve()
    base = application_directory()
    if (base / 'nexo-installed').is_file():
        return user_data_directory()
    portable = base / 'Nexo-data'
    try:
        portable.mkdir(parents=True, exist_ok=True)
        probe = portable / '.write-check'
        probe.write_bytes(b'')
        probe.unlink()
        return portable
    except OSError:
        return user_data_directory()
