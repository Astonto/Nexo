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
    args = parser.parse_args()
    data = args.executable.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("El archivo no es un ejecutable de Windows.")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[offset:offset+4] != b"PE\0\0" or struct.unpack_from("<H", data, offset+4)[0] != 0x8664:
        raise ValueError("Esta descarga debe ser un ejecutable x64 real.")
    args.output.mkdir(parents=True, exist_ok=True)
    prefix = f"Nexo-{__version__}-windows-x64"
    executable = args.output / (prefix + ".exe")
    shutil.copy2(args.executable, executable)
    archive = args.output / (prefix + "-portable.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        package.write(executable, "Nexo/Nexo.exe")
        for name in ("README.md", "THIRD_PARTY.md"):
            package.write(root / name, "Nexo/" + name)
        package.writestr("Nexo/LEEME.txt", "Nexo " + __version__ + " — Windows x64\n\nExtrae esta carpeta y abre Nexo.exe. No hace falta instalar Python.\nNexo guarda tus macros y ajustes en Nexo-data junto al ejecutable.\nPara actualizar, cierra Nexo y reemplaza solo el ejecutable. Conserva Nexo-data.\nLa X lo oculta en la bandeja; usa Salir de Nexo para cerrarlo.\n")
        for path in sorted((root / "resources" / "licenses").rglob("*")):
            if path.is_file():
                package.write(path, "Nexo/licenses/" + path.relative_to(root / "resources" / "licenses").as_posix())
        package.write(root / "resources" / "Inter-OFL.txt", "Nexo/licenses/Inter-OFL.txt")
    hashes = args.output / "SHA256SUMS.txt"
    hashes.write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in (executable, archive)), encoding="utf-8")
    print(executable)
    print(archive)
    print(hashes)


if __name__ == "__main__":
    main()
