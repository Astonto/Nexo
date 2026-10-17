import ctypes
import json
import os
from pathlib import Path
import sys

import pytest

from macroflow import paths


@pytest.fixture
def installation_environment(monkeypatch, tmp_path):
    base = tmp_path / 'application'
    base.mkdir()
    local = tmp_path / 'user'
    monkeypatch.setattr(paths, 'application_directory', lambda: base)
    monkeypatch.setenv('LOCALAPPDATA', str(local))
    monkeypatch.delenv('NEXO_DATA_DIR', raising=False)
    monkeypatch.delenv('MACROFLOW_DATA_DIR', raising=False)
    return base, local


def test_installed_app_always_uses_user_data_even_in_writable_location(installation_environment):
    base, local = installation_environment
    (base / 'nexo-installed').write_text('installed', encoding='utf-8')
    assert paths.data_directory() == local / 'Nexo'
    assert not (base / 'Nexo-data').exists()


def test_portable_app_keeps_its_existing_data(installation_environment):
    base, local = installation_environment
    portable = base / 'Nexo-data'
    portable.mkdir()
    settings = portable / 'settings.json'
    settings.write_text('{"language":"es"}', encoding='utf-8')
    assert paths.data_directory() == portable
    assert settings.read_text(encoding='utf-8') == '{"language":"es"}'
    assert not (local / 'Nexo').exists()


def test_data_override_takes_priority_in_installed_edition(installation_environment, monkeypatch):
    base, local = installation_environment
    (base / 'nexo-installed').touch()
    monkeypatch.setenv('NEXO_DATA_DIR', str(local / 'isolated'))
    assert paths.data_directory() == local / 'isolated'


def test_readonly_portable_location_falls_back_to_user_data(installation_environment, monkeypatch):
    base, local = installation_environment
    original = Path.mkdir
    def mkdir(path, *args, **kwargs):
        if path == base / 'Nexo-data':
            raise PermissionError('read only')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', mkdir)
    assert paths.data_directory() == local / 'Nexo'


def test_installed_language_and_settings_use_the_same_directory(installation_environment, monkeypatch):
    from macroflow.config import Settings
    from macroflow.i18n import startup_language
    base, local = installation_environment
    (base / 'nexo-installed').touch()
    target = local / 'Nexo'
    target.mkdir(parents=True)
    (target / 'settings.json').write_text(json.dumps({'language': 'es'}), encoding='utf-8')
    monkeypatch.delenv('NEXO_LANGUAGE', raising=False)
    assert startup_language() == 'es'
    assert Settings().directory == target
    assert Settings().data['language'] == 'es'


def test_packaged_directory_is_next_to_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'Nexo.exe'))
    assert paths.application_directory() == tmp_path


@pytest.mark.skipif(os.name != 'nt', reason='Windows installer mutex')
def test_installer_can_detect_running_application():
    from macroflow.single_instance import create_installation_guard
    handle = create_installation_guard()
    assert handle
    kernel = ctypes.windll.kernel32
    open_mutex = kernel.OpenMutexW
    open_mutex.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    open_mutex.restype = ctypes.c_void_p
    close = kernel.CloseHandle
    close.argtypes = [ctypes.c_void_p]
    close.restype = ctypes.c_bool
    found = open_mutex(0x100000, False, 'Nexo.SetupGuard')
    try:
        assert found
    finally:
        if found:
            close(found)
        close(handle)
