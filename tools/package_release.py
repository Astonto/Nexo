import argparse
import hashlib
import shutil
import struct
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from macroflow import __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", type=Path, default=root / "dist" / "release")
    parser.add_argument("--installer", type=Path)
    args = parser.parse_args()
    data = args.executable.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("The file is not a Windows executable.")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[offset:offset+4] != b"PE\0\0" or struct.unpack_from("<H", data, offset+4)[0] != 0x8664:
        raise ValueError("This download must be a native x64 executable.")
    args.output.mkdir(parents=True, exist_ok=True)
    prefix = f"Nexo-{__version__}-windows-x64"
    executable = args.output / (prefix + ".exe")
    shutil.copy2(args.executable, executable)
    archive = args.output / (prefix + "-portable.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        package.write(executable, "Nexo/Nexo.exe")
        for name in ("README.md", "THIRD_PARTY.md", "LICENSE"):
            package.write(root / name, "Nexo/" + name)
        package.write(root / "docs/images/home.png", "Nexo/docs/images/home.png")
        package.writestr("Nexo/START_HERE.txt", "Nexo " + __version__ + " — Windows x64\n\nExtract this folder and open Nexo.exe. Python is not required.\nNexo saves macros and settings in Nexo-data next to the executable.\nTo update, quit Nexo and replace only the executable. Keep Nexo-data.\nThe X hides Nexo in the system tray; use Quit Nexo to exit.\nChange your language in Settings > General, save and restart Nexo.\n")
        for path in sorted((root / "resources" / "licenses").rglob("*")):
            if path.is_file():
                package.write(path, "Nexo/licenses/" + path.relative_to(root / "resources" / "licenses").as_posix())
        package.write(root / "resources" / "Inter-OFL.txt", "Nexo/licenses/Inter-OFL.txt")
    artifacts = [executable, archive]
    if args.installer:
        installer = args.installer.resolve(strict=True)
        expected_name = prefix + '-setup.exe'
        if installer.name != expected_name:
            parser.error('The installer filename must match the current version and architecture.')
        destination = args.output / expected_name
        if installer != destination.resolve():
            shutil.copy2(installer, destination)
        artifacts.append(destination)
    hashes = args.output / "SHA256SUMS.txt"
    hashes.write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in artifacts), encoding="utf-8")
    print(executable)
    print(archive)
    print(hashes)


if __name__ == "__main__":
    main()
