from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1] / "resources" / "licenses"
root.mkdir(parents=True, exist_ok=True)
for name in ("PySide6", "PySide6_Essentials", "shiboken6", "pynput", "comtypes", "PyInstaller", "six"):
    try:
        package = distribution(name)
    except PackageNotFoundError:
        continue
    destination = root / name
    destination.mkdir(exist_ok=True)
    for entry in package.files or []:
        is_license = any(token in entry.name.lower() for token in ("license", "copying")) or any("license" in part.lower() for part in entry.parts)
        if is_license and entry.suffix.lower() in ("", ".txt", ".md", ".rst") and package.locate_file(entry).is_file():
            shutil.copy2(package.locate_file(entry), destination / entry.name)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copy2(python_license, root / "Python-LICENSE.txt")
print(f"Collected {sum(p.is_file() for p in root.rglob('*'))} license texts.")
