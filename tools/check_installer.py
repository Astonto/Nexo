import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import winreg

APP_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{164947D3-507E-43B7-AC53-AB298BD12EE6}_is1'


def registration():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return {name: winreg.QueryValueEx(key, name)[0] for name in ('DisplayName', 'DisplayVersion', 'InstallLocation')}
    except FileNotFoundError:
        return None


def shell_folder(identifier):
    value = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, identifier, None, 0, value):
        raise RuntimeError('Could not read the Windows shortcut location.')
    return Path(value.value)


def run_installer(executable, arguments):
    result = subprocess.run([str(executable), *arguments], timeout=90)
    if result.returncode:
        raise RuntimeError(f'Installer returned {result.returncode}.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('installer', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    installer = args.installer.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        parser.error('Choose a new output directory for this isolated check.')
    if registration() is not None:
        parser.error('Nexo is already installed for this user; this check will not change that installation.')
    desktop = shell_folder(0x10) / 'Nexo.lnk'
    if desktop.exists():
        parser.error('A Nexo desktop shortcut already exists; this check will not replace it.')
    start = shell_folder(0x02) / 'Nexo' / 'Nexo.lnk'
    if start.exists():
        parser.error('A Nexo Start menu shortcut already exists; this check will not replace it.')
    output.mkdir(parents=True)
    application = output / 'application'
    local = output / 'user-data'
    data = local / 'Nexo'
    data.mkdir(parents=True)
    settings = data / 'settings.json'
    settings.write_text('{"language":"es"}', encoding='utf-8')
    macro_id = str(uuid.uuid4())
    macros = data / 'macros'
    macros.mkdir()
    macro = macros / (macro_id + '.json')
    macro.write_text(json.dumps({'format': 'macroflow', 'version': 1, 'id': macro_id, 'name': 'Installer check', 'category': 'QA', 'modified': '2026-10-16T00:00:00+00:00', 'events': []}), encoding='utf-8')
    arguments = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER', f'/DIR={application}', '/TASKS=desktopicon']
    installed = False
    report = {}
    try:
        run_installer(installer, [*arguments, f'/LOG={output / "install.log"}'])
        installed = True
        entry = registration()
        assert entry and entry['DisplayName'] == 'Nexo', entry
        assert Path(entry['InstallLocation']).resolve() == application
        assert (application / 'nexo-installed').is_file()
        assert start.is_file() and desktop.is_file()
        from comtypes.client import CreateObject
        shell = CreateObject('WScript.Shell', dynamic=True)
        for shortcut in (start, desktop):
            assert Path(shell.CreateShortcut(str(shortcut)).TargetPath).resolve() == application / 'Nexo.exe'
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'LOCALAPPDATA': str(local)}
        for name in ('NEXO_DATA_DIR', 'MACROFLOW_DATA_DIR', 'NEXO_LANGUAGE'):
            env.pop(name, None)
        startup = output / 'startup.json'
        result = subprocess.run([str(application / 'Nexo.exe'), '--smoke-test', '--smoke-report', str(startup)], env=env, timeout=60)
        assert result.returncode == 0, result.returncode
        app_report = json.loads(startup.read_text(encoding='utf-8'))
        assert Path(app_report['data_directory']).resolve() == data
        assert app_report['language'] == 'es' and app_report['pages'] == 7
        assert not (application / 'Nexo-data').exists()
        previous = {path: path.read_bytes() for path in (settings, macro)}
        run_installer(installer, [*arguments, f'/LOG={output / "upgrade.log"}'])
        assert all(path.read_bytes() == value for path, value in previous.items())
        report = {'registered': entry, 'shortcuts_verified': True, 'installed_startup': True, 'user_data_location': str(data), 'same_version_reinstall_kept_data': True}
    finally:
        if installed:
            uninstaller = application / 'unins000.exe'
            run_installer(uninstaller, ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/LOG={output / "uninstall.log"}'])
            for _ in range(50):
                if not (application / 'Nexo.exe').exists() and registration() is None:
                    break
                time.sleep(.1)
            assert not (application / 'Nexo.exe').exists()
            assert not (application / 'nexo-installed').exists()
            assert registration() is None
            assert not start.exists() and not desktop.exists()
            assert settings.is_file() and macro.is_file()
            report['uninstalled_and_kept_data'] = True
            (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
