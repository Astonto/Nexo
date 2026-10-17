import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macroflow import __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', type=Path)
    parser.add_argument('--executable', type=Path, default=ROOT / 'dist/Nexo.exe')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/release')
    args = parser.parse_args()
    candidates = [args.compiler, shutil.which('ISCC.exe')]
    for variable in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
        base = os.environ.get(variable)
        if base:
            candidates.extend([Path(base) / 'Inno Setup 6/ISCC.exe', Path(base) / 'Programs/Inno Setup 6/ISCC.exe'])
    compiler = next((Path(p) for p in candidates if p and Path(p).is_file()), None)
    if compiler is None:
        parser.error('Install Inno Setup 6, or pass --compiler with the path to ISCC.exe.')
    executable = args.executable.resolve(strict=True)
    data = executable.read_bytes()
    if data[:2] != b'MZ' or len(data) < 64:
        parser.error('The application must be a Windows executable.')
    offset = struct.unpack_from('<I', data, 0x3c)[0]
    if data[offset:offset+4] != b'PE\0\0' or struct.unpack_from('<H', data, offset+4)[0] != 0x8664:
        parser.error('The application must be a native x64 executable.')
    args.output.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(compiler.resolve()), f'/DAppVersion={__version__}', f'/DAppExe={executable}', f'/O{args.output.resolve()}', str(ROOT / 'installer/Nexo.iss')], check=True)
    result = args.output / f'Nexo-{__version__}-windows-x64-setup.exe'
    if not result.is_file():
        raise RuntimeError('The compiler did not produce the installer.')
    print(result)


if __name__ == '__main__':
    main()
