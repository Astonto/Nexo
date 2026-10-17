from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap, QColor
from PySide6.QtSvg import QSvgRenderer
from ..app import resource_path

PATHS = {
    "nav_home": '<path d="M3 10L12 3L21 10V20A1 1 0 0 1 20 21H15V14H9V21H4A1 1 0 0 1 3 20Z"/>',
    "nav_record": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
    "nav_macros": '<rect x="3" y="3" width="6" height="6" rx="1.5"/><rect x="15" y="15" width="6" height="6" rx="1.5"/><path d="M6 9V16A2 2 0 0 0 8 18H15"/>',
    "nav_click": '<path d="M4 3L20 13L13 15L10 22Z M16 3L17 1M20 7L23 6"/>',
    "nav_edit": '<path d="M14 5L19 10M4 20L5 14L16 3A2 2 0 0 1 19 3L21 5A2 2 0 0 1 21 8L10 19Z M4 20H20"/>',
    "nav_library": '<path d="M3 8V5A2 2 0 0 1 5 3H10L13 6H19A2 2 0 0 1 21 8M3 8H21L19 20H3Z"/>',
    "nav_settings": '<path d="M9 2H15L15.5 5L18 6L20.5 4.5L23 9L20.5 11V13L23 15L20.5 19.5L18 18L15.5 19L15 22H9L8.5 19L6 18L3.5 19.5L1 15L3.5 13V11L1 9L3.5 4.5L6 6L8.5 5Z"/><circle cx="12" cy="12" r="3.5"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4V20"/>',
    "home": '<path d="M4 10L12 3L20 10V21H4Z M9 21V13H15V21"/>',
    "macros": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9H21M3 15H21M9 3V21M15 3V21"/>',
    "record": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3" fill="currentColor"/>',
    "play": '<path d="M7 4L20 12L7 20Z"/>',
    "click": '<path d="M6 3L19 13L13 14L10 21Z"/><path d="M16 4L18 2M20 8H23"/>',
    "edit": '<path d="M4 17L16 5L20 9L8 21H4Z M13 8L17 12"/>',
    "library": '<path d="M3 6H10L12 8H21V20H3Z M3 10H21"/>',
    "settings": '<path d="M4 6H20M4 12H20M4 18H20"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="10" cy="18" r="2"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "plus": '<path d="M12 5V19M5 12H19"/>',
    "pause": '<path d="M8 5V19M16 5V19"/>',
    "save": '<path d="M4 3H17L21 7V21H3V3Z M7 3V9H16V3M7 21V14H17V21"/>',
    "shield": '<path d="M12 3L20 6V12Q20 18 12 22Q4 18 4 12V6Z M8 12L11 15L16 9"/>',
    "trash": '<path d="M4 6H20M9 6V3H15V6M6 6L7 21H17L18 6M10 10V17M14 10V17"/>',
}


def icon(name, color="#b0b0b0"):
    body = PATHS.get(name, PATHS["plus"]).replace("currentColor", color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


DEFAULT_ACCENT = '#ff1744'


def accent_color(widget):
    while widget is not None:
        value = widget.property('accentColor')
        if value:
            return QColor(value)
        widget = widget.parentWidget()
    return QColor(DEFAULT_ACCENT)


def stylesheet(theme="dark", accent=DEFAULT_ACCENT):
    check = resource_path("check.svg").as_posix()
    down = resource_path("chevron-down.svg").as_posix()
    up = resource_path("chevron-up.svg").as_posix()
    dark = theme == "dark"
    bg, side, card, field = ("#000000", "#212225", "#000000", "#212225") if dark else ("#f5f5f5", "#e5e7eb", "#ffffff", "#e2e5ea")
    text, muted, border, hover = ("#ffffff", "#a0a0a5", "#37383d", "#2e2f32") if dark else ("#20242b", "#555b65", "#c3c7ce", "#d2d6de")
    selected = '#303238' if dark else '#dce1e9'
    track, handle = ('#343538', '#b5b5b7') if dark else ('#d7dae0', '#747b86')
    return f'''
        QWidget {{ color: {text}; font-family: "Inter"; font-size: 13px; font-weight:500; }}
        QLabel {{ font-weight:550; }}
        QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{ font-weight:600; }}
        QCheckBox, QRadioButton {{ font-weight:550; }}
        QMainWindow, QDialog, #pageRoot, #appRoot, #workspace {{ background: {bg}; }}
        QPushButton#sideBrand {{ font-size:30px; font-weight:800; background:transparent; border:0; padding:0 0 0 15px; text-align:left; text-decoration:none; }}
        QPushButton#sideBrand[collapsed="true"] {{ padding:0; text-align:center; }}
        #brandAccent {{ background:{accent}; }}
        #versionLabel {{ font-size:11px; color:{muted}; padding-left:14px; }}
        #sidebarStatus {{ color:{muted}; font-size:12px; }}
        #welcomeTitle {{ font-size:34px; font-weight:700; }}
        #welcomeSubtitle {{ color:{muted}; font-size:14px; font-weight:450; }}
        #homeMetric {{ font-size:44px; font-weight:600; }}
        #homeState {{ font-size:27px; font-weight:600; padding-top:12px; }}
        #divider {{ background:{border}; }}
        #emptyState {{ color:{muted}; padding:40px 12px; font-size:15px; }}
        #formError {{ color:{accent}; }}
        #currentAction {{ border:1px solid {border}; background:{card}; border-radius:8px; padding:24px; font-size:20px; }}
        #timer[recording="true"] {{ color:{accent}; }}
        QPushButton[choice="true"] {{ text-align:left; padding:16px 18px; font-weight:600; }}
        QPushButton[choice="true"]:checked {{ color:{accent}; background:{field}; font-weight:600; }}
        QPushButton[choice="true"]:checked:hover {{ background:{hover}; }}
        QTabWidget::pane {{ border:0; background:{bg}; }}
        QTabBar::tab {{ background:{side}; color:{muted}; padding:10px 18px; border:none; border-radius:18px; margin-right:6px; margin-bottom:8px; font-weight:600; }}
        QTabBar::tab:selected {{ color:{text}; font-weight:650; }}
        QTabBar::tab:hover {{ color:{text}; background:{hover}; }}
        QListView#sequenceView {{ background:{bg}; border:0; }}

        QToolTip {{ background: {card}; color: {text}; border: 1px solid {border}; padding: 6px; }}
        #sidebar {{ background: {side}; border: none; }}
        #brand {{ font-size: 24px; font-weight: 700; }}
        #eyebrow {{ color: {muted}; font-size: 11px; font-weight:600; }}
        #pageTitle {{ font-size: 28px; font-weight: 700; }}
        #sectionTitle {{ font-size: 17px; font-weight: 650; }}
        #muted {{ color: {muted}; font-weight:450; }}
        #metric {{ font-size: 34px; font-weight: 650; }}
        #timer {{ font-size:52px; font-weight:500; padding:16px 0; }}
        #consoleTimer {{ font-size: 48px; font-weight:500; padding:14px 0 0 0; }}
        #monogram {{ background:{field}; border-radius:7px; font-size:20px; font-weight:600; padding:4px 9px; }}
        #keycap {{ background:{field}; border:1px solid {border}; border-radius:6px; padding:5px 9px; font-size:12px; }}
        #card #currentAction {{ background:{field}; border-radius:8px; padding:14px; font-size:18px; font-weight:600; }}
        #card {{ background: {bg}; border:none; border-radius:0; }}
        #hero {{ background: {card}; border: 1px solid {border}; border-left: 4px solid {accent}; border-radius: 12px; }}
        #card QLabel, #hero QLabel {{ background: transparent; border: none; }}
        QPushButton {{ background: {field}; border: none; border-radius: 7px; padding: 9px 14px; font-weight:650; }}
        QPushButton:hover {{ background: {hover}; color:{text}; }}
        QPushButton:pressed, QPushButton:checked {{ background: {field}; color:{text}; }}
        QPushButton:checked:hover {{ background:{hover}; }}
        QPushButton:disabled {{ color: {muted}; background: {bg}; }}
        QPushButton[recordControl="true"]:disabled {{ color:{muted}; background:{field}; }}
        QPushButton[primary="true"] {{ background:{field}; color:{text}; }}
        QPushButton[primary="true"]:hover {{ background:{hover}; color:{text}; }}
        QPushButton[primary="true"]:disabled {{ background:{border}; color:{muted}; }}
        QPushButton[danger="true"] {{ color: {text}; }}
        QPushButton:focus {{ text-decoration:none; }}
        QPushButton[nav="true"] {{ text-align:left; border:none; border-left:3px solid transparent; border-radius:6px; padding:10px 12px; background:transparent; color:{muted}; font-weight:550; }}
        QPushButton[nav="true"]:hover {{ background: {hover}; }}
        QPushButton[nav="true"]:checked {{ background:{field}; color:{text}; border-left:3px solid {accent}; font-weight:650; }}
        QPushButton[nav="true"]:checked:hover {{ background:{hover}; }}
        QPushButton[nav="true"][collapsed="true"] {{ text-align:center; padding:0; }}
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{ background: {field}; border: none; border-radius: 6px; padding: 7px 9px; selection-background-color: {accent}; }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: none; }}
        QLineEdit:enabled:hover, QSpinBox:enabled:hover, QDoubleSpinBox:enabled:hover, QComboBox:enabled:hover, QPlainTextEdit:enabled:hover {{ background:{hover}; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox {{ border:2px solid transparent; padding:5px 7px; font-weight:650; font-size:14px; }}
        QComboBox:focus {{ border:2px solid transparent; }}
        QComboBox:on {{ border:2px solid {'#f4f4f5' if dark else '#686e78'}; background:{hover}; }}
        QComboBox::down-arrow {{ image:url("{down}"); width:10px; height:10px; }}
        QComboBox::down-arrow:on {{ image:url("{up}"); }}
        QSpinBox, QDoubleSpinBox {{ padding:7px 4px 7px 9px; }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{ width:30px; height:18px; border:0; subcontrol-origin:border; subcontrol-position:top right; }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{ width:30px; height:18px; border:0; subcontrol-origin:border; subcontrol-position:bottom right; }}
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background:{hover}; border-radius:4px; }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image:url("{up}"); width:13px; height:13px; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image:url("{down}"); width:13px; height:13px; }}
        QComboBox QAbstractItemView {{ background: {field}; color:{text}; selection-background-color: {hover}; selection-color:{text}; border:none; outline:none; padding:4px 0; font-weight:650; font-size:14px; }}
        QComboBox QAbstractItemView::item {{ min-height:38px; padding:3px 12px; margin:2px 4px; border:none; border-radius:6px; }}
        QComboBox QAbstractItemView::item:selected {{ background:{hover}; color:{text}; font-weight:650; }}
        QComboBox QAbstractItemView::item:hover {{ background:{hover}; color:{text}; }}
        #categorySuggestions {{ background:{field}; color:{text}; border:0; outline:0; padding:4px 0; font-size:14px; font-weight:650; }}
        #categorySuggestions::item {{ min-height:34px; padding:3px 12px; margin:2px 4px; border:0; border-radius:6px; }}
        #categorySuggestions::item:selected, #categorySuggestions::item:hover {{ background:{hover}; color:{text}; }}
        QCheckBox {{ spacing: 9px; }}
        QCheckBox::indicator {{ width: 17px; height: 17px; border: none; border-radius: 4px; background: {field}; }}
        QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image:url("{check}"); }}
        QCheckBox::indicator:unchecked:hover {{ background:{hover}; }}
        QTableView, QListWidget {{ background: {card}; alternate-background-color: {field}; border: 1px solid {border}; border-radius: 8px; gridline-color: {border}; selection-background-color: {hover}; selection-color: {text}; }}
        QTableView::item {{ padding: 7px; border: none; }}
        QTableView::item:selected {{ background: {hover}; color: {text}; border:none; }}
        QTableView#libraryTable {{ background:{card}; alternate-background-color:{'#141517' if dark else '#f0f2f5'}; border:1px solid {border}; border-radius:8px; outline:0; }}
        QTableView#libraryTable::item {{ padding:9px 12px; border:0; }}
        QTableView#libraryTable::item:hover {{ background:{hover}; }}
        QTableView#libraryTable::item:selected {{ background:{selected}; color:{text}; border:0; }}
        QTableView#libraryTable QHeaderView::section {{ background:{field}; color:{muted}; padding:12px; border:0; font-weight:650; }}
        QTableView#libraryTable QScrollBar:horizontal {{ margin:0 10px; }}
        QHeaderView::section {{ background: {field}; color: {muted}; padding: 10px; border: none; border-bottom: 1px solid {border}; font-weight: 600; }}
        QTableCornerButton::section {{ background: {field}; border: none; }}
        QProgressBar {{ border: none; border-radius: 4px; background: {border}; min-height: 7px; max-height: 7px; }}
        QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: {track}; width: 4px; margin: 0; border:none; }}
        QScrollBar::handle:vertical {{ background: {handle}; min-height: 28px; border-radius: 2px; }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed {{ background: #dedee0; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ background: {track}; height: 4px; margin:0; border:none; }}
        QScrollBar::handle:horizontal {{ background: {handle}; min-width: 28px; border-radius: 2px; }}
        QScrollBar::handle:horizontal:hover, QScrollBar::handle:horizontal:pressed {{ background: #dedee0; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QScrollBar::up-arrow, QScrollBar::down-arrow, QScrollBar::left-arrow, QScrollBar::right-arrow {{ width:0; height:0; background:none; }}
        QStatusBar {{ background: {side}; color: {muted}; border-top: 1px solid {border}; }}
        QMenu {{ background: {card}; border: none; padding: 5px; }}
        QMenu::item {{ padding: 7px 20px; }}
        QMenu::item:selected {{ background: {hover}; }}
        #statusBadge {{ border: 1px solid {border}; border-radius: 14px; padding: 6px 12px; color: {muted}; }}
        #notice {{ background: {field}; border: 1px solid {border}; border-radius: 8px; padding: 12px; color: {muted}; }}
        #noticeOverlay {{ background:{field}; border:1px solid {border}; border-radius:8px; color:{text}; }}
        #noticeOverlay QLabel {{ color:{text}; background:transparent; }}
        QPushButton#noticeDismiss {{ padding:0; border:0; border-radius:5px; background:transparent; color:{text}; font-size:18px; }}
        QPushButton#noticeDismiss:hover {{ background:{hover}; }}
        QSplitter::handle {{ background: {border}; }}
    '''
