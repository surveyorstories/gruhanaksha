import os
import shutil
import datetime
import hashlib
import json
import subprocess
import sys
import time
from qgis.utils import iface
try:
    from qgis.PyQt.QtCore import QTimer, Qt, QThread, pyqtSignal
    from qgis.PyQt.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
        QMessageBox, QFileDialog, QRadioButton, QButtonGroup, QListWidget,
        QListWidgetItem, QCheckBox, QFrame, QSystemTrayIcon, QWidgetAction,
        QTextEdit, QTabWidget
    )
    from qgis.PyQt.QtGui import QFont, QIcon
    from qgis.core import QgsProject, QgsVectorLayer, Qgis
except ImportError:
    try:
        from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
        from PyQt5.QtWidgets import *
        from PyQt5.QtGui import QFont
    except ImportError:
        from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
        from PyQt6.QtWidgets import *
        from PyQt6.QtGui import QFont


class QtCompat:
    """Qt version compatibility helper"""

    @staticmethod
    def _get_enum(parent, enum_class, attr_name):
        """Helper to get enum value from Qt5 or Qt6"""
        try:
            # Qt6: Try enum class approach
            if hasattr(parent, enum_class):
                enum = getattr(parent, enum_class)
                if hasattr(enum, attr_name):
                    return getattr(enum, attr_name)
            # Qt5: Direct attribute
            if hasattr(parent, attr_name):
                return getattr(parent, attr_name)
        except:
            pass
        # Final fallback
        return getattr(parent, attr_name)

    @classmethod
    def checked(cls):
        return cls._get_enum(Qt, 'CheckState', 'Checked')

    @classmethod
    def unchecked(cls):
        return cls._get_enum(Qt, 'CheckState', 'Unchecked')

    @classmethod
    def user_role(cls):
        return cls._get_enum(Qt, 'ItemDataRole', 'UserRole')

    @classmethod
    def text_interaction(cls):
        return cls._get_enum(Qt, 'TextInteractionFlag', 'TextBrowserInteraction')

    @classmethod
    def pointing_cursor(cls):
        return cls._get_enum(Qt, 'CursorShape', 'PointingHandCursor')

    @classmethod
    def hline(cls):
        return cls._get_enum(QFrame, 'Shape', 'HLine')

    @classmethod
    def sunken(cls):
        return cls._get_enum(QFrame, 'Shadow', 'Sunken')

    @classmethod
    def window_flags(cls):
        try:
            # Qt6
            if hasattr(Qt, 'WindowType'):
                return (Qt.WindowType.Window | Qt.WindowType.WindowTitleHint |
                        Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint |
                        Qt.WindowType.CustomizeWindowHint)
        except:
            pass
        # Qt5
        return (Qt.Window | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint |
                Qt.WindowCloseButtonHint | Qt.CustomizeWindowHint)

    @classmethod
    def stay_on_top(cls):
        return cls._get_enum(Qt, 'WindowType', 'WindowStaysOnTopHint')

    @classmethod
    def double_click(cls):
        return cls._get_enum(QSystemTrayIcon, 'ActivationReason', 'DoubleClick')

    @classmethod
    def info_icon(cls):
        return cls._get_enum(QSystemTrayIcon, 'MessageIcon', 'Information')

    @classmethod
    def warning_icon(cls):
        return cls._get_enum(QSystemTrayIcon, 'MessageIcon', 'Warning')


def get_icon(name):
    """Return QIcon that works in both Qt5 and Qt6."""
    plugin_dir = os.path.dirname(__file__)
    icon_path = os.path.join(plugin_dir, "images", name)
    return QIcon(icon_path) if os.path.exists(icon_path) else QIcon()


class ToolbarTimerWidget(QWidget):
    """Custom widget to display countdown timer in toolbar"""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        # Icon label
        self.icon_label = QLabel("🔄")
        font = QFont()
        font.setPointSize(10)
        self.icon_label.setFont(font)

        # Timer label
        self.timer_label = QLabel("--:--")
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        self.timer_label.setFont(font)
        self.set_timer_color('blue')

        # Status label
        self.status_label = QLabel("Backup Active")
        font = QFont()
        font.setPointSize(8)
        self.status_label.setFont(font)
        self.status_label.setStyleSheet("color: #666;")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.timer_label)
        layout.addWidget(self.status_label)

        self.setLayout(layout)
        self.setCursor(QtCompat.pointing_cursor())
        self.setToolTip("Click to open Backup Manager\nNext backup countdown")

    def set_timer_color(self, color):
        """Set timer color based on urgency"""
        colors = {
            'red': ("D32F2F", "FFEBEE", "EF9A9A"),
            'orange': ("F57C00", "FFF3E0", "FFCC80"),
            'blue': ("2196F3", "E3F2FD", "90CAF9")
        }
        c = colors.get(color, colors['blue'])
        self.timer_label.setStyleSheet(f"""
            QLabel {{
                color: #{c[0]};
                padding: 2px 6px;
                background-color: #{c[1]};
                border-radius: 3px;
                border: 1px solid #{c[2]};
            }}
        """)

    def mousePressEvent(self, event):
        self.clicked.emit()

    def update_timer(self, minutes, seconds):
        self.timer_label.setText(f"{minutes:02d}:{seconds:02d}")
        if minutes == 0 and seconds <= 10:
            self.set_timer_color('red')
        elif minutes == 0 and seconds <= 30:
            self.set_timer_color('orange')
        else:
            self.set_timer_color('blue')

    def update_status(self, status_text):
        self.status_label.setText(status_text)


class ComprehensiveProjectBackupWidget(QWidget):
    timerUpdated = pyqtSignal(str)
    hideTimer = pyqtSignal()
    toolbarTimerUpdate = pyqtSignal(int, int, str)

    def __init__(self, parent=iface.mainWindow()):
        super().__init__(parent)
        self.iface = None

        # Set window properties
        self.setWindowFlags(QtCompat.window_flags())
        self.setWindowFlag(QtCompat.stay_on_top(), False)
        self.setWindowIcon(get_icon("autosave.svg"))
        self.setWindowTitle("Auto Save and Backup")
        self.setMinimumWidth(350)

        # Initialize state variables
        self.timer = QTimer(self)
        self.countdown_timer = QTimer(self)
        self.warning_shown = False
        self.toolbar_widget = None
        self.toolbar_action = None
        self.backup_toolbar = None
        self.tray_icon = None
        self.session_log_path = None
        self.backup_interval_ms = 0
        self.remaining_time = 0
        self.latest_backup_folder = None
        self.backup_history = {}
        self.current_layers = set()
        self.last_backup_time = None
        self.backup_thread = None
        self.layer_registry = QgsProject.instance()
        self.signals_connected = False
        self.is_visible = False

        # Setup UI
        self.setup_ui()
        self.setup_tray_icon()
        self.setup_connections()

        # Initialize backup folder
        default_folder = os.path.join(
            os.path.expanduser("~"), "QGIS_Project_Backups")
        os.makedirs(default_folder, exist_ok=True)
        self.backupFolderPath.setText(default_folder)

        self.history_file = os.path.join(default_folder, "backup_history.json")
        self.load_backup_history()
        self.load_layers()

    def setup_ui(self):
        """Setup user interface"""
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Settings Tab
        self.setup_settings_tab()

        # Log Tab
        self.setup_log_tab()

        # Control buttons
        self.setup_control_buttons(main_layout)
        main_layout.addStretch()

    def setup_settings_tab(self):
        """Setup settings tab"""
        settings_widget = QWidget()
        settings_layout = QVBoxLayout()
        settings_widget.setLayout(settings_layout)
        self.tab_widget.addTab(settings_widget, "Settings")

        # Add separator
        settings_layout.addWidget(self.create_separator())

        # Backup Settings Section
        settings_layout.addWidget(QLabel("Backup Settings"))

        # Backup interval
        intervalLayout = QHBoxLayout()
        self.intervalLabel = QLabel("Backup Interval:")
        self.intervalSpinBox = QSpinBox()
        self.intervalSpinBox.setRange(1, 1440)
        self.intervalSpinBox.setValue(10)
        self.intervalSpinBox.setSuffix(" minutes")
        self.intervalSpinBox.setToolTip("How often to create backups")
        self.intervalSpinBox.setMinimumWidth(120)
        intervalLayout.addWidget(self.intervalLabel)
        intervalLayout.addWidget(self.intervalSpinBox)
        intervalLayout.addStretch()
        settings_layout.addLayout(intervalLayout)

        # Countdown display
        self.countdownLabel = QLabel("Next Backup: Not scheduled")
        self.countdownLabel.setStyleSheet("color: #666; font-style: italic;")
        settings_layout.addWidget(self.countdownLabel)

        # Backup folder section
        settings_layout.addWidget(QLabel("Backup Location:"))
        self.setup_folder_selection(settings_layout)

        # Backup mode section
        settings_layout.addWidget(QLabel("Backup Mode:"))
        self.setup_mode_selection(settings_layout)

        settings_layout.addWidget(self.create_separator())

        # Layer selection section
        settings_layout.addWidget(QLabel("Select Layers to Backup:"))
        self.selectAllCheckbox = QCheckBox("Select All Layers")
        settings_layout.addWidget(self.selectAllCheckbox)

        self.layerListWidget = QListWidget()
        self.layerListWidget.setMinimumHeight(150)
        self.layerListWidget.setAlternatingRowColors(True)
        self.layerListWidget.setToolTip(
            "Check layers you want to include in backup")
        settings_layout.addWidget(self.layerListWidget)

        infoLabel = QLabel("Note: Project file is always included in backup")
        infoLabel.setStyleSheet("color: #666; font-style: italic;")
        settings_layout.addWidget(infoLabel)

    def setup_log_tab(self):
        """Setup log tab"""
        log_widget = QWidget()
        log_layout = QVBoxLayout()
        log_widget.setLayout(log_layout)
        self.tab_widget.addTab(log_widget, "Log")

        self.logTextEdit = QTextEdit()
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setMinimumHeight(100)
        log_layout.addWidget(self.logTextEdit)

        self.clearLogButton = QPushButton("Clear Log")
        log_layout.addWidget(self.clearLogButton)

    def setup_folder_selection(self, layout):
        """Setup folder selection UI"""
        folderLayout = QHBoxLayout()
        self.backupFolderPath = QLabel("")
        self.backupFolderPath.setStyleSheet(
            "color: #0066cc; padding: 5px; background-color: #f5f5f5; "
            "border: 1px solid #ddd; border-radius: 3px;"
        )
        self.backupFolderPath.setTextInteractionFlags(
            QtCompat.text_interaction())
        self.backupFolderPath.setCursor(QtCompat.pointing_cursor())
        self.backupFolderPath.mousePressEvent = self.open_backup_folder
        self.backupFolderPath.setWordWrap(True)
        self.backupFolderPath.setToolTip("Click to open backup folder")

        self.selectFolderButton = self.create_button(
            "Change Folder", "Choose where to store backups")

        folderLayout.addWidget(self.backupFolderPath, 1)
        folderLayout.addWidget(self.selectFolderButton)
        layout.addLayout(folderLayout)

    def setup_mode_selection(self, layout):
        """Setup backup mode selection UI"""
        modeLayout = QHBoxLayout()
        self.singleRadio = QRadioButton("Single Backup")
        self.singleRadio.setChecked(True)
        self.singleRadio.setToolTip(
            "Maintains one backup, overwriting previous version")

        self.multipleRadio = QRadioButton("Multiple Backups")
        self.multipleRadio.setToolTip("Creates timestamped backup copies")

        self.modeGroup = QButtonGroup()
        self.modeGroup.addButton(self.singleRadio)
        self.modeGroup.addButton(self.multipleRadio)

        modeLayout.addWidget(self.singleRadio)
        modeLayout.addWidget(self.multipleRadio)
        modeLayout.addStretch()
        layout.addLayout(modeLayout)

        # Max backups option
        maxBackupsLayout = QHBoxLayout()
        self.maxBackupsLabel = QLabel("Maximum Backups to Keep:")
        self.maxBackupsSpinBox = QSpinBox()
        self.maxBackupsSpinBox.setRange(1, 100)
        self.maxBackupsSpinBox.setValue(10)
        self.maxBackupsSpinBox.setToolTip(
            "Older backups will be automatically deleted")
        self.maxBackupsSpinBox.setMinimumWidth(80)
        maxBackupsLayout.addWidget(self.maxBackupsLabel)
        maxBackupsLayout.addWidget(self.maxBackupsSpinBox)
        maxBackupsLayout.addStretch()
        layout.addLayout(maxBackupsLayout)

        self.maxBackupsLabel.hide()
        self.maxBackupsSpinBox.hide()

    def setup_control_buttons(self, layout):
        """Setup control buttons"""
        layout.addWidget(self.create_separator())

        buttonLayout = QHBoxLayout()
        self.backupNowButton = self.create_button("Backup Now", min_height=35)
        self.startButton = self.create_button(
            "Start Auto Backup", min_height=35)
        self.stopButton = self.create_button("Stop Auto Backup", min_height=35)
        self.stopButton.setEnabled(False)

        buttonLayout.addWidget(self.startButton)
        buttonLayout.addWidget(self.stopButton)
        buttonLayout.addWidget(self.backupNowButton)
        layout.addLayout(buttonLayout)

    def setup_connections(self):
        """Setup signal connections"""
        self.timer.timeout.connect(self.backup_project)
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.selectAllCheckbox.stateChanged.connect(
            self.toggle_select_all_layers)
        self.multipleRadio.toggled.connect(self.on_mode_changed)
        self.singleRadio.toggled.connect(self.on_mode_changed)
        self.selectFolderButton.clicked.connect(self.select_backup_folder)
        self.backupNowButton.clicked.connect(self.backup_now)
        self.startButton.clicked.connect(self.start_backup)
        self.stopButton.clicked.connect(self.stop_backup)
        self.clearLogButton.clicked.connect(self.clear_log)

    def create_separator(self):
        """Create a horizontal separator line"""
        separator = QFrame()
        separator.setFrameShape(QtCompat.hline())
        separator.setFrameShadow(QtCompat.sunken())
        return separator

    def create_button(self, text, tooltip=None, min_height=None):
        """Create a styled button"""
        button = QPushButton(text)
        if tooltip:
            button.setToolTip(tooltip)
        if min_height:
            button.setMinimumHeight(min_height)
        button.setStyleSheet(
            "QPushButton { background-color: #333; color: white; padding: 8px 16px; "
            "border: none; border-radius: 3px; } "
            "QPushButton:hover { background-color: #555; } "
            "QPushButton:disabled { background-color: #999; color: #ccc; }"
        )
        return button

    def clear_log(self):
        self.logTextEdit.clear()

    def setup_tray_icon(self):
        """Setup system tray icon"""
        try:
            self.tray_icon = QSystemTrayIcon(self)
            icon = self.style().standardIcon(self.style().SP_DialogSaveButton)
            self.tray_icon.setIcon(icon)
            self.tray_icon.setToolTip("QGIS Backup Manager")
            self.tray_icon.activated.connect(self.on_tray_icon_activated)
        except Exception as e:
            print(f"System tray icon not available: {e}")
            self.tray_icon = None

    def on_tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QtCompat.double_click():
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def create_toolbar_timer(self):
        """Create and add timer widget to QGIS toolbar"""
        if not self.iface:
            return

        try:
            self.remove_toolbar_timer()
            self.toolbar_widget = ToolbarTimerWidget()
            self.toolbar_widget.clicked.connect(self.on_toolbar_timer_clicked)
            self.toolbar_action = QWidgetAction(self.iface.mainWindow())
            self.toolbar_action.setDefaultWidget(self.toolbar_widget)
            self.backup_toolbar = self.iface.addToolBar("Backup Timer")
            self.backup_toolbar.setObjectName("BackupTimerToolbar")
            self.backup_toolbar.addAction(self.toolbar_action)
        except Exception as e:
            print(f"Failed to create toolbar timer: {e}")

    def remove_toolbar_timer(self):
        """Remove timer widget from toolbar"""
        if self.backup_toolbar and self.iface:
            try:
                self.iface.mainWindow().removeToolBar(self.backup_toolbar)
                self.backup_toolbar.deleteLater()
                self.backup_toolbar = None
                self.toolbar_action = None
                self.toolbar_widget = None
            except Exception as e:
                print(f"Error removing toolbar timer: {e}")

    def on_toolbar_timer_clicked(self):
        """Handle toolbar timer click"""
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show()
        self.activateWindow()
        self.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self.is_visible = True
        self.connect_layer_signals()
        self.load_layers()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.is_visible = False
        self.disconnect_layer_signals()

    def connect_layer_signals(self):
        """Connect layer registry signals"""
        if not self.signals_connected and self.layer_registry:
            try:
                self.layer_registry.layersAdded.connect(self.on_layers_added)
                self.layer_registry.layersRemoved.connect(
                    self.on_layers_removed)
                self.signals_connected = True
            except (TypeError, AttributeError):
                pass

    def disconnect_layer_signals(self):
        """Disconnect layer registry signals"""
        if self.signals_connected and self.layer_registry:
            try:
                self.layer_registry.layersAdded.disconnect(
                    self.on_layers_added)
                self.layer_registry.layersRemoved.disconnect(
                    self.on_layers_removed)
                self.signals_connected = False
            except (TypeError, AttributeError):
                pass

    def load_layers(self):
        """Load vector layers into the layer list"""
        # Block signals to prevent triggering stateChanged during load
        self.selectAllCheckbox.blockSignals(True)
        self.layerListWidget.blockSignals(True)

        self.layerListWidget.clear()
        self.current_layers.clear()
        project = QgsProject.instance()

        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                self.current_layers.add(layer.id())
                item = QListWidgetItem(layer.name())
                item.setData(QtCompat.user_role(), layer.id())
                item.setCheckState(QtCompat.unchecked())
                self.layerListWidget.addItem(item)

        # Restore signal blocking
        self.selectAllCheckbox.blockSignals(False)
        self.layerListWidget.blockSignals(False)

        # Reset select all checkbox state
        self.selectAllCheckbox.setChecked(False)

    def toggle_select_all_layers(self, state):
        """Toggle all layer checkboxes"""
        checked_state = QtCompat.checked()
        unchecked_state = QtCompat.unchecked()

        # Block signals during batch update
        self.layerListWidget.blockSignals(True)

        try:
            is_checked = state == checked_state or (
                hasattr(checked_state, 'value') and state == checked_state.value)
        except AttributeError:
            is_checked = state == checked_state

        for index in range(self.layerListWidget.count()):
            item = self.layerListWidget.item(index)
            item.setCheckState(
                checked_state if is_checked else unchecked_state)

        self.layerListWidget.blockSignals(False)

    def get_selected_layers(self):
        """Get list of selected layer names - FIXED BUG"""
        """Get list of selected layer IDs"""
        selected_layers = []
        checked_state = QtCompat.checked()

        for i in range(self.layerListWidget.count()):
            item = self.layerListWidget.item(i)
            try:
                is_checked = item.checkState() == checked_state or (
                    hasattr(checked_state, 'value') and item.checkState(
                    ) == checked_state.value
                )
            except AttributeError:
                is_checked = item.checkState() == checked_state

            if is_checked:
                selected_layers.append(item.text())
                selected_layers.append(item.data(QtCompat.user_role()))

        return selected_layers

    def select_backup_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Backup Folder", self.backupFolderPath.text())
        if folder:
            self.backupFolderPath.setText(folder)
            self.reset_state()

    def validate_backup_folder(self):
        """Validate backup folder is writable"""
        folder = self.backupFolderPath.text()
        if not folder:
            self.show_message("Please select a backup folder",
                              level=Qgis.Warning)
            return False

        try:
            os.makedirs(folder, exist_ok=True)
            test_file = os.path.join(folder, '.test_write')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except Exception as e:
            self.show_message(
                f"Backup folder is not writable: {e}", level=Qgis.Critical)
            return False

    def backup_now(self):
        """Perform immediate backup"""
        project = QgsProject.instance()
        if not project.fileName():
            self.show_message("Please save the project first",
                              level=Qgis.Warning)
            return

        if not self.validate_backup_folder():
            return

        self.backupNowButton.setEnabled(False)
        self.backup_project()
        QTimer.singleShot(2000, lambda: self.backupNowButton.setEnabled(True))

    def start_backup(self):
        """Start auto backup timer"""
        project = QgsProject.instance()
        if not project.fileName():
            self.show_message("Please save the project first",
                              level=Qgis.Warning)
            return

        if not self.validate_backup_folder():
            return

        project.write()

        # Setup session log
        project_name = os.path.splitext(os.path.basename(project.fileName()))[
            0] or "unnamed_project"
        self.session_log_path = os.path.join(
            self.backupFolderPath.text(),
            f"{project_name}_auto_backup_session.log"
        )

        try:
            with open(self.session_log_path, 'w') as f:
                f.write("Auto Backup Session Log\n" + "="*20 + "\n")
        except Exception as e:
            self.show_message(
                f"Failed to create session log: {e}", level=Qgis.Warning)
            self.session_log_path = None

        self.backup_interval_ms = self.intervalSpinBox.value() * 60 * 1000
        self.remaining_time = self.backup_interval_ms
        self.warning_shown = False

        self.timer.start(self.backup_interval_ms)
        self.countdown_timer.start(1000)

        # Update UI state
        self.set_ui_state(backup_active=True)
        self.setWindowTitle("Auto Save and Backup - ACTIVE")
        self.create_toolbar_timer()

        # Show tray notification
        if self.tray_icon:
            self.tray_icon.show()
            try:
                self.tray_icon.showMessage(
                    "QGIS Backup Started",
                    "Auto backup is now running",
                    QtCompat.info_icon(),
                    3000
                )
            except:
                pass

        self.show_message("Auto backup started - Timer visible in toolbar")
        self.update_countdown()

    def stop_backup(self):
        """Stop auto backup timer"""
        self.timer.stop()
        self.countdown_timer.stop()
        self.warning_shown = False
        self.hideTimer.emit()

        # Update UI state
        self.set_ui_state(backup_active=False)
        self.setWindowTitle("Auto Save and Backup")
        self.remove_toolbar_timer()

        if self.tray_icon:
            self.tray_icon.hide()

        self.countdownLabel.setText("Next Backup: Not scheduled")
        self.countdownLabel.setStyleSheet("color: #666; font-style: italic;")
        self.show_message("Auto backup stopped", level=Qgis.Info)
        self.session_log_path = None

    def set_ui_state(self, backup_active):
        """Set UI element states based on backup status"""
        self.startButton.setEnabled(not backup_active)
        self.stopButton.setEnabled(backup_active)
        self.backupNowButton.setEnabled(True)
        self.intervalSpinBox.setEnabled(not backup_active)
        self.selectFolderButton.setEnabled(not backup_active)
        self.singleRadio.setEnabled(not backup_active)
        self.multipleRadio.setEnabled(not backup_active)
        self.maxBackupsSpinBox.setEnabled(not backup_active)

    def update_countdown(self):
        """Update countdown timer display"""
        self.remaining_time -= 1000
        minutes = self.remaining_time // 60000
        seconds = (self.remaining_time % 60000) // 1000

        # Show warning 10 seconds before backup
        if self.remaining_time <= 10000 and not self.warning_shown:
            message = "Backup will occur in 10 seconds..."
            self.show_message(message, level=Qgis.Info)

            if self.tray_icon and self.isMinimized():
                try:
                    self.tray_icon.showMessage(
                        "QGIS Backup Alert", message, QtCompat.info_icon(), 5000)
                except:
                    pass

            self.warning_shown = True

        countdown_text = f"Next Backup: {minutes:02d}:{seconds:02d}"
        status_text = "Active"

        if self.last_backup_time:
            elapsed = datetime.datetime.now() - self.last_backup_time
            if elapsed.total_seconds() < 2:
                status = "Last backup: Just now"
            else:
                status = f"Last backup: {int(elapsed.total_seconds())} seconds ago"
            countdown_text = f"{countdown_text} | {status}"

            if elapsed.total_seconds() < 60:
                status_text = "Just backed up"

        self.countdownLabel.setText(countdown_text)
        self.countdownLabel.setStyleSheet("color: #2196F3;")
        self.setWindowTitle(
            f"Auto Save and Backup - {minutes:02d}:{seconds:02d}")

        # Update toolbar timer
        if self.toolbar_widget:
            self.toolbar_widget.update_timer(minutes, seconds)
            self.toolbar_widget.update_status(status_text)

        self.toolbarTimerUpdate.emit(minutes, seconds, status_text)

        # Update tray icon
        if self.tray_icon:
            if self.isMinimized():
                self.tray_icon.setToolTip(f"QGIS Backup\n{countdown_text}")
                if not self.tray_icon.isVisible():
                    self.tray_icon.show()
            else:
                if self.tray_icon.isVisible() and self.toolbar_widget:
                    self.tray_icon.hide()

        if self.isMinimized():
            self.timerUpdated.emit(countdown_text)
        else:
            self.hideTimer.emit()

        if self.remaining_time <= 0:
            self.remaining_time = self.backup_interval_ms
            self.warning_shown = False

    def calculate_file_hash(self, filepath):
        """Calculate SHA-256 hash of a file"""
        try:
            hasher = hashlib.sha256()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for {filepath}: {e}")
            return None

    def load_backup_history(self):
        """Load backup history from JSON file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    self.backup_history = json.load(f)
        except Exception as e:
            self.show_message(
                f"Failed to load backup history: {e}", level=Qgis.Warning)
            self.backup_history = {}

    def save_backup_history(self):
        """Save backup history to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self.backup_history, f, indent=4)
        except Exception as e:
            self.show_message(
                f"Failed to save backup history: {e}", level=Qgis.Warning)

    def cleanup_old_backups(self):
        """Remove old backups exceeding the maximum count"""
        if not self.multipleRadio.isChecked():
            return

        backup_root = self.backupFolderPath.text()
        project = QgsProject.instance()
        project_path = project.fileName()

        if not project_path:
            return

        project_name = os.path.splitext(os.path.basename(project_path))[0]
        safe_project_name = "".join(
            c for c in project_name if c.isalnum() or c in (' ', '-', '_')).strip()

        if not safe_project_name:
            safe_project_name = "Project"

        try:
            backup_folders = [
                d for d in os.listdir(backup_root)
                if os.path.isdir(os.path.join(backup_root, d))
                and d.startswith(f"{safe_project_name}_Backup_")
            ]

            if len(backup_folders) > self.maxBackupsSpinBox.value():
                backup_folders.sort()
                for folder in backup_folders[:-self.maxBackupsSpinBox.value()]:
                    try:
                        shutil.rmtree(os.path.join(backup_root, folder))
                    except Exception as e:
                        self.show_message(
                            f"Failed to remove old backup {folder}: {e}", level=Qgis.Warning)
        except Exception as e:
            self.show_message(
                f"Error during backup cleanup: {e}", level=Qgis.Warning)

    def should_backup_file(self, source_file, dest_file):
        """Determine if a file should be backed up"""
        if self.multipleRadio.isChecked():
            return True

        if not os.path.exists(dest_file):
            return True

        try:
            source_stats = os.stat(source_file)
            prev_info = self.backup_history.get(source_file, {})

            if prev_info.get('mtime') == source_stats.st_mtime:
                if not os.path.exists(dest_file):
                    return True
                return False

            current_hash = self.calculate_file_hash(source_file)
            prev_hash = prev_info.get('hash')

            if current_hash != prev_hash:
                return True

            self.backup_history[source_file]['mtime'] = source_stats.st_mtime
            return False

        except Exception as e:
            print(f"Error checking file {source_file}: {e}")
            return True

    def copy_file_with_retry(self, src, dst, max_retries=3):
        """Copy file with retry logic for locked files"""
        for attempt in range(max_retries):
            try:
                shutil.copy2(src, dst)
                return True
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                    time.sleep(0.5)  # Wait before retrying
                else:
                    raise
            except Exception:
                raise
        return False

    def backup_project(self):
        """Main backup function"""
        if not self.validate_backup_folder():
            self.stop_backup()
            return

        project = QgsProject.instance()

        # Commit layer changes
        commit_failed = []
        try:
            for layer in project.mapLayers().values():
                if isinstance(layer, QgsVectorLayer) and layer.isEditable():
                    if not layer.commitChanges():
                        commit_failed.append(layer.name())
                        errors = layer.commitErrors()
                        print(f"Failed to commit {layer.name()}: {errors}")
        except Exception as e:
            self.show_message(
                f"Error committing layer changes: {e}", level=Qgis.Critical)
            self.stop_backup()
            return

        if commit_failed:
            self.show_message(
                f"Failed to commit changes for layers: {', '.join(commit_failed)}",
                level=Qgis.Warning
            )

        # Save project
        try:
            if not project.write():
                raise Exception("Failed to save project")
        except Exception as e:
            self.show_message(
                f"Failed to save project: {e}", level=Qgis.Critical)
            self.stop_backup()
            return

        project_path = project.fileName()
        if not project_path:
            self.show_message(
                "Backup failed: Project not saved", level=Qgis.Critical)
            self.stop_backup()
            return

        project_name = os.path.splitext(os.path.basename(project_path))[0]
        safe_project_name = "".join(c for c in project_name if c.isalnum() or c in (
            ' ', '-', '_')).strip() or "Project"

        # Create backup folder
        if self.multipleRadio.isChecked():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_folder = os.path.join(
                self.backupFolderPath.text(), f"{safe_project_name}_Backup_{timestamp}")
        else:
            backup_folder = os.path.join(
                self.backupFolderPath.text(), f"{safe_project_name}_Latest_Backup")

        backup_summary = []
        backup_errors = []

        try:
            os.makedirs(backup_folder, exist_ok=True)

            # Backup project file
            project_filename = os.path.basename(project_path)
            project_backup_path = os.path.join(backup_folder, project_filename)

            try:
                self.copy_file_with_retry(project_path, project_backup_path)
                backup_summary.append("Project file")
            except Exception as e:
                backup_errors.append(f"Failed to backup project file: {e}")

            # Backup selected layers - FIXED BUG
            selected_layers = self.get_selected_layers()
            selected_layer_ids = self.get_selected_layers()

            if selected_layers:
                for layer_name in selected_layers:
                    layers = project.mapLayersByName(layer_name)
                    if layers:
                        layer = layers[0]
            if selected_layer_ids:
                for layer_id in selected_layer_ids:
                    layer = project.mapLayer(layer_id)
                    if not layer:
                        continue
                    layer_name = layer.name()

                    if layer.providerType() not in ['ogr', 'spatialite', 'gpkg']:
                        continue

                    force_backup = layer.isEditable() and layer.isModified()
                    layer_source = layer.source()

                    try:
                        if self.backup_vector_layer(layer_source, backup_folder, layer_name, force_backup):
                            backup_summary.append(layer_name)
                    except Exception as e:
                        backup_errors.append(
                            f"Failed to backup layer {layer_name}: {e}")

            if not self.multipleRadio.isChecked():
                self.save_backup_history()

        except Exception as e:
            backup_errors.append(f"General backup error: {e}")

        finally:
            # Write backup log
            log_path = os.path.join(backup_folder, "backup_log.txt")
            try:
                with open(log_path, 'w') as f:
                    f.write("Backup Summary\n" + "="*20 + "\n")
                    f.write(
                        f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Project: {project_name}\n")
                    if backup_summary:
                        f.write("\nBacked up files:\n")
                        for item in backup_summary:
                            f.write(f"- {item}\n")
                    if backup_errors:
                        f.write("\nErrors:\n")
                        for err in backup_errors:
                            f.write(f"- {err}\n")
            except Exception as e:
                self.show_message(
                    f"Failed to write backup log: {e}", level=Qgis.Warning)

        # Show completion message
        if backup_errors:
            summary_message = "Backup completed with errors. See log for details."
            level = Qgis.Warning
        else:
            if len(backup_summary) == 1:
                summary_message = "Backup completed: Project file only"
            else:
                layer_names = [
                    item for item in backup_summary if item != "Project file"]
                summary_message = f"Backup completed: Project and layers: {', '.join(layer_names)}"
            level = Qgis.Success

        self.show_message(summary_message, level=level)

        # Update toolbar widget
        if self.toolbar_widget:
            self.toolbar_widget.update_status("Backing up...")
            QTimer.singleShot(1000, lambda: self.toolbar_widget.update_status(
                "Complete!") if self.toolbar_widget else None)
            QTimer.singleShot(3000, lambda: self.toolbar_widget.update_status(
                "Active") if self.toolbar_widget else None)

        if self.tray_icon and self.isMinimized():
            try:
                icon = QtCompat.info_icon() if not backup_errors else QtCompat.warning_icon()
                self.tray_icon.showMessage(
                    "QGIS Backup Complete", summary_message, icon, 3000)
            except:
                pass

        self.cleanup_old_backups()
        self.last_backup_time = datetime.datetime.now()

    def backup_vector_layer(self, source, backup_folder, layer_name, force_backup=False):
        """Backup vector layer files"""
        try:
            safe_layer_name = "".join(
                c for c in layer_name if c.isalnum() or c in (' ', '-', '_')).strip()

            if '|' in source:
                source = source.split('|')[0]

            base_source = os.path.splitext(source)[0]
            new_source_base = os.path.join(backup_folder, safe_layer_name)

            if not os.path.isabs(new_source_base):
                new_source_base = os.path.abspath(new_source_base)

            extensions = [
                '.shp', '.dbf', '.shx', '.prj', '.qpj', '.cpg',
                '.geojson', '.gpkg', '.sqlite', '.qix', '.sbn', '.sbx'
            ]

            backed_up = False
            files_to_backup = []

            for ext in extensions:
                source_file = base_source + ext
                if os.path.exists(source_file):
                    dest_file = new_source_base + ext

                    if force_backup or self.should_backup_file(source_file, dest_file):
                        files_to_backup.append((source_file, dest_file))

            for source_file, dest_file in files_to_backup:
                try:
                    self.copy_file_with_retry(source_file, dest_file)
                    backed_up = True

                    if not self.multipleRadio.isChecked():
                        try:
                            stats = os.stat(source_file)
                            self.backup_history[source_file] = {
                                'hash': self.calculate_file_hash(source_file),
                                'mtime': stats.st_mtime,
                                'size': stats.st_size,
                                'last_backup': datetime.datetime.now().isoformat()
                            }
                        except Exception as e:
                            print(
                                f"Error updating history for {source_file}: {e}")

                except Exception as e:
                    self.show_message(
                        f"Failed to copy {os.path.basename(source_file)}: {e}", level=Qgis.Warning)

            return backed_up

        except Exception as e:
            self.show_message(
                f"Failed to backup layer {layer_name}: {e}", level=Qgis.Critical)
            raise

    def on_layers_added(self, layers):
        """Handle new layers being added to the project"""
        if not self.is_visible:
            return

        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.id() not in self.current_layers:
                self.current_layers.add(layer.id())
                item = QListWidgetItem(layer.name())
                item.setData(QtCompat.user_role(), layer.id())
                item.setCheckState(QtCompat.unchecked())
                self.layerListWidget.addItem(item)
                self.show_message(
                    f"New layer added: {layer.name()}", level=Qgis.Info)

    def on_layers_removed(self, layer_ids):
        """Handle layers being removed from the project"""
        if not self.is_visible:
            return

        for layer_id in layer_ids:
            if layer_id in self.current_layers:
                self.current_layers.remove(layer_id)
                for i in range(self.layerListWidget.count()):
                    item = self.layerListWidget.item(i)
                    if item.data(QtCompat.user_role()) == layer_id:
                        self.layerListWidget.takeItem(i)
                        break

    def set_iface(self, iface):
        """Initialize the QGIS interface"""
        self.iface = iface
        if self.iface:
            self.layer_registry = QgsProject.instance()
            if self.is_visible:
                self.connect_layer_signals()

    def closeEvent(self, event):
        """Called when widget is closed"""
        self.disconnect_layer_signals()
        self.stop_backup()
        self.remove_toolbar_timer()
        if self.tray_icon:
            self.tray_icon.hide()
        super().closeEvent(event)

    def show_message(self, message, level=Qgis.Info, duration=2):
        """Display a message in QGIS's message bar and log panel"""
        if hasattr(self, 'iface') and self.iface and self.iface.messageBar():
            self.iface.messageBar().pushMessage("Backup", message, level, duration)
        else:
            level_text = {
                Qgis.Info: "INFO",
                Qgis.Warning: "WARNING",
                Qgis.Critical: "CRITICAL",
                Qgis.Success: "SUCCESS"
            }.get(level, "INFO")
            print(f"[Backup {level_text}] {message}")

        # Append to log panel
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logTextEdit.append(log_entry)
        self.logTextEdit.ensureCursorVisible()

        # Append to session log file if active
        if self.session_log_path:
            try:
                with open(self.session_log_path, 'a') as f:
                    f.write(log_entry + '\n')
            except Exception as e:
                print(f"Failed to write to session log: {e}")

    def reset_state(self):
        """Reset internal states and history without deleting backup files"""
        self.backup_history = {}
        self.current_layers = set()
        self.last_backup_time = None
        self.remaining_time = 0
        self.latest_backup_folder = None
        self.warning_shown = False

        if os.path.exists(self.history_file):
            try:
                os.remove(self.history_file)
            except Exception:
                pass

        self.load_layers()
        self.countdownLabel.setText("Next Backup: Not scheduled")
        self.countdownLabel.setStyleSheet("color: #666; font-style: italic;")
        self.set_ui_state(backup_active=False)
        self.timer.stop()
        self.countdown_timer.stop()

    def on_mode_changed(self, checked):
        """Handle backup mode changes"""
        if checked:
            self.stop_backup()
            self.reset_state()

            show_max_backups = self.multipleRadio.isChecked()
            self.maxBackupsLabel.setVisible(show_max_backups)
            self.maxBackupsSpinBox.setVisible(show_max_backups)

            self.show_message(
                "Backup mode changed. Previous backups preserved.", level=Qgis.Info)

    def open_backup_folder(self, event):
        """Open the backup folder in the system file explorer"""
        folder = self.backupFolderPath.text()
        if os.path.exists(folder):
            try:
                if os.name == 'nt':
                    os.startfile(folder)
                elif sys.platform == "darwin":
                    subprocess.call(["open", folder])
                else:
                    subprocess.call(["xdg-open", folder])
            except Exception as e:
                self.show_message(
                    f"Failed to open folder: {e}", level=Qgis.Warning)


class BackupPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.widget = ComprehensiveProjectBackupWidget()
        self.widget.set_iface(self.iface)

    def show(self):
        """Show the backup widget"""
        if self.widget:
            self.widget.show()

    def unload(self):
        """Clean up when plugin is unloaded"""
        if self.widget:
            self.widget.remove_toolbar_timer()
            self.widget.close()


# Create and show the widget
# widget = BackupPlugin(iface)
# widget.show()
