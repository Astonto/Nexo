
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

root = Path(__file__).resolve().parent.parent
app = QApplication.instance() or QApplication([])
renderer = QSvgRenderer(str(root / "resources" / "nexo.svg"))
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
renderer.render(painter)
painter.end()
if not image.save(str(root / "resources" / "nexo.ico"), "ICO"):
    raise RuntimeError("No se pudo generar el icono.")
if sys.platform == "win32":
    import comtypes.client
    comtypes.client.GetModule("UIAutomationCore.dll")
print("Icono y recursos de accesibilidad preparados.")
