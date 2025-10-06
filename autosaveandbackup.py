import os
import shutil
import datetime
import hashlib
import json
import subprocess
import sys
import time

try:
    from qgis.PyQt.QtCore import QTimer, Qt, QThread, pyqtSignal
    from qgis.PyQt.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
        QMessageBox, QFileDialog, QRadioButton, QButtonGroup, QListWidget, QTabWidget,
        QListWidgetItem, QCheckBox, QFrame, QSystemTrayIcon, QWidgetAction,
        QTextEdit
    )
    from qgis.PyQt.QtGui import QFont
    from qgis.core import QgsProject, QgsVectorLayer, Qgis
except ImportError:
    # Fallback for different Qt versions
    try:
        from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
            QMessageBox, QFileDialog, QRadioButton, QButtonGroup, QListWidget,
            QListWidgetItem, QCheckBox, QFrame, QSystemTrayIcon, QWidgetAction,
            QTextEdit
        )
        from PyQt5.QtGui import QFont
    except ImportError:
        from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
        from PyQt6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
            QMessageBox, QFileDialog, QRadioButton, QButtonGroup, QListWidget,
            QListWidgetItem, QCheckBox, QFrame, QSystemTrayIcon, QWidgetAction,
            QTextEdit
        )
        from PyQt6.QtGui import QFont


class BackupThread(QThread):
    """Thread for performing backup operations without blocking UI"""
    finished = pyqtSignal(bool, str, list)
    progress = pyqtSignal(str)

    def __init__(self, backup_func, *args, **kwargs):
        super().__init__()
        self.backup_func = backup_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.backup_func(*self.args, **self.kwargs)
            if result:
                success, message, files = result
                self.finished.emit(success, message, files)
            else:
                self.finished.emit(False, "Backup failed", [])
        except Exception as e:
            self.finished.emit(False, "Backup error: {}".format(str(e)), [])


# Qt version compatibility helpers
def get_qt_checkstate_checked():
    """Get the Checked state constant for current Qt version"""
    try:
        return Qt.CheckState.Checked
    except AttributeError:
        return Qt.Checked


def get_qt_checkstate_unchecked():
    """Get the Unchecked state constant for current Qt version"""
    try:
        return Qt.CheckState.Unchecked
    except AttributeError:
        return Qt.Unchecked


def get_qt_user_role():
    """Get the UserRole constant for current Qt version"""
    try:
        return Qt.ItemDataRole.UserRole
    except AttributeError:
        return Qt.UserRole


def get_qt_text_interaction():
    """Get the TextBrowserInteraction constant for current Qt version"""
    try:
        return Qt.TextInteractionFlag.TextBrowserInteraction
    except AttributeError:
        return Qt.TextBrowserInteraction


def get_qt_cursor():
    """Get the PointingHandCursor constant for current Qt version"""
    try:
        return Qt.CursorShape.PointingHandCursor
    except AttributeError:
        return Qt.PointingHandCursor


def get_frame_shape():
    """Get the HLine shape constant for current Qt version"""
    try:
        return QFrame.Shape.HLine
    except AttributeError:
        return QFrame.HLine


def get_frame_shadow():
    """Get the Sunken shadow constant for current Qt version"""
    try:
        return QFrame.Shadow.Sunken
    except AttributeError:
        return QFrame.Sunken


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
        self.timer_label.setStyleSheet("""
            QLabel {
                color: #2196F3;
                padding: 2px 6px;
                background-color: #E3F2FD;
                border-radius: 3px;
                border: 1px solid #90CAF9;
            }
        """)

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
        self.setCursor(get_qt_cursor())
        self.setToolTip("Click to open Backup Manager\nNext backup countdown")

    def mousePressEvent(self, event):
        """Handle click to open main widget"""
        self.clicked.emit()

    def update_timer(self, minutes, seconds):
        """Update the timer display"""
        self.timer_label.setText("{:02d}:{:02d}".format(minutes, seconds))

        # Change color based on time remaining
        if minutes == 0 and seconds <= 10:
            # Red when < 10 seconds
            self.timer_label.setStyleSheet("""
                QLabel {
                    color: #D32F2F;
                    padding: 2px 6px;
                    background-color: #FFEBEE;
                    border-radius: 3px;
                    border: 1px solid #EF9A9A;
                }
            """)
        elif minutes == 0 and seconds <= 30:
            # Orange when < 30 seconds
            self.timer_label.setStyleSheet("""
                QLabel {
                    color: #F57C00;
                    padding: 2px 6px;
                    background-color: #FFF3E0;
                    border-radius: 3px;
                    border: 1px solid #FFCC80;
                }
            """)
        else:
            # Blue for normal countdown
            self.timer_label.setStyleSheet("""
                QLabel {
                    color: #2196F3;
                    padding: 2px 6px;
                    background-color: #E3F2FD;
                    border-radius: 3px;
                    border: 1px solid #90CAF9;
                }
            """)

    def update_status(self, status_text):
        """Update status text"""
        self.status_label.setText(status_text)


class ComprehensiveProjectBackupWidget(QWidget):
    timerUpdated = pyqtSignal(str)
    hideTimer = pyqtSignal()
    toolbarTimerUpdate = pyqtSignal(int, int, str)  # minutes, seconds, status

    def __init__(self, parent=None):
        super().__init__(parent)
        self.iface = None

        self.setWindowTitle("Auto Save and Backup")
        self.setMinimumWidth(300)
        self.timer = QTimer(self)
        self.countdown_timer = QTimer(self)
        self.warning_shown = False

        # Add toolbar widget references
        self.toolbar_widget = None
        self.toolbar_action = None
        self.backup_toolbar = None

        # Add system tray icon support
        self.tray_icon = None
        self.setup_tray_icon()

        # Session log path
        self.session_log_path = None

        # Main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Settings Tab
        settings_widget = QWidget()
        settings_layout = QVBoxLayout()
        settings_widget.setLayout(settings_layout)
        self.tab_widget.addTab(settings_widget, "Settings")

        # Log Tab
        log_widget = QWidget()
        log_layout = QVBoxLayout()
        log_widget.setLayout(log_layout)
        self.tab_widget.addTab(log_widget, "Log")

        # Add separator
        separator1 = QFrame()
        separator1.setFrameShape(get_frame_shape())
        separator1.setFrameShadow(get_frame_shadow())
        settings_layout.addWidget(separator1)

        # Backup Settings Section
        settingsLabel = QLabel("Backup Settings")
        settings_layout.addWidget(settingsLabel)

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
        folderLabel = QLabel("Backup Location:")
        settings_layout.addWidget(folderLabel)

        folderLayout = QHBoxLayout()
        self.backupFolderPath = QLabel("")
        self.backupFolderPath.setStyleSheet(
            "color: #0066cc; padding: 5px; background-color: #f5f5f5; border: 1px solid #ddd; border-radius: 3px;"
        )
        self.backupFolderPath.setTextInteractionFlags(
            get_qt_text_interaction())
        self.backupFolderPath.setCursor(get_qt_cursor())
        self.backupFolderPath.mousePressEvent = self.open_backup_folder
        self.backupFolderPath.setWordWrap(True)
        self.backupFolderPath.setToolTip("Click to open backup folder")

        self.selectFolderButton = QPushButton("Change Folder")
        self.selectFolderButton.clicked.connect(self.select_backup_folder)
        self.selectFolderButton.setToolTip("Choose where to store backups")
        self.selectFolderButton.setStyleSheet(
            "QPushButton { background-color: #333; color: white; padding: 6px 12px; border: none; border-radius: 3px; } "
            "QPushButton:hover { background-color: #555; } "
            "QPushButton:disabled { background-color: #999; color: #ccc; }"
        )

        folderLayout.addWidget(self.backupFolderPath, 1)
        folderLayout.addWidget(self.selectFolderButton)
        settings_layout.addLayout(folderLayout)

        # Backup mode section
        modeLabel = QLabel("Backup Mode:")
        settings_layout.addWidget(modeLabel)

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
        settings_layout.addLayout(modeLayout)

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
        settings_layout.addLayout(maxBackupsLayout)

        self.maxBackupsLabel.hide()
        self.maxBackupsSpinBox.hide()

        # Connect mode change signals
        self.multipleRadio.toggled.connect(self.on_mode_changed)
        self.singleRadio.toggled.connect(self.on_mode_changed)

        # Add separator
        separator2 = QFrame()
        separator2.setFrameShape(get_frame_shape())
        separator2.setFrameShadow(get_frame_shadow())
        settings_layout.addWidget(separator2)

        # Layer selection section
        layerLabel = QLabel("Select Layers to Backup:")
        settings_layout.addWidget(layerLabel)

        self.selectAllCheckbox = QCheckBox("Select All Layers")
        self.selectAllCheckbox.stateChanged.connect(
            self.toggle_select_all_layers)
        settings_layout.addWidget(self.selectAllCheckbox)

        self.layerListWidget = QListWidget()
        self.layerListWidget.setMinimumHeight(150)
        self.layerListWidget.setAlternatingRowColors(True)
        self.layerListWidget.setToolTip(
            "Check layers you want to include in backup")
        settings_layout.addWidget(self.layerListWidget)

        infoLabel = QLabel("Note: Project file is always included in backup")
        infoLabel.setStyleSheet(
            "color: #666; font-style: italic;")
        settings_layout.addWidget(infoLabel)

        # Backup Log section
        self.logTextEdit = QTextEdit()
        self.logTextEdit.setReadOnly(True)
        self.logTextEdit.setMinimumHeight(100)
        log_layout.addWidget(self.logTextEdit)

        self.clearLogButton = QPushButton("Clear Log")
        self.clearLogButton.clicked.connect(self.clear_log)
        log_layout.addWidget(self.clearLogButton)

        # Add separator
        separator3 = QFrame()
        separator3.setFrameShape(get_frame_shape())
        separator3.setFrameShadow(get_frame_shadow())
        main_layout.addWidget(separator3)

        # Control buttons
        buttonLayout = QHBoxLayout()

        self.backupNowButton = QPushButton("Backup Now")
        self.backupNowButton.clicked.connect(self.backup_now)
        self.backupNowButton.setMinimumHeight(35)
        self.backupNowButton.setStyleSheet(
            "QPushButton { background-color: #333; color: white; padding: 8px 16px; border: none; border-radius: 3px; } "
            "QPushButton:hover { background-color: #555; } "
            "QPushButton:disabled { background-color: #999; color: #ccc; }"
        )

        self.startButton = QPushButton("Start Auto Backup")
        self.startButton.clicked.connect(self.start_backup)
        self.startButton.setMinimumHeight(35)
        self.startButton.setStyleSheet(
            "QPushButton { background-color: #333; color: white; padding: 8px 16px; border: none; border-radius: 3px; } "
            "QPushButton:hover { background-color: #555; } "
            "QPushButton:disabled { background-color: #999; color: #ccc; }"
        )

        self.stopButton = QPushButton("Stop Auto Backup")
        self.stopButton.clicked.connect(self.stop_backup)
        self.stopButton.setEnabled(False)
        self.stopButton.setMinimumHeight(35)
        self.stopButton.setStyleSheet(
            "QPushButton { background-color: #333; color: white; padding: 8px 16px; border: none; border-radius: 3px; } "
            "QPushButton:hover { background-color: #555; } "
            "QPushButton:disabled { background-color: #999; color: #ccc; }"
        )

        buttonLayout.addWidget(self.startButton)
        buttonLayout.addWidget(self.stopButton)
        buttonLayout.addWidget(self.backupNowButton)
        main_layout.addLayout(buttonLayout)

        main_layout.addStretch()

        # Setup timers
        self.timer.timeout.connect(self.backup_project)
        self.countdown_timer.timeout.connect(self.update_countdown)

        # Set default backup folder
        default_folder = os.path.join(
            os.path.expanduser("~"), "QGIS_Project_Backups")
        os.makedirs(default_folder, exist_ok=True)
        self.backupFolderPath.setText(default_folder)

        self.backup_interval_ms = 0
        self.remaining_time = 0
        self.latest_backup_folder = None

        self.backup_history = {}
        self.history_file = os.path.join(
            os.path.expanduser("~"), "QGIS_Project_Backups", "backup_history.json")
        self.load_backup_history()

        self.current_layers = set()
        self.load_layers()

        self.last_backup_time = None
        self.backup_thread = None

        self.layer_registry = QgsProject.instance()
        self.signals_connected = False
        self.is_visible = False

        self.reset_state()

    def clear_log(self):
        self.logTextEdit.clear()

    def setup_tray_icon(self):
        """Setup system tray icon for minimized notifications"""
        try:
            self.tray_icon = QSystemTrayIcon(self)
            icon = self.style().standardIcon(self.style().SP_DialogSaveButton)
            self.tray_icon.setIcon(icon)
            self.tray_icon.setToolTip("QGIS Backup Manager")
            self.tray_icon.activated.connect(self.on_tray_icon_activated)
        except Exception as e:
            print("System tray icon not available: {}".format(str(e)))
            self.tray_icon = None

    def on_tray_icon_activated(self, reason):
        """Handle tray icon double-click to restore window"""
        try:
            try:
                double_click = QSystemTrayIcon.ActivationReason.DoubleClick
            except AttributeError:
                double_click = QSystemTrayIcon.DoubleClick

            if reason == double_click:
                self.showNormal()
                self.activateWindow()
                self.raise_()
        except:
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def create_toolbar_timer(self):
        """Create and add timer widget to QGIS toolbar"""
        if not self.iface:
            print("No iface available for toolbar")
            return

        try:
            # Remove existing toolbar widget if present
            self.remove_toolbar_timer()

            # Create toolbar widget
            self.toolbar_widget = ToolbarTimerWidget()
            self.toolbar_widget.clicked.connect(self.on_toolbar_timer_clicked)

            # Create action to hold the widget
            self.toolbar_action = QWidgetAction(self.iface.mainWindow())
            self.toolbar_action.setDefaultWidget(self.toolbar_widget)

            # Add to toolbar
            self.backup_toolbar = self.iface.addToolBar("Backup Timer")
            self.backup_toolbar.setObjectName("BackupTimerToolbar")
            self.backup_toolbar.addAction(self.toolbar_action)

            print("Toolbar timer created successfully")
        except Exception as e:
            print("Failed to create toolbar timer: {}".format(str(e)))
            import traceback
            traceback.print_exc()

    def remove_toolbar_timer(self):
        """Remove timer widget from toolbar"""
        if self.backup_toolbar and self.iface:
            try:
                self.iface.mainWindow().removeToolBar(self.backup_toolbar)
                self.backup_toolbar.deleteLater()
                self.backup_toolbar = None
                self.toolbar_action = None
                self.toolbar_widget = None
                print("Toolbar timer removed")
            except Exception as e:
                print("Error removing toolbar timer: {}".format(str(e)))

    def on_toolbar_timer_clicked(self):
        """Handle toolbar timer click - show/restore main window"""
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show()
        self.activateWindow()
        self.raise_()

    def showEvent(self, event):
        """Called when widget becomes visible"""
        super().showEvent(event)
        self.is_visible = True
        self.connect_layer_signals()
        self.load_layers()

    def hideEvent(self, event):
        """Called when widget is hidden"""
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
        self.layerListWidget.clear()
        self.current_layers.clear()
        project = QgsProject.instance()

        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                self.current_layers.add(layer.id())
                item = QListWidgetItem(layer.name())
                item.setData(get_qt_user_role(), layer.id())
                item.setCheckState(get_qt_checkstate_unchecked())
                self.layerListWidget.addItem(item)

    def toggle_select_all_layers(self, state):
        checked_state = get_qt_checkstate_checked()
        unchecked_state = get_qt_checkstate_unchecked()

        for index in range(self.layerListWidget.count()):
            item = self.layerListWidget.item(index)
            try:
                if state == checked_state or state == checked_state.value:
                    item.setCheckState(checked_state)
                else:
                    item.setCheckState(unchecked_state)
            except AttributeError:
                if state == checked_state:
                    item.setCheckState(checked_state)
                else:
                    item.setCheckState(unchecked_state)

    def select_backup_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Backup Folder", self.backupFolderPath.text())
        if folder:
            self.backupFolderPath.setText(folder)
            self.reset_state()

    def validate_backup_folder(self):
        """Validate and ensure backup folder is writable"""
        folder = self.backupFolderPath.text()
        if not folder:
            self.show_message("Please select a backup folder",
                              level=Qgis.Warning, duration=2)
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
                "Backup folder is not writable: {}".format(str(e)), level=Qgis.Critical, duration=2)
            return False

    def backup_now(self):
        """Perform an immediate backup"""
        project = QgsProject.instance()
        if not project.fileName():
            self.show_message("Please save the project first",
                              level=Qgis.Warning, duration=2)
            return

        if not self.validate_backup_folder():
            return

        self.backupNowButton.setEnabled(False)
        self.backup_project()
        QTimer.singleShot(2000, lambda: self.backupNowButton.setEnabled(True))

    def start_backup(self):
        # self.show_message("'Start Auto Backup' clicked.",
        #                   level=Qgis.Info, duration=2)
        project = QgsProject.instance()
        if not project.fileName():
            self.show_message("Please save the project first",
                              level=Qgis.Warning, duration=2)
            return

        if not self.validate_backup_folder():
            return

        project.write()

        # Set up session log file
        project = QgsProject.instance()
        project_path = project.fileName()
        project_name = os.path.splitext(os.path.basename(project_path))[
            0] if project_path else "unnamed_project"
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_log_path = os.path.join(
            self.backupFolderPath.text(),
            f"{project_name}_auto_backup_session.log"
        )
        # Create the file
        try:
            with open(self.session_log_path, 'w') as f:
                f.write("Auto Backup Session Log\n")
                f.write("=" * 20 + "\n")
        except Exception as e:
            self.show_message(
                f"Failed to create session log file: {str(e)}", level=Qgis.Warning, duration=2
            )
            self.session_log_path = None

        self.backup_interval_ms = self.intervalSpinBox.value() * 60 * 1000
        self.remaining_time = self.backup_interval_ms
        self.warning_shown = False

        # self.show_message("Starting backup timer...",
        #                   level=Qgis.Info, duration=2)
        self.timer.start(self.backup_interval_ms)
        self.countdown_timer.start(1000)

        # Update UI state
        self.startButton.setEnabled(False)
        self.stopButton.setEnabled(True)
        self.backupNowButton.setEnabled(True)
        self.intervalSpinBox.setEnabled(False)
        self.selectFolderButton.setEnabled(False)
        self.singleRadio.setEnabled(False)
        self.multipleRadio.setEnabled(False)
        self.maxBackupsSpinBox.setEnabled(False)

        # Update window title
        self.setWindowTitle("Auto Save and Backup - ACTIVE")

        # Create toolbar timer
        self.create_toolbar_timer()

        # Show tray notification
        if self.tray_icon:
            self.tray_icon.show()
            try:
                self.tray_icon.showMessage(
                    "QGIS Backup Started",
                    "Auto backup is now running",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
            except:
                self.tray_icon.showMessage(
                    "QGIS Backup Started",
                    "Auto backup is now running",
                    QSystemTrayIcon.Information,
                    3000
                )

        self.show_message("Auto backup started - Timer visible in toolbar")
        self.update_countdown()

    def stop_backup(self):
        self.timer.stop()
        self.countdown_timer.stop()
        self.warning_shown = False
        self.hideTimer.emit()

        # Update UI state
        self.startButton.setEnabled(True)
        self.stopButton.setEnabled(False)
        self.backupNowButton.setEnabled(True)
        self.intervalSpinBox.setEnabled(True)
        self.selectFolderButton.setEnabled(True)
        self.singleRadio.setEnabled(True)
        self.multipleRadio.setEnabled(True)
        self.maxBackupsSpinBox.setEnabled(True)

        # Reset window title
        self.setWindowTitle("Auto Save and Backup")

        # Remove toolbar timer
        self.remove_toolbar_timer()

        # Hide tray icon
        if self.tray_icon:
            self.tray_icon.hide()

        self.countdownLabel.setText("Next Backup: Not scheduled")
        self.countdownLabel.setStyleSheet("color: #666; font-style: italic;")
        self.show_message("Auto backup stopped", level=Qgis.Info, duration=2)

        # Reset session log path
        self.session_log_path = None

    def update_countdown(self):
        self.remaining_time -= 1000
        minutes = self.remaining_time // 60000
        seconds = (self.remaining_time % 60000) // 1000

        # Show warning 10 seconds before backup
        if self.remaining_time <= 10000 and not self.warning_shown:
            message = "Backup will occur in 10 seconds..."
            self.show_message(message, level=Qgis.Info, duration=2)

            if self.tray_icon and self.isMinimized():
                try:
                    self.tray_icon.showMessage(
                        "QGIS Backup Alert",
                        message,
                        QSystemTrayIcon.MessageIcon.Information,
                        5000
                    )
                except:
                    self.tray_icon.showMessage(
                        "QGIS Backup Alert",
                        message,
                        QSystemTrayIcon.Information,
                        5000
                    )

            self.warning_shown = True

        countdown_text = "Next Backup: {:02d}:{:02d}".format(minutes, seconds)
        status_text = "Active"

        if self.last_backup_time:
            elapsed = datetime.datetime.now() - self.last_backup_time
            if elapsed.total_seconds() < 2:
                status = "Last backup: Just now"
            else:
                status = "Last backup: {} seconds ago".format(
                    int(elapsed.total_seconds()))
            countdown_text = "{} | {}".format(countdown_text, status)

            if elapsed.total_seconds() < 60:
                status_text = "Just backed up"
            else:
                status_text = "Active"

        self.countdownLabel.setText(countdown_text)
        self.countdownLabel.setStyleSheet("color: #2196F3;")

        # Update window title with countdown
        self.setWindowTitle(
            "Auto Save and Backup - {:02d}:{:02d}".format(minutes, seconds))

        # Update toolbar timer
        if self.toolbar_widget:
            self.toolbar_widget.update_timer(minutes, seconds)
            self.toolbar_widget.update_status(status_text)

        # Emit signal for toolbar update
        self.toolbarTimerUpdate.emit(minutes, seconds, status_text)

        # Update tray icon tooltip when minimized
        if self.tray_icon:
            if self.isMinimized():
                self.tray_icon.setToolTip(
                    "QGIS Backup\n{}".format(countdown_text))
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
            print("Error calculating hash for {}: {}".format(filepath, str(e)))
            return None

    def load_backup_history(self):
        """Load backup history from JSON file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    self.backup_history = json.load(f)
        except Exception as e:
            self.show_message(
                "Failed to load backup history: {}".format(str(e)), level=Qgis.Warning, duration=2)
            self.backup_history = {}

    def save_backup_history(self):
        """Save backup history to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self.backup_history, f, indent=4)
        except Exception as e:
            self.show_message(
                "Failed to save backup history: {}".format(str(e)), level=Qgis.Warning, duration=2)

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
                and d.startswith("{}_Backup_".format(safe_project_name))
            ]

            if len(backup_folders) > self.maxBackupsSpinBox.value():
                backup_folders.sort()
                for folder in backup_folders[:-self.maxBackupsSpinBox.value()]:
                    try:
                        shutil.rmtree(os.path.join(backup_root, folder))
                    except Exception as e:
                        self.show_message(
                            "Failed to remove old backup {}: {}".format(
                                folder, str(e)),
                            level=Qgis.Warning, duration=2)
        except Exception as e:
            self.show_message(
                "Error during backup cleanup: {}".format(str(e)), level=Qgis.Warning, duration=2)

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
            print("Error checking file {}: {}".format(source_file, str(e)))
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

        commit_failed = []
        try:
            for layer in project.mapLayers().values():
                if isinstance(layer, QgsVectorLayer) and layer.isEditable():
                    if not layer.commitChanges():
                        commit_failed.append(layer.name())
                        errors = layer.commitErrors()
                        print("Failed to commit {}: {}".format(
                            layer.name(), errors))
        except Exception as e:
            self.show_message(
                "Error committing layer changes: {}".format(str(e)), level=Qgis.Critical, duration=2)
            self.stop_backup()
            return

        if commit_failed:
            self.show_message(
                "Failed to commit changes for layers: {}".format(
                    ', '.join(commit_failed)),
                level=Qgis.Warning, duration=2)

        try:
            if not project.write():
                raise Exception("Failed to save project")
        except Exception as e:
            self.show_message(
                "Failed to save project: {}".format(str(e)), level=Qgis.Critical, duration=2)
            self.stop_backup()
            return

        project_path = project.fileName()
        if not project_path:
            self.show_message(
                "Backup failed: Project not saved", level=Qgis.Critical, duration=2)
            self.stop_backup()
            return

        project_name = os.path.splitext(os.path.basename(project_path))[0]
        safe_project_name = "".join(
            c for c in project_name if c.isalnum() or c in (' ', '-', '_')).strip()

        if not safe_project_name:
            safe_project_name = "Project"

        if self.multipleRadio.isChecked():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_folder = os.path.join(
                self.backupFolderPath.text(), "{}_Backup_{}".format(safe_project_name, timestamp))
        else:
            backup_folder = os.path.join(
                self.backupFolderPath.text(), "{}_Latest_Backup".format(safe_project_name))

        backup_summary = []
        backup_errors = []

        try:
            os.makedirs(backup_folder, exist_ok=True)

            project_filename = os.path.basename(project_path)
            project_backup_path = os.path.join(backup_folder, project_filename)

            try:
                self.copy_file_with_retry(project_path, project_backup_path)
                backup_summary.append("Project file")
            except Exception as e:
                backup_errors.append(
                    "Failed to backup project file: {}".format(str(e)))

            selected_layers = []
            checked_state = get_qt_checkstate_checked()

            for i in range(self.layerListWidget.count()):
                item = self.layerListWidget.item(i)
                try:
                    if item.checkState() == checked_state or item.checkState() == checked_state.value:
                        selected_layers.append(item.text())
                except AttributeError:
                    if item.checkState() == checked_state:
                        selected_layers.append(item.text())

            if selected_layers:
                for layer_name in selected_layers:
                    layers = project.mapLayersByName(layer_name)
                    if layers:
                        layer = layers[0]

                        if layer.providerType() not in ['ogr', 'spatialite', 'gpkg']:
                            continue

                        force_backup = layer.isEditable() and layer.isModified()

                        layer_source = layer.source()
                        try:
                            if self.backup_vector_layer(
                                    layer_source, backup_folder, layer_name, force_backup):
                                backup_summary.append(layer_name)
                        except Exception as e:
                            backup_errors.append(
                                "Failed to backup layer {}: {}".format(layer_name, str(e)))

            if not self.multipleRadio.isChecked():
                self.save_backup_history()

        except Exception as e:
            backup_errors.append("General backup error: {}".format(str(e)))

        finally:
            # Write backup log
            self.show_message("Writing backup log...",
                              level=Qgis.Info, duration=2)
            log_path = os.path.join(backup_folder, "backup_log.txt")
            try:
                with open(log_path, 'w') as f:
                    f.write("Backup Summary\n")
                    f.write("="*20 + "\n")
                    f.write("Timestamp: {}\n".format(
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    f.write("Project: {}\n".format(project_name))
                    if backup_summary:
                        f.write("\nBacked up files:\n")
                        for item in backup_summary:
                            f.write("- {}\n".format(item))
                    if backup_errors:
                        f.write("\nErrors:\n")
                        for err in backup_errors:
                            f.write("- {}\n".format(err))
                self.show_message("Backup log written to: {}".format(
                    log_path), level=Qgis.Info, duration=2)
            except Exception as e:
                self.show_message(
                    "Failed to write backup log: {}".format(str(e)), level=Qgis.Warning, duration=2)

        if backup_errors:
            summary_message = "Backup completed with errors. See log for details."
            level = Qgis.Warning
        else:
            if len(backup_summary) == 1:
                summary_message = "Backup completed: Project file only"
            else:
                layer_names = [
                    item for item in backup_summary if item != "Project file"]
                summary_message = "Backup completed: Project and layers: {}".format(
                    ', '.join(layer_names))
            level = Qgis.Success

        self.show_message(summary_message, level=level)

        # Update toolbar widget
        try:
            if self.toolbar_widget:
                self.toolbar_widget.update_status("Backing up...")
                QTimer.singleShot(1000, lambda: self.toolbar_widget.update_status(
                    "Complete!") if self.toolbar_widget else None)
                QTimer.singleShot(3000, lambda: self.toolbar_widget.update_status(
                    "Active") if self.toolbar_widget else None)

            if self.tray_icon and self.isMinimized():
                try:
                    self.tray_icon.showMessage(
                        "QGIS Backup Complete",
                        summary_message,
                        QSystemTrayIcon.MessageIcon.Information if not backup_errors else QSystemTrayIcon.MessageIcon.Warning,
                        3000
                    )
                except:
                    self.tray_icon.showMessage(
                        "QGIS Backup Complete",
                        summary_message,
                        QSystemTrayIcon.Information if not backup_errors else QSystemTrayIcon.Warning,
                        3000
                    )
        except Exception as e:
            print("Could not show notification: {}".format(str(e)))

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
                            print("Error updating history for {}: {}".format(
                                source_file, str(e)))

                except Exception as e:
                    self.show_message(
                        "Failed to copy {}: {}".format(
                            os.path.basename(source_file), str(e)),
                        level=Qgis.Warning, duration=2)

            return backed_up

        except Exception as e:
            self.show_message(
                "Failed to backup layer {}: {}".format(layer_name, str(e)), level=Qgis.Critical, duration=2)
            raise

    def on_layers_added(self, layers):
        """Handle new layers being added to the project"""
        if not self.is_visible:
            return

        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.id() not in self.current_layers:
                self.current_layers.add(layer.id())
                item = QListWidgetItem(layer.name())
                item.setData(get_qt_user_role(), layer.id())
                item.setCheckState(get_qt_checkstate_unchecked())
                self.layerListWidget.addItem(item)
                self.show_message("New layer added: {}".format(
                    layer.name()), level=Qgis.Info, duration=2)

    def on_layers_removed(self, layer_ids):
        """Handle layers being removed from the project"""
        if not self.is_visible:
            return

        for layer_id in layer_ids:
            if layer_id in self.current_layers:
                self.current_layers.remove(layer_id)
                for i in range(self.layerListWidget.count()):
                    item = self.layerListWidget.item(i)
                    if item.data(get_qt_user_role()) == layer_id:
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

        # Clean up toolbar timer
        self.remove_toolbar_timer()

        # Clean up tray icon
        if self.tray_icon:
            self.tray_icon.hide()

        super().closeEvent(event)

    def show_message(self, message, level=Qgis.Info, duration=2):
        """Display a message in QGIS's message bar and log panel"""
        if hasattr(self, 'iface') and self.iface and self.iface.messageBar():
            duration = 2
            self.iface.messageBar().pushMessage("Backup", message, level, duration)
        else:
            level_text = {
                Qgis.Info: "INFO",
                Qgis.Warning: "WARNING",
                Qgis.Critical: "CRITICAL",
                Qgis.Success: "SUCCESS"
            }.get(level, "INFO")
            print("[Backup {}] {}".format(level_text, message))

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
                print(f"Failed to write to session log: {str(e)}")

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
        self.startButton.setEnabled(True)
        self.stopButton.setEnabled(False)
        self.backupNowButton.setEnabled(True)
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
                "Backup mode changed. Previous backups preserved.", level=Qgis.Info, duration=2)

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
                    "Failed to open folder: {}".format(str(e)), level=Qgis.Warning, duration=2)


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
