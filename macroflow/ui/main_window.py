from __future__ import annotations
from ..i18n import tr

import copy
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPropertyAnimation, QVariantAnimation, QEasingCurve, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QColorDialog, QDialog, QFileDialog,
                               QFormLayout, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar, QScrollArea, QStackedWidget, QFrame, QTabWidget,
                               QTableWidget, QTableWidgetItem, QToolTip, QSizePolicy, QVBoxLayout, QWidget, QSystemTrayIcon, QMenu)

from .. import __version__
from ..config import DEFAULTS, HOTKEY_LABELS, Settings
from ..engine import Engine
from ..hotkeys import GlobalHotkeys, reserved_keys
from ..models import ClickOptions, Macro, ValidationError, interval_seconds, now_iso
from ..persistence import SaveService
from ..recording import PositionPicker
from ..storage import Library
from ..triggers import InputRouter, check_os_binding, parse_binding, validate_bindings
from ..windows import InputTarget, application_windows, foreground_process, monitor_rects, point_on_screen
from .dialogs import AssignDialog, CreateMacroDialog, MacroDialog, ShortcutField
from .capture import KeyCaptureDialog
from .home import Home
from .playback_panel import PlaybackPanel
from .recording_indicator import RecordingIndicator
from .notice import Notice
from .color_picker import ColorDialog
from .scrolling import install_smooth_scrolling
from .restrictions import RecordingRestrictions
from ..triggers import display_binding, excluded_key_codes, keyboard_layout
from .editor import Editor
from .theme import icon, stylesheet
from .widgets import BrandButton, NavigationButton, LibraryDelegate, LibraryTable, LockSwitch, ThemedButton, button, card, combo, duration_text, label, row, spin

MODE_LABELS = {"once": tr('Single press'), "hold": tr('Hold'), "toggle": tr('Toggle')}


class Bridge(QObject):
    activation = Signal(object)
    event = Signal(str, object)
    hotkey = Signal(str, str)
    position = Signal(int, int)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, enable_hooks=True):
        super().__init__()
        install_smooth_scrolling()
        self.settings = settings
        self.enable_hooks = enable_hooks
        self.exit_requested = False
        self.tray = None
        self.setWindowTitle("Nexo")
        self.setMinimumSize(980, 680)
        self.resize(*[int(v) for v in settings.data["window_size"]])
        self.bridge = Bridge()
        self.bridge.event.connect(self.on_engine_event)
        self.bridge.hotkey.connect(self.on_hotkey)
        self.bridge.position.connect(self.position_selected)
        self.engine = Engine(self.bridge.event.emit)
        self.engine.activation_request = self.request_target_activation
        self.bridge.activation.connect(self.perform_target_activation)
        self.engine.policy = settings.data["concurrency"]
        self.library = Library(settings.macro_folder)
        self.macros = {macro.id: macro for macro in self.library.all()}
        self.writer = SaveService(self.library, self.bridge.event.emit)
        self.recovery_writer = SaveService(Library(settings.directory / "recovery" / "recordings"),
                                           lambda name, data: self.bridge.event.emit(name, data) if name == "warning" else None)
        self.closed = False
        self.router = InputRouter(self.route_hotkey, lambda: not self.picking and self.engine.task != "record" and foreground_process() != os.getpid())
        self.hotkeys = GlobalHotkeys(self.native_hotkey)
        self.native_registration_ready = False
        self.native_registration_signature = None
        QApplication.instance().applicationStateChanged.connect(self.native_focus_changed)
        self.hotkeys_ok = not enable_hooks
        self.router_ok = not enable_hooks
        self.picking = False
        self.hold_control = None
        self.picker = None
        self.current = self.macros.get(settings.data["last_macro"]) or next(iter(self.macros.values()), None)
        self.record_target = None
        self.loading = False
        self.last_checkpoint = 0
        self.record_indicator = RecordingIndicator()
        self.record_indicator.stop_requested.connect(self.stop_recording_indicator)
        self.record_indicator.pause_requested.connect(self.pause_task)
        self.playback_panel = PlaybackPanel()
        self.playback_panel.pause_requested.connect(self.pause_task)
        self.playback_panel.stop_requested.connect(self.stop_task)
        self.playback_panel.previous_requested.connect(lambda: self.engine.seek(-1))
        self.playback_panel.next_requested.connect(lambda: self.engine.seek(1))
        self.playback_panel.restart_requested.connect(lambda: self.engine.seek(restart=True))
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(650)
        self.autosave_timer.timeout.connect(self.save_current)
        self.build_ui()
        self.apply_theme()
        self.notice = Notice(self)
        self.statusBar().messageChanged.connect(self.show_notice)
        self.refresh_library()
        if self.current:
            self.load_macro(self.current.id)
        self.refresh_current()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.sync_state()
        self.change_page(0)
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(self.save_current)
        self.sidebar_shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.sidebar_shortcut.activated.connect(self.toggle_sidebar)
        self.set_sidebar_collapsed(self.settings.data["sidebar_collapsed"], animate=False)
        QTimer.singleShot(0, self.start_hooks)

    def build_ui(self):
        central = QWidget()
        central.setObjectName("appRoot")
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(186)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(15, 32, 15, 22)
        side.setSpacing(12)
        brand = BrandButton(self.toggle_sidebar)
        brand.setObjectName("sideBrand")
        self.side_brand = brand
        brand.setFixedHeight(32)
        side.addWidget(brand)
        mark = QFrame()
        mark.setObjectName("brandAccent")
        mark.setFixedSize(27, 2)
        marker = row(mark, None)
        self.brand_marker = marker
        marker_policy = marker.sizePolicy()
        marker_policy.setRetainSizeWhenHidden(True)
        marker.setSizePolicy(marker_policy)
        marker.layout().setContentsMargins(15, 5, 0, 0)
        side.addWidget(marker)
        side.addSpacing(34)
        self.page_names = [tr('Home'), tr('Record'), "Macros", "Autoclicker", "Editor", tr('Library'), tr('Settings')]
        symbols = ["home", "record", "macros", "click", "edit", "library", "settings"]
        self.nav = []
        for index, (name, symbol) in enumerate(zip(self.page_names, symbols)):
            item = NavigationButton(name, lambda checked=False, i=index: self.change_page(i), symbol)
            item.setProperty("nav", True)
            item.setToolTip(name)
            item.setAccessibleName(name)
            item.setCheckable(True)
            item.setFixedHeight(42)
            self.nav.append(item)
        for index in (0, 1, 2, 4, 5, 6):
            side.addWidget(self.nav[index])
        side.addWidget(self.nav[3])
        side.addStretch()
        self.status_badge = label(tr('Ready'), "sidebarStatus")
        self.status_badge.setWordWrap(True)
        self.stop_all = button(tr('Stop all'), self.emergency, symbol="stop")
        self.stop_all.setToolTip(tr('Emergency stop: stops tasks and releases held inputs'))
        self.emergency_label = label(display_binding(self.settings.data["hotkeys"]["emergency"]), "eyebrow")
        side.addWidget(self.status_badge)
        self.status_badge.hide()
        self.stop_all.hide()
        self.emergency_label.hide()
        side.addSpacing(10)
        self.lock_switch = LockSwitch(self.set_automation_locked)
        side.addWidget(self.lock_switch)
        self.version_label = label("Nexo  " + __version__, "versionLabel")
        side.addWidget(self.version_label)
        outer.addWidget(self.sidebar)
        self.workspace = QWidget()
        self.workspace.setObjectName("workspace")
        content = QVBoxLayout(self.workspace)
        content.setContentsMargins(52, 42, 52, 28)
        content.setSpacing(18)
        self.breadcrumb = label(tr('NEXO  /  HOME'), "eyebrow")
        self.breadcrumb.setParent(self.workspace)
        self.breadcrumb.hide()
        self.title = label(tr('Home'), "pageTitle")
        self.subtitle = label("", "muted", True)
        content.addWidget(self.title)
        content.addWidget(self.subtitle)
        self.current_combo = combo([])
        self.current_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.current_combo.setMinimumContentsLength(18)
        self.current_combo.setMinimumWidth(160)
        self.current_combo.setMaximumWidth(320)
        self.current_combo.activated.connect(lambda i: self.select_macro(self.current_combo.itemData(i)))
        self.new_button = button(tr('New'), self.new_macro, symbol="plus")
        self.save_button = button(tr('Save'), self.save_current, symbol="save")
        self.config_macro_button = button(tr('Configure'), self.configure_macro, symbol="settings")
        self.macro_toolbar = row(self.current_combo, None, self.new_button, self.config_macro_button, self.save_button)
        content.addWidget(self.macro_toolbar)
        self.target_combo = combo([(tr('Entire screen · global input'), None)])
        self.target_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.target_combo.setMinimumContentsLength(28)
        self.target_combo.setMaximumWidth(420)
        self.target_combo.currentIndexChanged.connect(self.select_input_target)
        self.target_refresh = button(tr('Refresh windows'), self.refresh_targets)
        self.target_label = label(tr('Target'), "muted")
        self.target_row = row(self.target_label, self.target_combo, self.target_refresh, None)
        self.target_row.setToolTip(tr('Choose a window for playback and the autoclicker; set the input mode below.'))
        content.addWidget(self.target_row)
        self.target_delivery = combo([(tr('Background · Windows messages'), "background"),
                                      (tr('Focused · compatibility'), "foreground"),
                                      (tr('Activate window · bring to front'), "activate")])
        self.target_delivery.currentIndexChanged.connect(self.select_input_target)
        self.target_note = label("", "muted", True)
        self.target_options = row(self.target_delivery, self.target_note)
        content.addWidget(self.target_options)
        self.refresh_targets()
        self.pages = QStackedWidget()
        content.addWidget(self.pages, 1)
        outer.addWidget(self.workspace, 1)
        self.build_dashboard()
        self.build_recorder()
        self.build_player()
        self.build_clicker()
        self.build_editor()
        self.build_library()
        self.build_settings()
        self.capture_dialog = KeyCaptureDialog(self, self.stop_task)
        self.record_mode.currentIndexChanged.connect(self.update_record_options)
        self.click_kind.currentIndexChanged.connect(self.update_click_options)
        self.update_record_options()
        self.update_click_options()
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage(tr('Ready · Autosave enabled'))
        self.statusBar().hide()

    def refresh_targets(self):
        previous = self.target_combo.currentData()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItem(tr('Entire screen · global input'), None)
        for hwnd, pid, title in application_windows():
            self.target_combo.addItem(title, (hwnd, pid))
        index = self.target_combo.findData(previous)
        if previous is not None and index < 0:
            self.target_combo.addItem(tr('Window closed · choose another target'), previous)
            index = self.target_combo.count() - 1
        self.target_combo.setCurrentIndex(max(0, index))
        self.target_combo.blockSignals(False)
        self.select_input_target()

    def select_input_target(self):
        target = self.target_combo.currentData()
        self.engine.input_target = InputTarget(*target) if target else None
        self.engine.input_delivery = self.target_delivery.currentData()
        background = self.engine.input_delivery == "background"
        self.target_note.setText(tr('If Background mode does not work, this mode restores the window and brings it to the front before running. It must stay active; switching windows stops playback.') if self.engine.input_delivery == "activate" else tr('Keeps your current window active. Some apps and games ignore these messages.') if background else
                                 tr('The target must be in front. Switching windows stops playback.'))
        self.target_note.setMinimumHeight(self.target_note.fontMetrics().lineSpacing() * 5 if self.engine.input_delivery == "activate" else 0)
        self.target_options.setMinimumHeight(self.target_note.minimumHeight())
        self.target_note.setToolTip(self.target_note.text())
        if getattr(self, "native_registration_ready", False):
            self.sync_native_macros()
        if hasattr(self, "pages"):
            self.target_options.setVisible(bool(target) and self.pages.currentIndex() in (2, 3))
        else:
            self.target_options.hide()

    def page(self, scroll=True):
        page = QWidget()
        page.setObjectName("pageRoot")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 3, 0, 6)
        layout.setSpacing(17)
        if scroll:
            wrapper = QScrollArea()
            wrapper.setWidgetResizable(True)
            wrapper.setWidget(page)
            self.pages.addWidget(wrapper)
        else:
            self.pages.addWidget(page)
        return page, layout

    def build_dashboard(self):
        _, layout = self.page()
        self.home = Home(self)
        layout.addWidget(self.home, 1)

    def build_recorder(self):
        _, layout = self.page()
        layout.setSpacing(12)
        overview = QGridLayout()
        overview.setHorizontalSpacing(28)
        overview.setColumnStretch(0, 1)
        overview.setColumnStretch(1, 1)
        summary = QWidget()
        summary.setMinimumHeight(150)
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(0, 8, 0, 8)
        summary_layout.setSpacing(8)
        self.record_target_label = label(tr('Select a macro to record.'), "muted", True)
        self.record_target_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.record_target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_layout.addWidget(self.record_target_label)
        summary_layout.addStretch()
        self.record_timer = label("00:00:00.000", "timer")
        self.record_timer.setStyleSheet("font-size:40px; padding:6px 0;")
        self.record_timer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_count = label(tr('0 recorded events'), "muted")
        self.record_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_layout.addWidget(self.record_timer)
        summary_layout.addWidget(self.record_count)
        summary_layout.addStretch()
        overview.addWidget(summary, 0, 0)
        capture = QWidget()
        capture_layout = QVBoxLayout(capture)
        capture_layout.setContentsMargins(0, 8, 0, 8)
        capture_layout.setSpacing(8)
        capture_layout.addWidget(label(tr('CAPTURE MODE'), "eyebrow"))
        self.record_mode = combo([(tr('Real time · keyboard and mouse'), "timed"), (tr('Keystrokes · fixed interval'), "fixed")])
        self.record_mode.setCurrentIndex(self.record_mode.findData(self.settings.data["record_mode"]))
        capture_layout.addWidget(self.record_mode)
        self.record_options = QWidget()
        form = QFormLayout(self.record_options)
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(8)
        self.fixed_interval = spin(0.01, 86400, self.settings.data["fixed_interval"], " s", 3)
        self.fixed_interval_row = row(self.fixed_interval)
        form.addRow(tr('Fixed interval'), self.fixed_interval_row)
        self.fixed_interval_label = form.labelForField(self.fixed_interval_row)
        self.capture_moves = QCheckBox(tr('Include cursor movements'))
        self.capture_moves.setChecked(self.settings.data["capture_moves"])
        form.addRow(self.capture_moves)
        self.record_countdown = spin(0, 30, self.settings.data["countdown"], " s")
        self.record_countdown_row = row(self.record_countdown)
        form.addRow(tr('Countdown'), self.record_countdown_row)
        self.record_countdown_label = form.labelForField(self.record_countdown_row)
        capture_layout.addWidget(self.record_options)
        capture_layout.addStretch()
        overview.addWidget(capture, 0, 1)
        layout.addLayout(overview)
        self.record_start = button(tr('Start recording'), self.start_recording, symbol="record", primary=True)
        self.record_pause = button(tr('Pause'), self.pause_task, symbol="pause")
        self.record_stop = button(tr('Finish and save'), self.stop_task, symbol="stop")
        controls = QHBoxLayout()
        controls.setSpacing(12)
        for control in (self.record_start, self.record_pause, self.record_stop):
            control.setProperty("recordControl", True)
            controls.addWidget(control, 1)
        layout.addLayout(controls)
        self.record_privacy = label(tr('Control shortcuts and clicks inside Nexo are excluded.'), "muted", True)
        self.record_privacy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.record_privacy)
        layout.addSpacing(8)
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addWidget(row(label(tr('RECORDING SHORTCUTS'), "eyebrow"), None,
                             button(tr('Edit shortcuts'), lambda: self.open_settings_tab(1), symbol="settings")))
        self.record_hotkey_fields = {}
        shortcuts = QGridLayout()
        shortcuts.setHorizontalSpacing(12)
        shortcuts.setVerticalSpacing(6)
        for column, (action, caption) in enumerate((("record_start", tr('Start')), ("record_pause", tr('Pause')), ("record_stop", tr('Stop')))):
            field = ShortcutField(self.settings.data["hotkeys"][action])
            self.record_hotkey_fields[action] = field
            field.setToolTip(HOTKEY_LABELS[action])
            shortcuts.addWidget(label(caption, "eyebrow"), 0, column)
            shortcuts.addWidget(field, 1, column)
            shortcuts.setColumnStretch(column, 1)
        layout.addLayout(shortcuts)
        layout.addStretch()

    def update_record_options(self):
        fixed = self.record_mode.currentData() == "fixed"
        self.fixed_interval_row.setVisible(fixed)
        self.fixed_interval_label.setVisible(fixed)
        self.capture_moves.setVisible(not fixed)
        self.capture_moves.setEnabled(not fixed and not self.engine.busy)
        self.record_countdown_row.setVisible(not fixed)
        self.record_countdown_label.setVisible(not fixed)

    def update_click_options(self):
        keyboard = self.click_kind.currentData() == "keyboard"
        self.click_kind.setEnabled(not self.engine.busy)
        self.keyboard_hold_button.setEnabled(not self.engine.busy)
        for field in getattr(self, "click_ignored_modifiers", {}).values():
            field.setEnabled(not self.engine.busy)
        self.keyboard_hold_row.setEnabled(not self.engine.busy)
        for widget in (self.keyboard_hold_row, self.keyboard_hold_label, self.keyboard_hold_hint):
            widget.setVisible(keyboard)
        for field in (self.click_button, self.click_double, self.click_position, self.click_x, self.click_y, self.pick_button):
            field.setEnabled(not keyboard and not self.engine.busy)
        self.repeat_key.setEnabled(keyboard and not self.engine.busy)
        self.repeat_key_button.setEnabled(keyboard and not self.engine.busy)
        for widget in (self.click_key_row, self.click_key_label):
            widget.setVisible(keyboard)
        for widget in (self.click_mouse_row, self.click_mouse_label, self.click_position, self.click_position_label):
            widget.setVisible(not keyboard)
        fixed = not keyboard and self.click_position.currentData() == "fixed"
        self.coordinates_row.setVisible(fixed)
        self.coordinates_label.setVisible(fixed)

    def open_settings_tab(self, index):
        self.change_page(6)
        self.settings_tabs.setCurrentIndex(index)

    def build_player(self):
        _, layout = self.page()
        layout.setSpacing(10)
        surface = QWidget()
        surface.setObjectName("pageRoot")
        detail = QVBoxLayout(surface)
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(8)
        layout.addWidget(surface)
        self.player_name = label(tr('Select a macro'), "sectionTitle", True)
        self.player_meta = label("", "muted", True)
        for item in (self.player_name, self.player_meta):
            item.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        detail.addWidget(self.player_name)
        detail.addWidget(self.player_meta)
        self.player_action = label(tr('No actions'), "currentAction", True)
        self.player_action.setStyleSheet("font-size:17px; padding:12px;")
        self.player_action.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        detail.addWidget(self.player_action)
        help_text = (tr("<qt><table width='320' cellspacing='0' cellpadding='0'><tr><td><b>Reading the sequence</b><br><br>The number shows the action's position.<br>Press and Release are separate actions.<br>Up means the up arrow key.<br><br>The bar below shows completed actions.</td></tr></table></qt>"))
        self.player_action.setToolTip(help_text)
        help_button = button("?")
        help_button.setFixedWidth(32)
        help_button.setAccessibleName(tr('Player help'))
        help_button.setToolTip(help_text)
        help_button.clicked.connect(lambda: QToolTip.showText(help_button.mapToGlobal(help_button.rect().bottomLeft()), help_text, help_button))
        self.macro_toggle = button(tr('Enable shortcut'), self.toggle_current_macro)
        options = QWidget()
        form = QFormLayout(options)
        form.setContentsMargins(0, 8, 12, 8)
        form.setVerticalSpacing(12)
        self.play_speed = spin(0.1, 10, self.settings.data["speed"], "×", 2)
        self.play_repetitions = spin(1, 10_000_000, 1)
        self.play_continuous = QCheckBox(tr('Repeat until stopped'))
        self.play_continuous.toggled.connect(lambda checked: self.play_repetitions.setEnabled(not checked))
        self.play_countdown = spin(0, 30, self.settings.data["countdown"], " s")
        form.addRow(tr('Speed'), self.play_speed)
        form.addRow(tr('Repeats'), row(self.play_repetitions, self.play_continuous, None))
        form.addRow(tr('Countdown'), self.play_countdown)
        self.play_options_toggle = button(tr('Playback options'))
        self.play_options_toggle.setCheckable(True)
        self.play_options_toggle.toggled.connect(options.setVisible)
        detail.addWidget(row(button(tr('Edit sequence'), lambda: self.change_page(4), symbol="edit"),
                             self.macro_toggle, self.play_options_toggle, help_button, None))
        detail.addWidget(options)
        options.hide()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setToolTip(tr('Action progress for the current repeat'))
        layout.addWidget(self.progress)
        self.play_progress = label(tr('Nothing playing'), "muted", True)
        layout.addWidget(self.play_progress)
        self.play_start = button(tr('Play'), self.start_playback, symbol="play", primary=True)
        self.play_pause = button(tr('Pause'), self.pause_task, symbol="pause")
        self.play_stop = button(tr('Stop'), self.stop_task, symbol="stop")
        previous = button("‹", lambda: self.engine.seek(-1))
        following = button("›", lambda: self.engine.seek(1))
        for control, name in ((previous, tr('Previous action')), (following, tr('Next action'))):
            control.setFixedWidth(34)
            control.setAccessibleName(name)
            control.setToolTip(name)
        self.play_navigation = row(previous, following,
                                   button(tr('Restart'), lambda: self.engine.seek(restart=True)), None)
        layout.addWidget(row(self.play_start, self.play_pause, self.play_stop, self.play_navigation, None))
        self.queue_label = label(tr('Queue empty'), "muted")
        layout.addWidget(row(self.queue_label, None, button(tr('Clear queue'), self.clear_queue)))
        layout.addStretch()

    def build_clicker(self):
        _, layout = self.page(False)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.tabBar().setDrawBase(False)
        layout.addWidget(tabs, 1)
        def tab(title):
            widget = QWidget()
            widget.setObjectName("pageRoot")
            form = QFormLayout(widget)
            form.setContentsMargins(6, 24, 14, 24)
            form.setVerticalSpacing(18)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            tabs.addTab(scroll, title)
            return form
        form = tab(tr('Action'))
        self.click_kind = combo([(tr('Mouse'), "mouse"), (tr('Keyboard'), "keyboard")])
        self.repeat_key = ShortcutField("V")
        self.repeat_key_button = button(tr('Assign key'), lambda: self.assign_record_control(self.repeat_key))
        form.addRow(tr('Device'), self.click_kind)
        self.click_key_row = row(self.repeat_key, self.repeat_key_button)
        form.addRow(tr('Key to repeat'), self.click_key_row)
        self.click_key_label = form.labelForField(self.click_key_row)
        self.keyboard_hold_button = ShortcutField()
        self.keyboard_hold_button.setPlaceholderText(tr('Not assigned'))
        self.keyboard_hold_assign = button(tr('Assign'), self.assign_hold_binding)
        self.keyboard_hold_clear = button(tr('Remove'), lambda: self.keyboard_hold_button.setText(''))
        self.keyboard_hold_row = row(self.keyboard_hold_button, self.keyboard_hold_assign, self.keyboard_hold_clear)
        form.addRow(tr('Hold to repeat'), self.keyboard_hold_row)
        self.keyboard_hold_label = form.labelForField(self.keyboard_hold_row)
        self.keyboard_hold_hint = label(tr('Hold the assigned key, combination or mouse button to repeat. Release it to stop. Starts without a countdown and follows the interval and limits.'), 'muted', True)
        form.addRow(self.keyboard_hold_hint)
        self.click_button = combo([(tr('Left'), "left"), (tr('Right'), "right"), (tr('Middle'), "middle"), (tr('Side button X1'), "x1"), (tr('Side button X2'), "x2")])
        self.click_double = QCheckBox(tr('Double-click'))
        self.click_mouse_row = row(self.click_button, self.click_double, None)
        form.addRow(tr('Button'), self.click_mouse_row)
        self.click_mouse_label = form.labelForField(self.click_mouse_row)
        self.click_position = combo([(tr('Current cursor position'), "current"), (tr('Custom coordinates'), "fixed")])
        form.addRow(tr('Position'), self.click_position)
        self.click_position_label = form.labelForField(self.click_position)
        self.click_x, self.click_y = spin(-1_000_000, 1_000_000, 0), spin(-1_000_000, 1_000_000, 0)
        self.pick_button = button(tr('Pick on screen'), self.pick_position)
        self.coordinates_row = row(self.click_x, self.click_y, self.pick_button)
        form.addRow("X / Y", self.coordinates_row)
        self.coordinates_label = form.labelForField(self.coordinates_row)
        self.click_position.currentIndexChanged.connect(self.update_click_options)
        form = tab(tr('Intervals and limits'))
        self.interval_hours, self.interval_minutes, self.interval_seconds, self.interval_ms = spin(0, 24, 0, " h"), spin(0, 59, 0, " min"), spin(0, 59, 0, " s"), spin(0, 999, 100, " ms")
        form.addRow(tr('Interval'), row(self.interval_hours, self.interval_minutes, self.interval_seconds, self.interval_ms))
        self.variable_interval = QCheckBox(tr('Random interval up to'))
        self.interval_max = spin(0.001, 90000, 0.5, " s", 3)
        form.addRow(tr('Variation'), row(self.variable_interval, self.interval_max))
        self.click_repetitions = spin(1, 10_000_000, 100)
        self.click_infinite = QCheckBox(tr('Unlimited'))
        self.click_infinite.toggled.connect(lambda checked: self.click_repetitions.setEnabled(not checked))
        form.addRow(tr('Repeats'), row(self.click_repetitions, self.click_infinite, None))
        self.click_duration = spin(0, 604800, 0, " s", 2)
        form.addRow(tr('Maximum duration'), self.click_duration)
        self.click_duration.setToolTip(tr('0 = no time limit'))
        self.click_countdown = spin(0, 30, self.settings.data["countdown"], " s")
        form.addRow(tr('Countdown'), self.click_countdown)
        form.addRow(label(tr('Minimum interval: 1 ms. Actual timing depends on the system and target. Duration 0 = unlimited.'), "muted", True))
        form = tab(tr('Exclusions'))
        form.addRow(label(tr('Ignore trigger modifiers'), "sectionTitle"))
        form.addRow(label(tr('Applies to Hold to repeat in Keyboard mode. You can use these keys while holding the trigger without changing the combination or stopping repeats. It does not block those keys in the game or change other shortcuts.'), "muted", True))
        self.click_ignored_modifiers = {}
        for modifier, title in (("ctrl", "Ctrl"), ("alt", "Alt"), ("shift", "Shift"), ("win", "Windows")):
            checkbox = QCheckBox(title)
            self.click_ignored_modifiers[modifier] = checkbox
            form.addRow(checkbox)
        form.addRow(label(tr('Modifiers explicitly included in the trigger are still required. Other exact shortcuts take priority.'), "muted", True))
        self.click_stats = label(tr('0 repeats'), "muted")
        layout.addWidget(self.click_stats)
        self.click_start = button(tr('Start'), self.start_clicker, symbol="play", primary=True)
        self.click_stop = button(tr('Stop'), self.stop_task, symbol="stop")
        layout.addWidget(row(self.click_start, self.click_stop, None))
        self.clicker_fields = {"kind": self.click_kind, "button": self.click_button, "double": self.click_double,
                               "position": self.click_position, "x": self.click_x, "y": self.click_y, "key": self.repeat_key,
                               "hours": self.interval_hours, "minutes": self.interval_minutes, "seconds": self.interval_seconds,
                               "milliseconds": self.interval_ms, "variable": self.variable_interval, "interval_max": self.interval_max,
                               "repetitions": self.click_repetitions, "infinite": self.click_infinite, "duration": self.click_duration,
                               "countdown": self.click_countdown, 'hold_button': self.keyboard_hold_button}
        self.clicker_fields.update({"ignore_" + name: field for name, field in self.click_ignored_modifiers.items()})
        saved_clicker = copy.deepcopy(self.settings.data["clicker"])
        for name, field in self.clicker_fields.items():
            value = saved_clicker[name]
            if isinstance(field, QComboBox):
                field.setCurrentIndex(field.findData(value))
                signal = field.currentIndexChanged
            elif isinstance(field, QCheckBox):
                field.setChecked(value)
                signal = field.toggled
            elif isinstance(field, QLineEdit):
                field.setText(value)
                signal = field.textChanged
            else:
                field.setValue(value)
                signal = field.valueChanged
            signal.connect(self.cache_clicker_settings)
        self.cache_clicker_settings()
        for field in self.click_ignored_modifiers.values():
            field.toggled.connect(self.update_hold_binding)
        self.keyboard_hold_button.textChanged.connect(self.update_hold_binding)
        self.click_kind.currentIndexChanged.connect(self.update_hold_binding)

    def cache_clicker_settings(self, *args):
        values = {}
        for name, field in self.clicker_fields.items():
            if isinstance(field, QComboBox):
                values[name] = field.currentData()
            elif isinstance(field, QCheckBox):
                values[name] = field.isChecked()
            elif isinstance(field, QLineEdit):
                values[name] = field.text()
            else:
                values[name] = field.value()
        self.settings.data["clicker"] = values

    def router_controls(self, hotkeys=None):
        controls = dict(hotkeys or self.settings.data['hotkeys'])
        clicker = self.settings.data['clicker']
        if clicker['kind'] == 'keyboard' and clicker['hold_button']:
            controls['keyboard_repeat_press'] = parse_binding(clicker['hold_button']).label
        return controls

    def update_hold_binding(self, *args):
        if self.hold_control is not None and self.hold_control is self.engine.control:
            self.engine.stop()
            self.hold_control = None
        try:
            self.configure_router(self.macros.values(), self.router_controls())
        except ValidationError as exc:
            self.keyboard_hold_button.setText('')
            self.show_notice(str(exc) + tr(' Assign a different hold trigger.'), warning=True)

    def assign_hold_binding(self):
        if not self.require_idle():
            return
        dialog = AssignDialog(self.router, self, allow_all_mouse=True)
        if dialog.exec() and dialog.value:
            self.keyboard_hold_button.setText(dialog.value)

    def build_editor(self):
        _, layout = self.page(False)
        self.macro_summary = label(tr('Create a macro to get started.'), "muted", True)
        layout.addWidget(self.macro_summary)
        self.editor = Editor()
        self.editor.model.changed.connect(self.events_changed)
        layout.addWidget(self.editor, 1)
        self.play_selection = button(tr('Play selection'), lambda: self.start_playback(True), symbol="play")
        layout.addWidget(row(label(tr('Time = delay before each action.'), "muted"), None, self.play_selection))

    def style_table(self, table):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(44)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def build_library(self):
        _, layout = self.page(False)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Search by name, shortcut or category…'))
        self.category_filter = combo([(tr('All categories'), "")])
        self.search.textChanged.connect(self.filter_library)
        self.category_filter.currentIndexChanged.connect(self.filter_library)
        layout.addWidget(row(self.search, self.category_filter))
        self.library_table = LibraryTable(0, 9)
        self.library_table.setMouseTracking(True)
        self.library_table.setObjectName('libraryTable')
        self.library_table.setItemDelegate(LibraryDelegate(self.library_table))
        self.library_table.setHorizontalHeaderLabels([tr('Name'), tr('Shortcut'), tr('Mode'), tr('Duration'), tr('Actions'), tr('Status'), tr('Category'), tr('Modified'), "ID"])
        self.library_table.setColumnHidden(8, True)
        self.style_table(self.library_table)
        self.library_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.library_table.setColumnWidth(0, 230)
        self.library_table.horizontalHeader().setStretchLastSection(False)
        self.library_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.library_table.cellDoubleClicked.connect(lambda r, c: self.open_library_selection())
        layout.addWidget(self.library_table, 1)
        self.library_actions = row(button(tr('Edit'), self.open_library_selection), button(tr('View in Macros'), self.open_library_player),
                                   button(tr('Duplicate'), self.duplicate_macro), button(tr('Delete'), self.delete_macro, danger=True), None)
        layout.addWidget(self.library_actions)
        layout.addWidget(row(button(tr('Import JSON'), self.import_macro), button(tr('Export JSON'), self.export_macro), None,
                              button(tr('Open folder'), self.open_macro_folder)))
        self.library_info = label("", "muted", True)
        layout.addWidget(self.library_info)

    def build_settings(self):
        _, layout = self.page(False)
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setDocumentMode(True)
        self.settings_tabs.tabBar().setDrawBase(False)
        layout.addWidget(self.settings_tabs, 1)
        def section(widget, title):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            self.settings_tabs.addTab(scroll, title)
        appearance, content = card(tr('Application preferences'))
        form = QFormLayout()
        self.setting_theme = combo([(tr('Dark'), "dark"), (tr('Light'), "light")])
        self.setting_language = combo([("English", "en"), ("Español", "es")])
        self.setting_accent = QLineEdit()
        self.setting_accent.setMaximumWidth(130)
        self.setting_countdown = spin(0, 30, 3, " s")
        self.setting_speed = spin(0.1, 10, 1, "×", 2)
        self.setting_folder = QLineEdit()
        self.setting_folder.setPlaceholderText(tr('Default portable folder'))
        self.setting_minimize = combo([(tr('Continue with visible indicator'), "keep"), (tr('Pause the active task'), "pause")])
        self.setting_policy = combo([(tr('Block the second macro'), "block"), (tr('Queue macros · up to 32'), "queue")])
        self.setting_confirm = QCheckBox(tr('Confirm before deleting macros'))
        self.setting_close = QCheckBox(tr('Hide to tray on close'))
        for name, widget in ((tr('Theme'), self.setting_theme), (tr('Accent color'), row(self.setting_accent, button(tr('Choose color'), self.choose_accent), None)),
                              (tr('Language'), self.setting_language), (tr('Default countdown'), self.setting_countdown),
                              (tr('Default speed'), self.setting_speed),
                              (tr('Macro folder'), row(self.setting_folder, button(tr('Browse'), self.choose_macro_folder))),
                              (tr('When minimized'), self.setting_minimize), (tr('When another macro is running'), self.setting_policy)):
            form.addRow(name, widget)
        content.addLayout(form)
        content.addWidget(label(tr("Language changes take effect after restarting Nexo."), "muted", True))
        content.addWidget(self.setting_confirm)
        content.addWidget(self.setting_close)
        content.addWidget(label(tr('The X hides Nexo next to the clock. Use its tray icon to show it or quit.'), 'muted', True))
        content.addWidget(label(tr('The queue runs one macro at a time. Recording and autoclicker tasks block other automation.'), "muted", True))
        section(appearance, "General")
        shortcuts, content = card(tr('Global shortcuts'), tr("Assign individual triggers in Configure macro. This section reserves the application's controls."))
        form = QFormLayout()
        self.setting_hotkeys = {}
        for action, title in HOTKEY_LABELS.items():
            field = ShortcutField()
            self.setting_hotkeys[action] = field
            form.addRow(title, row(field, button(tr('Assign shortcut'), lambda checked=False, target=field: self.assign_record_control(target))))
        content.addLayout(form)
        content.addWidget(label(tr('Press Assign shortcut, then your combination, such as Ctrl+Enter or Ctrl+Alt+Enter. Esc cancels. Conflicts are checked before applying changes.'), "muted", True))
        section(shortcuts, tr('Shortcuts'))
        exclusions, content = card(tr('Keys excluded from recording'))
        self.restrictions = RecordingRestrictions(self)
        content.addWidget(self.restrictions)
        section(exclusions, tr('Exclusions'))
        layout.addWidget(row(button(tr('Save preferences'), self.save_settings, primary=True),
                              button(tr('Restore defaults'), self.restore_settings), None, button(tr('Quit Nexo'), self.request_exit)))
        self.hook_status = label("", "notice", True)
        layout.addWidget(self.hook_status)
        self.load_settings_fields()

    def load_settings_fields(self, data=None):
        data = data or self.settings.data
        self.restrictions.load(data["excluded_keys"])
        self.setting_theme.setCurrentIndex(self.setting_theme.findData(data["theme"]))
        self.setting_language.setCurrentIndex(self.setting_language.findData(data["language"]))
        self.setting_accent.setText(data["accent"])
        self.setting_countdown.setValue(data["countdown"])
        self.setting_speed.setValue(data["speed"])
        self.setting_folder.setText(data["macro_folder"])
        self.setting_minimize.setCurrentIndex(self.setting_minimize.findData(data["minimize"]))
        self.setting_policy.setCurrentIndex(self.setting_policy.findData(data["concurrency"]))
        self.setting_confirm.setChecked(data["confirm_delete"])
        self.setting_close.setChecked(data['minimize_on_close'])
        for key, field in self.setting_hotkeys.items():
            field.setText(data["hotkeys"][key])
        for key, field in self.record_hotkey_fields.items():
            field.setText(data["hotkeys"][key])

    def apply_theme(self):
        accent = self.settings.data['accent']
        self.setProperty('accentColor', accent)
        self.setStyleSheet(stylesheet(self.settings.data["theme"], self.settings.data["accent"]))
        for panel in (self.playback_panel, self.record_indicator):
            panel.setProperty('accentColor', accent)
        self.playback_panel.update_phase(self.playback_panel.phase, getattr(self.playback_panel.macro_name, 'full_name', ''))
        self.record_indicator.update_phase(self.record_indicator.phase)
        self.lock_switch.update()
        for control in self.findChildren(ThemedButton):
            if control.symbol and control.property('danger'):
                control.setIcon(icon(control.symbol, accent))

    def toggle_sidebar(self):
        self.set_sidebar_collapsed(not self.settings.data["sidebar_collapsed"])

    def set_sidebar_collapsed(self, collapsed, animate=True):
        self.settings.data["sidebar_collapsed"] = collapsed
        self.side_brand.setText("NEXO")
        self.side_brand.setProperty("collapsed", collapsed)
        self.side_brand.style().unpolish(self.side_brand)
        self.side_brand.style().polish(self.side_brand)
        self.brand_marker.setVisible(not collapsed)
        self.version_label.setVisible(True)
        caption = tr('Show sidebar') if collapsed else tr('Hide sidebar')
        self.side_brand.setToolTip("")
        self.side_brand.setAccessibleName(caption)
        for item, name in zip(self.nav, self.page_names):
            item.dismiss_hint()
            item.setText(name)
            item.setProperty("collapsed", collapsed)
            item.style().unpolish(item)
            item.style().polish(item)
        if not hasattr(self, "sidebar_animation"):
            self.sidebar_animation = QVariantAnimation(self)
            self.sidebar_animation.setDuration(320)
            self.sidebar_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self.sidebar_animation.valueChanged.connect(self.update_sidebar_width)
            self.sidebar_animation.finished.connect(self.finish_sidebar_transition)
        self.sidebar_animation.stop()
        target = 72 if collapsed else 186
        if animate:
            self.update_sidebar_width(self.sidebar.width())
            self.sidebar_animation.setStartValue(self.sidebar.width())
            self.sidebar_animation.setEndValue(target)
            self.sidebar_animation.start()
        else:
            self.update_sidebar_width(target)
            self.finish_sidebar_transition()

    def update_sidebar_width(self, width):
        self.sidebar.setFixedWidth(int(width))
        reveal = max(0.0, min(1.0, (float(width) - 72) / 114))
        self.side_brand.setText("N" + "EXO"[:round(3 * reveal)])
        self.side_brand.detail_opacity = 1.0
        self.side_brand.update()
        version = "Nexo  " + __version__
        self.version_label.setText(version[:round(len(version) * reveal)])
        for item, name in zip(self.nav, self.page_names):
            item.setText(name[:round(len(name) * reveal)])
            item.text_opacity = 1.0
            item.update()

    def finish_sidebar_transition(self):
        collapsed = self.settings.data["sidebar_collapsed"]
        self.side_brand.setText("N" if collapsed else "NEXO")
        self.version_label.setVisible(not collapsed)
        for item, name in zip(self.nav, self.page_names):
            item.setText("" if collapsed else name)

    def change_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)
        self.breadcrumb.setText("NEXO  /  " + self.page_names[index].upper())
        self.title.setText(self.page_names[index])
        self.title.setVisible(index != 0)
        self.subtitle.setVisible(index != 0)
        self.macro_toolbar.setVisible(index in (1, 2, 4))
        self.new_button.setVisible(index in (1, 2))
        self.new_button.setText(tr('New macro'))
        self.target_label.setText(tr('Window to record') if index == 1 else tr('Target'))
        self.target_row.setToolTip(tr('Only records input while the selected window is active.') if index == 1 else tr('Choose the window where automation will run.'))
        self.target_row.setVisible(index in (1, 2, 3))
        self.target_options.setVisible(index in (2, 3) and self.target_combo.currentData() is not None)
        self.save_button.setVisible(index == 4)
        self.config_macro_button.setText(tr('Shortcut and playback') if index == 4 else tr('Configure'))
        descriptions = ["", tr('Capture a sequence at your own pace.'),
                        tr('Your macro, ready to run.'), tr('Repeat clicks or keys at your own interval.'),
                        tr('Build and fine-tune every action.'), tr('Find and organize your sequences.'),
                        tr('Make Nexo work your way.')]
        self.subtitle.setText(descriptions[index])
        self.statusBar().hide()
        if hasattr(self, "editor"):
            self.home.refresh()

    def refresh_player(self, index=0):
        macro = self.macros.get(self.engine.active_id) if self.engine.task == "play" else self.current
        self.player_name.setText(macro.name if macro else tr('Select a macro'))
        self.macro_toggle.setText(tr('Disable shortcut') if macro and macro.enabled else tr('Enable shortcut'))
        self.macro_toggle.setEnabled(bool(macro) and not self.engine.busy)
        if macro:
            self.player_meta.setText(tr('{0} actions · {1:g} s · {2} · {3}', len(macro.events), macro.duration, MODE_LABELS[macro.activation], display_binding(macro.trigger) or tr('No shortcut')))
            if macro.events:
                from .sequence import describe_event
                action = max(0, min(index, len(macro.events) - 1))
                prefix = tr('Current action') if self.engine.task == "play" else tr('First action')
                self.player_action.setText(f"{prefix} · {action + 1:02d}   {describe_event(macro.events[action])}")
            else:
                self.player_action.setText(tr('No actions yet. Record a sequence or open the editor.'))
        else:
            self.player_meta.setText(tr('Create a macro to get started.'))
            self.player_action.setText(tr('No actions'))
        if self.engine.task != "play":
            self.progress.setValue(0)
            self.play_progress.setText(tr('Ready to play · Progress will update when the macro runs'))

    def show_notice(self, text, warning=False):
        if not text or text.startswith((tr('Saved automatically'), tr('Unsaved changes'), tr('Ready ·'))):
            return
        self.notice.attach(self.capture_dialog if self.capture_dialog.isVisible() else self)
        self.notice.show_message(text, warning)

    def show_error(self, text):
        QMessageBox.warning(self, "Nexo", text)

    def start_hooks(self):
        if not self.enable_hooks:
            self.hook_status.setText(tr('Test mode without global capture.'))
            return
        try:
            validate_bindings(self.macros.values(), self.router_controls())
        except ValidationError as exc:

            for macro in self.macros.values():
                macro.enabled, macro.trigger = False, ""
            self.show_error(str(exc) + tr(' Triggers were disabled for this session so you can review them.'))
        self.configure_router(self.macros.values(), self.router_controls())
        try:
            self.start_hotkeys(self.settings.data["hotkeys"])
            self.hotkeys_ok = True
        except ValidationError as exc:
            self.hotkeys_ok = False
            self.show_error(str(exc) + tr(' Automation will remain blocked until the shortcuts are fixed.'))
        try:
            self.router.start()
            self.router_ok = True
        except Exception:
            self.router_ok = False
            self.show_error(tr('Could not start global controls. Automation is blocked.'))
        self.hook_status.setText(tr('Global controls available. Injected input does not trigger macros.') if self.hotkeys_ok and self.router_ok else tr('Check your shortcuts before running automation.'))
        self.home.refresh()
        if self.settings.warning:
            self.show_error(self.settings.warning)
        if self.library.errors:
            self.show_error(tr('Skipped {0} damaged files. They were kept in the folder so you can recover them.', len(self.library.errors)))

    def native_macro_bindings(self):
        if self.engine.input_delivery != 'activate' or not self.engine.enabled or foreground_process() == os.getpid():
            return {}
        return {'macro:' + macro.id: macro.trigger for macro in self.macros.values()
                if macro.enabled and macro.trigger and isinstance(parse_binding(macro.trigger).key, int)}

    def start_hotkeys(self, mapping):
        extra = self.native_macro_bindings()
        self.router.native_macros = set()
        try:
            self.hotkeys.start(mapping, extra=extra)
        except ValidationError:
            self.hotkeys_ok = False
            self.native_registration_signature = None
            raise
        self.router.native_macros = {action[6:] for action in extra}
        self.native_registration_signature = (tuple(mapping.items()), tuple(extra.items()))
        self.native_registration_ready = True
        self.hotkeys_ok = True

    def native_focus_changed(self, state):
        QTimer.singleShot(0, self, self.sync_native_macros)

    def sync_native_macros(self):
        if not self.enable_hooks or not self.native_registration_ready or not self.engine.enabled or getattr(self, 'closed', False):
            return
        mapping = self.settings.data['hotkeys']
        signature = (tuple(mapping.items()), tuple(self.native_macro_bindings().items()))
        if signature != self.native_registration_signature:
            try:
                self.start_hotkeys(mapping)
            except ValidationError as exc:
                self.show_error(str(exc))

    def configure_router(self, macros, controls):
        ignored = [name.capitalize() for name in ("ctrl", "alt", "shift", "win") if self.settings.data["clicker"].get("ignore_" + name, False)]
        self.router.configure(macros, controls, ignored_hold_modifiers=ignored)
        if self.native_registration_ready and self.enable_hooks:
            self.sync_native_macros()

    def native_hotkey(self, action):
        if action.startswith('macro:'):
            identifier = action[6:]
            if identifier in self.router.native_macros and self.engine.enabled and self.engine.input_delivery == "activate" and self.router.macro_allowed():
                self.route_hotkey('macro_press', identifier)

    def route_hotkey(self, action, identifier):
        if action == 'keyboard_repeat_release' and self.hold_control is not None and self.hold_control is self.engine.control:
            self.engine.stop()
            self.hold_control = None
        if action == "emergency":
            self.engine.stop()
        elif action == "macro_release":
            self.engine.release_trigger(identifier)
        self.bridge.hotkey.emit(action, identifier)

    def on_hotkey(self, action, identifier):
        if not self.engine.enabled:
            return
        if action == "emergency":
            self.emergency()
        elif action == "record_start":
            if not self.engine.busy:
                self.start_recording()
        elif action == "record_stop" and self.engine.task == "record":
            self.stop_task()
        elif action == "record_pause" and self.engine.task == "record":
            self.pause_task()
        elif action == "play":
            self.start_playback()
        elif action == "stop" and self.engine.task == "play":
            self.stop_task()
        elif action == "click":
            if self.engine.task == 'click':
                self.stop_task()
            else:
                self.start_clicker()
        elif action == 'keyboard_repeat_press':
            if self.click_kind.currentData() == 'keyboard' and self.router.hold_active is not None and not self.engine.busy:
                self.start_clicker(held=True)
        elif action == "macro_release":
            self.engine.release_trigger(identifier)
        elif action == "macro_press":
            macro = self.macros.get(identifier)
            if not macro or not macro.enabled or not self.automation_ready():
                return
            if macro.activation == "hold" and not any(item[0] == identifier for item in self.router.active.values()):
                return
            try:
                if not self.validate_coordinates(macro, interactive=False):
                    return
                result = self.engine.trigger(macro)
                statuses = {"blocked": tr('Another task is running; macro blocked.'), "queued": tr('Macro added to queue.'), "queue_full": tr('The queue is full.'), "unqueued": tr('Macro removed from queue.')}
                if result in statuses:
                    self.statusBar().showMessage(statuses[result], 5000)
                    if result in ("blocked", "queue_full"):
                        self.show_notice(statuses[result], warning=True)
            except ValidationError as exc:
                self.statusBar().showMessage(str(exc), 8000)

    def automation_ready(self):
        if not self.engine.enabled:
            self.show_notice(tr('Nexo is locked. Turn off the switch above the version number to continue.'))
            return False
        if not self.hotkeys_ok or not self.router_ok:
            self.show_error(tr('Set an available emergency stop shortcut before starting tasks.'))
            return False
        if self.picking:
            self.show_error(tr('Finish picking a position before starting a task.'))
            return False
        return True

    def set_automation_locked(self, locked):
        self.router.set_suspended(locked)
        self.engine.set_enabled(not locked)
        if locked:
            self.cancel_picker()
            self.hotkeys.stop()
        elif self.enable_hooks:
            try:
                self.start_hotkeys(self.settings.data['hotkeys'])
                self.hotkeys_ok = True
            except ValidationError as exc:
                self.hotkeys_ok = False
                self.show_error(str(exc))
        self.sync_state()
        self.show_notice(tr('Nexo locked: automation and shortcuts disabled.') if locked else tr('Nexo unlocked: automation available.'))

    def require_idle(self):
        if self.engine.busy:
            self.statusBar().showMessage(tr('Stop the current task before changing the library.'), 4000)
            return False
        return True

    def refresh_current(self):
        self.current_combo.blockSignals(True)
        self.current_combo.clear()
        if not self.macros:
            self.current_combo.addItem(tr('No macros · create one'), None)
        for macro in sorted(self.macros.values(), key=lambda m: m.name.lower()):
            self.current_combo.addItem(icon("library"), macro.name, macro.id)
        if self.current:
            self.current_combo.setCurrentIndex(self.current_combo.findData(self.current.id))
            self.macro_summary.setText(tr('{0}  ·  {1}  ·  Shortcut: {2}  ·  {3}  ·  {4}', self.current.name, self.current.category, display_binding(self.current.trigger) or tr('not assigned'), MODE_LABELS[self.current.activation], tr('Enabled') if self.current.enabled else tr('Disabled')))
        else:
            self.macro_summary.setText(tr('Create a macro to add actions.'))
        self.current_combo.blockSignals(False)
        self.record_target_label.setText(tr('Recording for ') + self.current.name if self.current else tr('Recording will create a new macro.'))
        self.refresh_player()
        self.editor.refresh_summary()
        if self.engine.task != "record":
            self.record_timer.setText(duration_text(self.current.duration if self.current else 0))
            self.record_count.setText(tr('{0} actions in the selected macro', len(self.current.events) if self.current else 0))
        self.sync_state()

    def select_macro(self, identifier):
        if identifier and self.require_idle():
            self.save_current()
            self.load_macro(identifier)

    def load_macro(self, identifier):
        if identifier not in self.macros:
            return
        self.current = self.macros[identifier]
        self.loading = True
        self.editor.model.load(self.current.events)
        self.loading = False
        self.play_speed.setValue(self.current.speed)
        self.play_repetitions.setValue(self.current.repetitions)
        self.settings.data["last_macro"] = identifier
        self.refresh_current()

    def new_macro(self, checked=False, name=None):
        if not self.require_idle():
            return
        self.save_current()
        mode, destination = "once", "editor"
        if name is None:
            dialog = CreateMacroDialog(self)
            if not dialog.exec():
                return
            name, mode, destination = dialog.name.text().strip(), dialog.activation, dialog.destination
        macro = Macro(name=name, activation=mode, speed=self.settings.data["speed"])
        self.macros[macro.id] = macro
        self.load_macro(macro.id)
        self.save_current()
        if destination != "editor":
            self.record_mode.setCurrentIndex(self.record_mode.findData(destination))
            self.change_page(1)
        else:
            self.change_page(4)

    def configure_macro(self):
        if not self.current or not self.require_idle():
            return
        self.save_current()
        def validator(candidate):
            others = [m for m in self.macros.values() if m.id != candidate.id]
            validate_bindings(others + [candidate], self.router_controls())
            if candidate.trigger and candidate.enabled and not (candidate.id in self.router.native_macros and parse_binding(candidate.trigger) == parse_binding(self.macros[candidate.id].trigger)):
                check_os_binding(candidate.trigger)
        dialog = MacroDialog(self.current, self.router, validator, self, categories=[macro.category for macro in self.macros.values()])
        if dialog.exec():
            self.current = dialog.result_macro
            self.macros[self.current.id] = self.current
            self.refresh_current()
            self.play_speed.setValue(self.current.speed)
            self.play_repetitions.setValue(self.current.repetitions)
            self.save_current()
            self.configure_router(self.macros.values(), self.router_controls())

    def events_changed(self):
        if self.loading or not self.current:
            return
        self.current.events = list(self.editor.model.events)
        self.current.modified = now_iso()
        self.home.refresh()
        self.refresh_player()
        self.statusBar().showMessage(tr('Unsaved changes…'))
        self.autosave_timer.start()

    def save_current(self):
        self.autosave_timer.stop()
        if self.current:
            self.current.events = list(self.editor.model.events)
            self.current.modified = now_iso()
            self.writer.submit(self.current)
            self.refresh_library()

    def refresh_library(self):
        selected_id = self.library_selection() if hasattr(self, "library_table") else None
        macros = sorted(self.macros.values(), key=lambda m: m.modified, reverse=True)
        self.library_table.setRowCount(len(macros))
        for r, macro in enumerate(macros):
            try:
                modified = datetime.fromisoformat(macro.modified).astimezone().strftime("%d/%m %H:%M")
            except ValueError:
                modified = "—"
            values = [macro.name, display_binding(macro.trigger) or "—", MODE_LABELS[macro.activation], f"{macro.duration:.2f} s", str(len(macro.events)),
                      tr('Enabled') if macro.enabled else tr('Disabled'), macro.category, modified, macro.id]
            for c, value in enumerate(values):
                self.library_table.setItem(r, c, QTableWidgetItem(value))
            if macro.id == selected_id:
                self.library_table.selectRow(r)
        previous = self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(tr('All categories'), "")
        for category in sorted({macro.category for macro in macros}):
            self.category_filter.addItem(category, category)
        self.category_filter.setCurrentIndex(max(0, self.category_filter.findData(previous)))
        self.category_filter.blockSignals(False)
        self.filter_library()
        self.library_info.setText(tr("{0} macros · {1}\nImported files open disabled, with no trigger assigned.", len(macros), self.library.folder))
        self.home.refresh()

    def filter_library(self):
        query = self.search.text().casefold()
        category = self.category_filter.currentData()
        for r in range(self.library_table.rowCount()):
            name = " ".join(self.library_table.item(r, c).text() for c in (0, 1, 6))
            cat = self.library_table.item(r, 6).text()
            self.library_table.setRowHidden(r, query not in name.casefold() or bool(category and cat != category))

    def library_selection(self):
        row_number = self.library_table.currentRow()
        if row_number >= 0 and self.library_table.item(row_number, 8):
            return self.library_table.item(row_number, 8).text()
        return None

    def open_library_selection(self):
        identifier = self.library_selection()
        if identifier and self.require_idle():
            self.select_macro(identifier)
            self.change_page(4)

    def open_library_player(self):
        identifier = self.library_selection()
        if identifier and self.require_idle():
            self.select_macro(identifier)
            self.change_page(2)

    def toggle_current_macro(self):
        if self.current:
            for index in range(self.library_table.rowCount()):
                if self.library_table.item(index, 8).text() == self.current.id:
                    self.library_table.selectRow(index)
                    self.toggle_macro()
                    break

    def configure_library_selection(self):
        identifier = self.library_selection()
        if identifier and self.require_idle():
            self.select_macro(identifier)
            self.configure_macro()

    def open_recent(self, row_number):
        if row_number < len(self.recent_ids) and self.require_idle():
            self.select_macro(self.recent_ids[row_number])
            self.change_page(4)

    def toggle_macro(self):
        identifier = self.library_selection()
        if not identifier or not self.require_idle():
            return
        macro = self.macros[identifier]
        if not macro.trigger:
            self.select_macro(identifier)
            self.configure_macro()
            return
        if not macro.enabled:
            try:
                check_os_binding(macro.trigger)
            except ValidationError as exc:
                self.show_error(str(exc))
                return
        macro.enabled = not macro.enabled
        self.writer.submit(macro)
        self.configure_router(self.macros.values(), self.router_controls())
        self.refresh_library()
        self.refresh_current()

    def duplicate_macro(self):
        identifier = self.library_selection()
        if identifier and self.require_idle():
            try:
                macro = self.library.duplicate(self.macros[identifier])
                self.macros[macro.id] = macro
                self.load_macro(macro.id)
                self.refresh_library()
                self.configure_router(self.macros.values(), self.router_controls())
            except (OSError, ValidationError) as exc:
                self.show_error(str(exc))

    def delete_macro(self):
        identifier = self.library_selection()
        if not identifier or not self.require_idle():
            return
        if self.settings.data["confirm_delete"]:
            result = QMessageBox.question(self, tr('Delete macro'), tr('Delete “{0}” from the library?', self.macros[identifier].name), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if result != QMessageBox.StandardButton.Yes:
                return
        self.autosave_timer.stop()
        if not self.writer.flush():
            self.show_error(tr('A save is pending or failed. The macro was not deleted.'))
            return
        try:
            self.library.delete(identifier)
            del self.macros[identifier]
            if self.current and self.current.id == identifier:
                self.current = next(iter(self.macros.values()), None)
                self.editor.model.load(self.current.events if self.current else [])
            self.configure_router(self.macros.values(), self.router_controls())
            self.refresh_current()
            self.refresh_library()
        except OSError:
            self.show_error(tr('Could not delete the file. Check its permissions.'))

    def import_macro(self):
        if not self.require_idle():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('Import macro'), "", "Nexo JSON (*.json)")
        if path:
            try:
                macro = self.library.import_file(path)
                self.macros[macro.id] = macro
                self.select_macro(macro.id)
                self.refresh_library()
                self.statusBar().showMessage(tr('Macro imported and validated. Trigger disabled.'), 6000)
            except (OSError, ValidationError) as exc:
                self.show_error(str(exc))

    def export_macro(self):
        identifier = self.library_selection() or (self.current.id if self.current else None)
        if not identifier:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr('Export macro'), "macro.json", "Nexo JSON (*.json)")
        if path:
            try:
                self.library.export_file(self.macros[identifier], path)
                self.statusBar().showMessage(tr('Macro exported.'), 4000)
            except (OSError, ValidationError) as exc:
                self.show_error(str(exc))

    def open_macro_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.folder)))

    def start_recording(self):
        if not self.automation_ready() or not self.require_idle():
            return
        if self.current is None:
            self.new_macro(name=tr('Recording ') + datetime.now().strftime("%d-%m %H.%M.%S"))
        self.save_current()

        if not self.writer.flush():
            self.show_error(tr('Could not save the macro before recording.'))
            return
        if self.current.events:
            try:
                self.library.export_file(self.current, self.settings.directory / "recovery" / f"{self.current.id}.json")
            except OSError:
                self.show_error(tr('Could not save the recovery copy. Check available disk space.'))
                return
        self.record_target = self.current.id
        self.record_timer.setText("00:00:00.000")
        self.record_count.setText(tr('0 recorded events'))
        self.settings.data["record_mode"] = self.record_mode.currentData()
        self.settings.data["fixed_interval"] = self.fixed_interval.value()
        self.settings.data["capture_moves"] = self.capture_moves.isChecked()
        self.attach_record_indicator(self.capture_dialog if self.record_mode.currentData() == "fixed" else None)
        try:
            self.engine.record(seconds=0 if self.record_mode.currentData() == "fixed" else self.record_countdown.value(), capture_moves=self.capture_moves.isChecked(),
                               reserved=excluded_key_codes(self.settings.data["excluded_keys"]),
                               controls=self.settings.data["hotkeys"], mode=self.record_mode.currentData(), fixed_interval=self.fixed_interval.value(),
                               physical_modifiers=self.router.physical_modifiers)
            if self.record_mode.currentData() == "fixed":
                self.capture_dialog.begin(self.current.name, self.fixed_interval.value(), display_binding(self.settings.data["hotkeys"]["record_stop"]), self.current.activation)
        except ValidationError as exc:
            self.show_error(str(exc))

    def validate_coordinates(self, macro, interactive=True):
        pointer_events = [e for e in macro.events if e.x is not None]
        rectangles = monitor_rects()
        if rectangles and any(not any(l <= e.x < r and t <= e.y < b for l, t, r, b in rectangles) for e in pointer_events):
            message = tr('The macro contains coordinates outside the current monitors. Fix them in the editor.')
            self.show_error(message) if interactive else self.statusBar().showMessage(message, 8000)
            return False
        if pointer_events and macro.display_signature and macro.display_signature != monitor_rects():
            if not interactive:
                self.statusBar().showMessage(tr('The monitor layout changed. Review the macro and run it from the player.'), 8000)
                return False
            answer = QMessageBox.question(self, tr('Displays changed'), tr('The monitor layout or resolution changed. Have you checked the coordinates and would you like to use the current displays?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return False
            macro.display_signature = monitor_rects()
            self.writer.submit(macro)
        return True

    def request_target_activation(self, callback, control):
        from PySide6.QtCore import QThread
        if QThread.currentThread() == self.thread():
            control.wait()
            callback()
            return
        request = dict(callback=callback, control=control, done=threading.Event(), error=None)
        self.bridge.activation.emit(request)
        while not request['done'].wait(.02):
            control.wait()
        if request['error'] is not None:
            raise request['error']
        control.wait()

    def perform_target_activation(self, request):
        from ..playback import Cancelled
        try:
            if request['control'].cancelled:
                raise Cancelled()
            request['callback']()
        except Exception as exc:
            request['error'] = exc
        finally:
            request['done'].set()

    def start_playback(self, selection=False):
        if not self.current or not self.automation_ready() or not self.require_idle():
            return
        selected = None
        if selection is True:
            rows = self.editor.table.selected_rows()
            if not rows:
                self.show_error(tr('Select one or more rows in the editor.'))
                return
            selected = [self.editor.model.events[i] for i in rows]
        if not self.validate_coordinates(self.current):
            return
        try:
            self.progress.setValue(0)
            self.engine.play(self.current, seconds=self.play_countdown.value(), speed=self.play_speed.value(),
                             repetitions=0 if self.play_continuous.isChecked() else self.play_repetitions.value(), selected=selected)
            if self.pages.currentIndex() != 0:
                self.change_page(2)
        except ValidationError as exc:
            self.show_error(str(exc))

    def start_clicker(self, held=False):
        if self.engine.task == "click":
            self.stop_task()
            return
        if not self.automation_ready() or not self.require_idle():
            return
        try:
            interval = interval_seconds(self.interval_hours.value(), self.interval_minutes.value(), self.interval_seconds.value(), self.interval_ms.value())
            keyboard_mode = self.click_kind.currentData() == "keyboard"
            position = (self.click_x.value(), self.click_y.value()) if not keyboard_mode and self.click_position.currentData() == "fixed" else None
            if position and not point_on_screen(*position):
                raise ValidationError(tr('The coordinates do not belong to any monitor.'))
            options = ClickOptions(self.click_button.currentData(), self.click_double.isChecked(), interval,
                                   self.interval_max.value() if self.variable_interval.isChecked() else None,
                                   position, 0 if self.click_infinite.isChecked() else self.click_repetitions.value(), self.click_duration.value(),
                                   self.repeat_key.text() if keyboard_mode else "")
            options.validate()
            self.cache_clicker_settings()
            self.settings.save()
            self.click_stats.setText(tr('0 clicks  ·  0 repeats  ·  00:00:00.000'))
            if held and self.router.hold_active is None:
                return
            self.engine.click(options, 0 if held else self.click_countdown.value())
            if held:
                self.hold_control = self.engine.control
                if self.router.hold_active is None:
                    self.engine.stop()
                    self.hold_control = None
        except (ValidationError, OSError) as exc:
            self.show_error(tr('Could not start or save the autoclicker: ') + str(exc))

    def pause_task(self):
        if self.engine.task == "record" and self.capture_dialog.reviewing:
            self.capture_dialog.reviewing = False
        self.engine.pause()
        self.sync_state()

    def stop_recording_indicator(self):
        if self.picking:
            self.cancel_picker()
        else:
            self.stop_task()

    def stop_task(self):
        if self.engine.task == "record" and self.capture_dialog.isVisible() and not self.capture_dialog.reviewing:
            self.capture_dialog.stop_for_review()
            return
        self.engine.stop()
        self.sync_state()

    def emergency(self):
        self.engine.stop()
        self.cancel_picker()
        self.router.capture = None
        self.statusBar().showMessage(tr('Emergency stop · tasks canceled and queue cleared'), 6000)
        self.sync_state()

    def clear_queue(self):
        with self.engine.lock:
            self.engine.queue.clear()
        self.queue_label.setText(tr('Queue empty'))

    def pick_position(self):
        if not self.require_idle() or self.picking:
            return
        self.picking = True
        self.attach_record_indicator(None)
        self.picker = PositionPicker(self.bridge.position.emit)
        self.picker.start()
        self.showMinimized()
        self.record_indicator.show_picker(display_binding(self.settings.data["hotkeys"]["emergency"]))
        self.record_indicator.show()
        QTimer.singleShot(15000, self.cancel_picker)

    def attach_record_indicator(self, parent):
        if self.record_indicator.parentWidget() is parent:
            return
        position = self.record_indicator.pos()
        self.record_indicator.setParent(parent, self.record_indicator.windowFlags())
        self.record_indicator.move(position)

    def position_selected(self, x, y):
        self.click_x.setValue(x)
        self.click_y.setValue(y)
        self.click_position.setCurrentIndex(self.click_position.findData("fixed"))
        QTimer.singleShot(180, self.cancel_picker)

    def cancel_picker(self):
        if not self.picking:
            return
        self.picking = False
        if self.picker:
            self.picker.stop()
            self.picker = None
        self.record_indicator.hide()
        self.showNormal()
        self.activateWindow()

    def on_engine_event(self, name, data):
        if name == "countdown":
            self.status_badge.setText(tr('Starts in {0:.1f} s', data['remaining']))
            if self.engine.task == "play":
                self.playback_panel.detail.setText(tr('Starts in {0:.1f} s', data['remaining']))
        elif name == "state":
            self.sync_state()
        elif name == "progress":
            self.refresh_player(data["index"])
            self.progress.setValue(round(data["index"] / data["total"] * 100))
            self.play_progress.setText(tr('Completed actions: {0} of {1}  ·  {2} completed iterations  ·  {3}', data['index'], data['total'], data['iterations'], duration_text(data['elapsed'])))
            self.playback_panel.set_progress(data["index"], data["total"], data["iterations"], duration_text(data["elapsed"]))
        elif name == "clicks":
            unit = tr('keystrokes') if self.click_kind.currentData() == "keyboard" else tr('clicks')
            self.click_stats.setText(tr('{0:,} {1}  ·  {2:,} repeats  ·  {3}', data['clicks'], unit, data['actions'], duration_text(data['elapsed'])))
        elif name == "finished":
            if data["task"] == "record":
                self.capture_dialog.hide()
            if data["task"] == "record" and data["result"] is not None and data["result"]["events"]:
                macro = self.macros.get(self.record_target)
                if macro:
                    macro.events = data["result"]["events"]
                    macro.display_signature = data["result"]["display_signature"]
                    self.load_macro(macro.id)
                    self.save_current()
                    self.change_page(4)
            if data.get("error"):
                self.clear_queue()
                self.show_error(data["error"])
            if data["task"] == "record":
                self.refresh_current()
            self.sync_state()
            self.engine.next_queued()
        elif name == "warning":
            self.show_notice(data["message"], warning=True)
        elif name == "saved":
            if not self.autosave_timer.isActive():
                self.statusBar().showMessage(tr('Saved automatically · ') + datetime.now().strftime("%H:%M:%S"), 4000)

    def sync_state(self):
        if not hasattr(self, "editor"):
            return
        if hasattr(self, "notice"):
            self.notice.attach(self.capture_dialog if self.capture_dialog.isVisible() else self)
        busy = self.engine.busy
        task, phase = self.engine.task, self.engine.phase
        names = {"idle": tr('Ready'), "record": tr('Recording'), "play": tr('Playing'), "click": "Autoclicker"}
        phase_suffix = tr(' · Paused') if phase == "paused" else tr(' · Stopping') if phase == "stopping" else ""
        if phase != "countdown":
            self.status_badge.setText("●  " + names[task] + phase_suffix)
        self.editor.set_editable(not busy and self.current is not None)
        self.current_combo.setEnabled(not busy)
        self.new_button.setEnabled(not busy)
        self.config_macro_button.setEnabled(not busy and self.current is not None)
        self.play_selection.setEnabled(self.engine.enabled and not busy and self.current is not None)
        self.library_actions.setEnabled(not busy)
        self.record_start.setEnabled(self.engine.enabled and not busy)
        self.play_start.setEnabled(self.engine.enabled and not busy and self.current is not None and bool(self.current.events))
        self.macro_toggle.setEnabled(not busy and self.current is not None)
        self.click_start.setEnabled(self.engine.enabled and not busy)
        self.target_combo.setEnabled(not busy)
        self.target_delivery.setEnabled(not busy)
        self.target_refresh.setEnabled(not busy)
        self.record_pause.setEnabled(task == "record" and phase not in ("countdown", "stopping"))
        self.record_pause.setText(tr('Resume') if phase == "paused" else tr('Pause'))
        self.play_pause.setEnabled(task == "play" and phase not in ("countdown", "stopping"))
        self.play_pause.setText(tr('Resume') if phase == "paused" else tr('Pause'))
        self.play_navigation.setEnabled(task == "play" and phase in ("running", "paused"))
        self.record_stop.setEnabled(task == "record")
        self.play_stop.setEnabled(task == "play")
        self.click_stop.setEnabled(task == "click")
        self.capture_moves.setEnabled(not busy and self.record_mode.currentData() == "timed")
        for field in (self.record_mode, self.fixed_interval, self.click_kind, self.repeat_key):
            field.setEnabled(not busy)
        self.pick_button.setEnabled(not busy and not self.picking)
        if task == "record" and phase in ("running", "paused"):
            self.record_indicator.update_phase(phase)
            self.record_indicator.show()
        elif not self.picking:
            self.record_indicator.hide()
        if task == "play" and phase != "stopping":
            active = self.macros.get(self.engine.active_id)
            if getattr(self, "_panel_control", None) is not self.engine.control:
                self._panel_control = self.engine.control
                self.playback_panel.set_progress(0, self.engine.control.event_count, 0, duration_text(0))
                self.progress.setValue(0)
                self.play_progress.setText(tr('Completed actions: 0 of {0}', self.engine.control.event_count))
            self.playback_panel.update_phase(phase, active.name if active else tr('Current macro'))
            self.playback_panel.show()
        else:
            self.playback_panel.hide()
        self.home.refresh()
        self.update_click_options()
        self.record_timer.setProperty("recording", task == "record" and phase == "running")
        self.record_timer.style().unpolish(self.record_timer)
        self.record_timer.style().polish(self.record_timer)
        if task == "record":
            self.capture_dialog.set_phase(phase)

    def tick(self):
        layout = keyboard_layout()
        if layout != getattr(self, '_label_layout', None):
            self._label_layout = layout
            self.refresh_library()
            if not self.engine.busy:
                self.refresh_current()
        if self.engine.recorder:
            recorder = self.engine.recorder
            self.record_timer.setText(duration_text(recorder.duration))
            self.record_count.setText(tr('{0:,} recorded events', len(recorder.events)))
            if recorder.mode == "fixed":
                self.capture_dialog.update_events(recorder.snapshot(), recorder.can_undo_reset)
                self.capture_dialog.set_phase(self.engine.phase)
            if recorder.privacy_reason:
                self.record_privacy.setText(recorder.privacy_reason + tr(' Always pause before entering sensitive information.'))
            if time.monotonic() - self.last_checkpoint > 5 and self.record_target:
                self.last_checkpoint = time.monotonic()
                macro = self.macros.get(self.record_target)
                if macro:
                    snapshot = copy.copy(macro)
                    snapshot.events = recorder.snapshot()
                    snapshot.display_signature = monitor_rects()
                    self.recovery_writer.submit(snapshot)
        self.queue_label.setText(tr('{0} macros queued', len(self.engine.queue)) if self.engine.queue else tr('Queue empty'))

    def choose_accent(self):
        dialog = ColorDialog(self.setting_accent.text(), self)
        if dialog.exec():
            self.setting_accent.setText(dialog.color.name())

    def assign_record_control(self, field):
        if not self.require_idle():
            return
        dialog = AssignDialog(self.router, self)
        if dialog.exec() and dialog.value:
            field.setText(dialog.value)

    def save_record_controls(self):
        if not self.require_idle():
            return
        from ..config import validate_settings
        candidate = copy.deepcopy(self.settings.data)
        candidate["hotkeys"].update({key: field.text().strip() for key, field in self.record_hotkey_fields.items()})
        previous = copy.deepcopy(self.settings.data)
        try:
            candidate = validate_settings(candidate)
            validate_bindings(self.macros.values(), self.router_controls(candidate["hotkeys"]))
            if self.enable_hooks:
                self.start_hotkeys(candidate["hotkeys"])
            self.settings.save(candidate)
            self.configure_router(self.macros.values(), self.router_controls(candidate["hotkeys"]))
            self.hotkeys_ok = True
            self.load_settings_fields()
            self.statusBar().showMessage(tr('Recording controls saved and excluded from capture.'), 6000)
        except (ValidationError, OSError) as exc:
            if self.enable_hooks:
                try:
                    self.start_hotkeys(previous["hotkeys"])
                    self.hotkeys_ok = True
                except ValidationError:
                    self.hotkeys_ok = False
            self.show_error(str(exc))

    def choose_macro_folder(self):
        folder = QFileDialog.getExistingDirectory(self, tr('Macro folder'), str(self.library.folder))
        if folder:
            self.setting_folder.setText(folder)

    def save_settings(self):
        if not self.require_idle():
            return
        from ..config import validate_settings
        old = copy.deepcopy(self.settings.data)
        candidate = copy.deepcopy(old)
        candidate.update(language=self.setting_language.currentData(), theme=self.setting_theme.currentData(), accent=self.setting_accent.text(),
                         countdown=self.setting_countdown.value(), speed=self.setting_speed.value(),
                         macro_folder=self.setting_folder.text().strip(), minimize=self.setting_minimize.currentData(),
                         confirm_delete=self.setting_confirm.isChecked(), minimize_on_close=self.setting_close.isChecked(), concurrency=self.setting_policy.currentData(),
                         excluded_keys=copy.deepcopy(self.restrictions.entries),
                         hotkeys={key: field.text().strip() for key, field in self.setting_hotkeys.items()})
        try:
            candidate = validate_settings(candidate)
            validate_bindings(self.macros.values(), self.router_controls(candidate["hotkeys"]))
            folder = Path(candidate["macro_folder"]) if candidate["macro_folder"] else self.settings.directory / "macros"
            new_library = Library(folder)
            if folder.resolve() != self.library.folder.resolve():

                new_macros = {m.id: m for m in new_library.all()}
                validate_bindings(new_macros.values(), self.router_controls(candidate["hotkeys"]))
            else:
                new_macros = self.macros
            if self.enable_hooks and self.engine.enabled:
                try:
                    self.start_hotkeys(candidate["hotkeys"])
                except ValidationError:
                    self.start_hotkeys(old["hotkeys"])
                    raise
            self.settings.save(candidate)
            self.hotkeys_ok = True
            if new_macros is not self.macros:
                self.save_current()
                if not self.writer.close():
                    raise ValidationError(tr('Could not finish saving the previous library.'))
                self.library, self.macros = new_library, new_macros
                self.writer = SaveService(self.library, self.bridge.event.emit)
                self.current = next(iter(self.macros.values()), None)
                self.editor.model.load(self.current.events if self.current else [])
            self.configure_router(self.macros.values(), self.router_controls(candidate["hotkeys"]))
            self.engine.policy = candidate["concurrency"]
            self.apply_theme()
            for field in (self.record_countdown, self.play_countdown, self.click_countdown):
                field.setValue(candidate["countdown"])
            self.play_speed.setValue(candidate["speed"])
            self.load_settings_fields()
            self.home.refresh()
            self.emergency_label.setText(display_binding(candidate["hotkeys"]["emergency"]))
            self.refresh_library()
            self.refresh_current()
            self.hook_status.setText(tr('Preferences saved. Nexo remains locked.') if not self.engine.enabled else tr('Preferences saved. Global shortcuts available.'))
            if candidate["language"] != old["language"]:
                self.hook_status.setText(tr("Preferences saved. Restart Nexo to apply the language."))
            self.statusBar().showMessage(tr("Preferences saved. Restart Nexo to apply the language.") if candidate["language"] != old["language"] else tr("Preferences saved."), 10000)
        except (ValidationError, OSError) as exc:
            self.show_error(str(exc))

    def restore_settings(self):
        self.load_settings_fields(copy.deepcopy(DEFAULTS))
        self.statusBar().showMessage(tr('Defaults restored in the form. Press Save preferences to apply them.'), 6000)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and hasattr(self, "engine"):
            if self.settings.data["minimize"] == "pause" and self.engine.busy and self.engine.phase == "running":
                self.engine.pause()
        super().changeEvent(event)

    def closeEvent(self, event):
        if self.closed:
            event.accept()
            return

        if self.enable_hooks and self.settings.data['minimize_on_close'] and not self.exit_requested:
            if self.ensure_tray():
                if self.settings.data['minimize'] == 'pause' and self.engine.busy and self.engine.phase == 'running':
                    self.engine.pause()
                self.hide()
            else:
                self.show_notice(tr('The system tray is unavailable. Nexo will stay open so you can access it.'), warning=True)
            event.ignore()
            return
        self.timer.stop()
        self.autosave_timer.stop()
        self.cancel_picker()
        if not self.engine.close():
            event.ignore()
            self.show_error(tr('The task is still releasing resources. Wait a moment, then close again.'))
            self.timer.start()
            return

        QApplication.processEvents()
        self.save_current()
        self.writer.retry_failed()
        self.recovery_writer.retry_failed()
        if not self.writer.flush():
            self.abort_close(event, tr('Some macros could not be saved. Check disk space and permissions, or export your changes before closing again.'))
            return
        if not self.recovery_writer.flush():
            self.abort_close(event, tr('Recovery copies could not be saved. Check disk space and permissions, then close again to retry.'))
            return
        self.cache_clicker_settings()
        self.settings.data["window_size"] = [self.width(), self.height()]
        self.settings.data["last_macro"] = self.current.id if self.current else ""
        try:
            self.settings.save()
        except (OSError, ValidationError):
            self.abort_close(event, tr('Could not save preferences. Nexo will stay open: check disk space and permissions, then close again to retry.'))
            return
        main_closed = self.writer.close()
        recovery_closed = self.recovery_writer.close()
        if not main_closed or not recovery_closed:
            self.writer = SaveService(self.library, self.bridge.event.emit)
            self.recovery_writer = SaveService(Library(self.settings.directory / "recovery"), self.bridge.event.emit)
            self.abort_close(event, tr('Could not finish saving on exit. Nexo will stay open so you can export and try again.'))
            return
        self.closed = True
        if self.tray:
            self.tray.hide()
        self.router.stop()
        self.hotkeys.stop()
        self.record_indicator.close()
        self.playback_panel.close()
        self.capture_dialog.hide()
        event.accept()

    def request_exit(self):
        self.exit_requested = True
        self.close()
        if not self.closed:
            self.exit_requested = False
        else:
            QApplication.quit()

    def ensure_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        if self.tray is None:
            self.tray = QSystemTrayIcon(self)
            tray_icon = QApplication.windowIcon()
            self.tray.setIcon(tray_icon if not tray_icon.isNull() else icon('nav_home'))
            self.tray.setToolTip(tr('Nexo · Show or hide'))
            menu = QMenu(self)
            self.tray_show = menu.addAction(tr('Show Nexo'))
            self.tray_show.triggered.connect(self.show_from_tray)
            menu.setDefaultAction(self.tray_show)
            menu.addSeparator()
            self.tray_exit = menu.addAction(tr('Quit Nexo'))
            self.tray_exit.triggered.connect(self.request_exit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        return True

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_from_tray()

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def abort_close(self, event, message):
        event.ignore()
        self.engine.shutting_down = False
        self.timer.start()
        self.show_error(message)
