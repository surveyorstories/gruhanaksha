"""
Shared Qt5/Qt6 compatibility layer for Gruhanaksha plugin.
"""
from qgis.PyQt import QtCore, QtGui, QtWidgets
try:
    from qgis.PyQt.QtCore import Qt, QObject, pyqtSignal, QTimer, QSize, QEvent, QVariant, QPointF
except ImportError:
    from qgis.PyQt.QtCore import Qt, QObject, pyqtSignal, QTimer, QSize, QEvent, QPointF
    QVariant = None
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QMenu, QSystemTrayIcon, QFrame,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
    QFileDialog, QRadioButton, QButtonGroup, QListWidget,
    QListWidgetItem, QCheckBox, QTextEdit, QTabWidget, QGraphicsTextItem,
    QMainWindow, QToolBar, QSizePolicy, QDialog, QComboBox, QLineEdit,
    QInputDialog, QDialogButtonBox, QFormLayout, QActionGroup
)
from qgis.PyQt.QtGui import QIcon, QFont, QColor, QPen, QBrush


class QtCompat:
    """Helper class to abstract differences between Qt5 and Qt6 enums."""

    @staticmethod
    def _get_attr(obj, *names):
        """Helper to try multiple attribute names, supporting dot notation."""
        for name in names:
            try:
                current_obj = obj
                for part in name.split('.'):
                    current_obj = getattr(current_obj, part)
                return current_obj
            except AttributeError:
                continue

        # Fallback to re-raising the first attempt's error if nothing worked
        current_obj = obj
        for part in names[0].split('.'):
            current_obj = getattr(current_obj, part)
        return current_obj

    # --- Window Flags (Methods) ---
    @classmethod
    def window_flags(cls):
        """Return standard window flags (Qt5/Qt6 compatible)."""
        if hasattr(Qt, 'WindowType'):  # Qt6
            return (Qt.WindowType.Window | Qt.WindowType.WindowTitleHint |
                    Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint |
                    Qt.WindowType.CustomizeWindowHint)
        # Qt5
        return (Qt.Window | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint |
                Qt.WindowCloseButtonHint | Qt.CustomizeWindowHint)

    @classmethod
    def tool_window_flags(cls):
        """Return tool window flags (Qt5/Qt6 compatible)."""
        if hasattr(Qt, 'WindowType'):  # Qt6
            return (Qt.WindowType.Tool | Qt.WindowType.WindowTitleHint |
                    Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.CustomizeWindowHint)
        else:  # Qt5
            return (Qt.Tool | Qt.WindowTitleHint |
                    Qt.WindowCloseButtonHint | Qt.CustomizeWindowHint)

    @classmethod
    def stay_on_top(cls):
        """Return WindowStaysOnTopHint (Qt5/Qt6 compatible)."""
        if hasattr(Qt, 'WindowType'):
            return Qt.WindowType.WindowStaysOnTopHint
        return Qt.WindowStaysOnTopHint

    # --- CheckState (Methods) ---
    @classmethod
    def checked(cls):
        return cls._get_attr(Qt, 'Checked', 'CheckState.Checked')

    @classmethod
    def unchecked(cls):
        return cls._get_attr(Qt, 'Unchecked', 'CheckState.Unchecked')

    # --- ItemFlag (Methods) ---
    @classmethod
    def item_is_user_checkable(cls):
        return cls._get_attr(Qt, 'ItemIsUserCheckable', 'ItemFlag.ItemIsUserCheckable')

    # --- CursorShape (Methods) ---
    @classmethod
    def pointing_cursor(cls):
        return cls._get_attr(Qt, 'PointingHandCursor', 'CursorShape.PointingHandCursor')

    @classmethod
    def cross_cursor(cls):
        return cls._get_attr(Qt, 'CrossCursor', 'CursorShape.CrossCursor')

    @classmethod
    def arrow_cursor(cls):
        return cls._get_attr(Qt, 'ArrowCursor', 'CursorShape.ArrowCursor')

    @classmethod
    def closed_hand_cursor(cls):
        return cls._get_attr(Qt, 'ClosedHandCursor', 'CursorShape.ClosedHandCursor')

    @classmethod
    def pointing_hand_cursor(cls):
        return cls._get_attr(Qt, 'PointingHandCursor', 'CursorShape.PointingHandCursor')

    @classmethod
    def text_interaction(cls):
        return cls._get_attr(Qt, 'TextSelectableByMouse', 'TextInteractionFlag.TextSelectableByMouse')

    # --- Generic Helper Methods ---
    @classmethod
    def get_cursor_shape(cls, name):
        """Get cursor shape by name (e.g., 'CrossCursor', 'ArrowCursor')."""
        return cls._get_attr(Qt, name, f'CursorShape.{name}')

    @classmethod
    def get_key(cls, name):
        """Get key enum by name (e.g., 'Key_Escape', 'Key_Return')."""
        return cls._get_attr(Qt, name, f'Key.{name}')

    @classmethod
    def get_mouse_button(cls, name):
        """Get mouse button enum by name (e.g., 'LeftButton', 'RightButton')."""
        return cls._get_attr(Qt, name, f'MouseButton.{name}')

    @classmethod
    def get_alignment(cls, name):
        """Get alignment flag by name (e.g., 'AlignTop', 'AlignCenter')."""
        return cls._get_attr(Qt, name, f'AlignmentFlag.{name}')

    # --- SizePolicy (Methods) ---
    @classmethod
    def size_policy_minimum(cls):
        return cls._get_attr(QSizePolicy, 'Minimum', 'Policy.Minimum')

    @classmethod
    def size_policy_preferred(cls):
        return cls._get_attr(QSizePolicy, 'Preferred', 'Policy.Preferred')

    @classmethod
    def size_policy_expanding(cls):
        return cls._get_attr(QSizePolicy, 'Expanding', 'Policy.Expanding')

    # --- Utils (Methods) ---
    @classmethod
    def question(cls, parent, title, text, buttons=None, default=None):
        """Wrapper for QMessageBox.question which changed signature slightly or enum usage."""
        return QMessageBox.question(parent, title, text, buttons, default)

    @classmethod
    def message_box_question(cls, parent, title, text, buttons=None, default=None):
        """Alias for question() method for compatibility."""
        return cls.question(parent, title, text, buttons, default)

    @classmethod
    def exec(cls, obj):
        """Handle exec_ vs exec difference."""
        if hasattr(obj, 'exec'):
            return obj.exec()
        else:
            return obj.exec_()

    @classmethod
    def hline(cls):
        """Return HLine shape for QFrame."""
        return cls.HLine

    @classmethod
    def sunken(cls):
        """Return Sunken shadow for QFrame."""
        return cls.Sunken

    @classmethod
    def user_role(cls):
        """Return UserRole enum."""
        return cls._get_attr(Qt, 'UserRole', 'ItemDataRole.UserRole')

    @classmethod
    def info_icon(cls):
        """Return Information icon for QSystemTrayIcon."""
        return cls._get_attr(QSystemTrayIcon, 'Information', 'MessageIcon.Information')

    @classmethod
    def warning_icon(cls):
        """Return Warning icon for QSystemTrayIcon."""
        return cls._get_attr(QSystemTrayIcon, 'Warning', 'MessageIcon.Warning')

    @classmethod
    def double_click(cls):
        """Return DoubleClick for QSystemTrayIcon."""
        return cls._get_attr(QSystemTrayIcon, 'DoubleClick', 'ActivationReason.DoubleClick')

    @classmethod
    def frame_shape(cls, shape):
        """Get frame shape by name (e.g. 'styledpanel', 'hline', 'box')."""
        # Map common names to QFrame attributes
        shape = shape.lower()
        mapping = {
            'hline': 'HLine',
            'vline': 'VLine',
            'styledpanel': 'StyledPanel',
            'plain': 'Plain',
            'raised': 'Raised',
            'sunken': 'Sunken',
            'box': 'Box',
            'panel': 'Panel',
            'noframe': 'NoFrame'
        }

        qt_name = mapping.get(shape, 'NoFrame')

        # Try finding it in QFrame.Shape (Qt6) or QFrame (Qt5)
        # Note: Some might be shapes, some shadows, but typically frame_shape is used for Shape.
        return cls._get_attr(QFrame, qt_name, f'Shape.{qt_name}')


# --- Attributes (Values) ---
# Populated dynamically to ensure they are values, not methods/properties
# WindowType
QtCompat.Window = QtCompat._get_attr(Qt, 'Window', 'WindowType.Window')
QtCompat.WindowTitleHint = QtCompat._get_attr(
    Qt, 'WindowTitleHint', 'WindowType.WindowTitleHint')
QtCompat.WindowMinimizeButtonHint = QtCompat._get_attr(
    Qt, 'WindowMinimizeButtonHint', 'WindowType.WindowMinimizeButtonHint')
QtCompat.WindowCloseButtonHint = QtCompat._get_attr(
    Qt, 'WindowCloseButtonHint', 'WindowType.WindowCloseButtonHint')
QtCompat.CustomizeWindowHint = QtCompat._get_attr(
    Qt, 'CustomizeWindowHint', 'WindowType.CustomizeWindowHint')
QtCompat.WindowStaysOnTopHint = QtCompat._get_attr(
    Qt, 'WindowStaysOnTopHint', 'WindowType.WindowStaysOnTopHint')

# MouseButton
QtCompat.LeftButton = QtCompat._get_attr(
    Qt, 'LeftButton', 'MouseButton.LeftButton')
QtCompat.RightButton = QtCompat._get_attr(
    Qt, 'RightButton', 'MouseButton.RightButton')

# KeyboardModifier
QtCompat.ControlModifier = QtCompat._get_attr(
    Qt, 'ControlModifier', 'KeyboardModifier.ControlModifier')
QtCompat.AltModifier = QtCompat._get_attr(
    Qt, 'AltModifier', 'KeyboardModifier.AltModifier')

# Key
QtCompat.Key_Escape = QtCompat._get_attr(Qt, 'Key_Escape', 'Key.Key_Escape')
QtCompat.Key_Backspace = QtCompat._get_attr(
    Qt, 'Key_Backspace', 'Key.Key_Backspace')
QtCompat.Key_Delete = QtCompat._get_attr(Qt, 'Key_Delete', 'Key.Key_Delete')
QtCompat.Key_Return = QtCompat._get_attr(Qt, 'Key_Return', 'Key.Key_Return')
QtCompat.Key_Enter = QtCompat._get_attr(Qt, 'Key_Enter', 'Key.Key_Enter')
QtCompat.Key_Z = QtCompat._get_attr(Qt, 'Key_Z', 'Key.Key_Z')
QtCompat.Key_Y = QtCompat._get_attr(Qt, 'Key_Y', 'Key.Key_Y')
QtCompat.Key_L = QtCompat._get_attr(Qt, 'Key_L', 'Key.Key_L')

# StandardButton
QtCompat.Yes = QtCompat._get_attr(QMessageBox, 'Yes', 'StandardButton.Yes')
QtCompat.No = QtCompat._get_attr(QMessageBox, 'No', 'StandardButton.No')
QtCompat.Cancel = QtCompat._get_attr(
    QMessageBox, 'Cancel', 'StandardButton.Cancel')
QtCompat.Ok = QtCompat._get_attr(QMessageBox, 'Ok', 'StandardButton.Ok')

# ItemDataRole
QtCompat.UserRole = QtCompat._get_attr(Qt, 'UserRole', 'ItemDataRole.UserRole')

# AlignmentFlag
QtCompat.AlignLeft = QtCompat._get_attr(
    Qt, 'AlignLeft', 'AlignmentFlag.AlignLeft')
QtCompat.AlignRight = QtCompat._get_attr(
    Qt, 'AlignRight', 'AlignmentFlag.AlignRight')
QtCompat.AlignCenter = QtCompat._get_attr(
    Qt, 'AlignCenter', 'AlignmentFlag.AlignCenter')
QtCompat.AlignTop = QtCompat._get_attr(
    Qt, 'AlignTop', 'AlignmentFlag.AlignTop')

# TextInteractionFlag
QtCompat.TextSelectableByMouse = QtCompat._get_attr(
    Qt, 'TextSelectableByMouse', 'TextInteractionFlag.TextSelectableByMouse')

# Frame Shape/Shadow
QtCompat.HLine = QtCompat._get_attr(QFrame, 'HLine', 'Shape.HLine')
QtCompat.Sunken = QtCompat._get_attr(QFrame, 'Sunken', 'Shadow.Sunken')

# ScrollBarPolicy
QtCompat.ScrollBarAlwaysOff = QtCompat._get_attr(
    Qt, 'ScrollBarAlwaysOff', 'ScrollBarPolicy.ScrollBarAlwaysOff')
QtCompat.ScrollBarAlwaysOn = QtCompat._get_attr(
    Qt, 'ScrollBarAlwaysOn', 'ScrollBarPolicy.ScrollBarAlwaysOn')
QtCompat.ScrollBarAsNeeded = QtCompat._get_attr(
    Qt, 'ScrollBarAsNeeded', 'ScrollBarPolicy.ScrollBarAsNeeded')

# SystemTrayIcon
QtCompat.DoubleClick = QtCompat._get_attr(
    QSystemTrayIcon, 'DoubleClick', 'ActivationReason.DoubleClick')
QtCompat.Information = QtCompat._get_attr(
    QSystemTrayIcon, 'Information', 'MessageIcon.Information')
QtCompat.Warning = QtCompat._get_attr(
    QSystemTrayIcon, 'Warning', 'MessageIcon.Warning')

# BrushStyle
QtCompat.NoBrush = QtCompat._get_attr(Qt, 'NoBrush', 'BrushStyle.NoBrush')

# PenStyle
QtCompat.DashLine = QtCompat._get_attr(Qt, 'DashLine', 'PenStyle.DashLine')
QtCompat.DotLine = QtCompat._get_attr(Qt, 'DotLine', 'PenStyle.DotLine')

# DialogCode
QtCompat.Ok = QtCompat._get_attr(QMessageBox, 'Ok', 'StandardButton.Ok')

# QMessageBox Icons (override QSystemTrayIcon icons for QMessageBox usage)
# Note: Warning and Information already defined for QSystemTrayIcon above.
# For QMessageBox we'll update them here:
QtCompat.Warning = QtCompat._get_attr(QMessageBox, 'Warning', 'Icon.Warning')
QtCompat.Information = QtCompat._get_attr(
    QMessageBox, 'Information', 'Icon.Information')
QtCompat.Question = QtCompat._get_attr(
    QMessageBox, 'Question', 'Icon.Question')
QtCompat.Critical = QtCompat._get_attr(
    QMessageBox, 'Critical', 'Icon.Critical')

# QMessageBox ButtonRole
QtCompat.AcceptRole = QtCompat._get_attr(
    QMessageBox, 'AcceptRole', 'ButtonRole.AcceptRole')
QtCompat.RejectRole = QtCompat._get_attr(
    QMessageBox, 'RejectRole', 'ButtonRole.RejectRole')
QtCompat.DestructiveRole = QtCompat._get_attr(
    QMessageBox, 'DestructiveRole', 'ButtonRole.DestructiveRole')

# QDialogButtonBox StandardButtons
QtCompat.DialogOk = QtCompat._get_attr(
    QDialogButtonBox, 'Ok', 'StandardButton.Ok')
QtCompat.DialogCancel = QtCompat._get_attr(
    QDialogButtonBox, 'Cancel', 'StandardButton.Cancel')
QtCompat.DialogButtonDestructiveRole = QtCompat._get_attr(
    QDialogButtonBox, 'DestructiveRole', 'ButtonRole.DestructiveRole')

# QDialog DialogCodes
QtCompat.DialogAccepted = QtCompat._get_attr(
    QDialog, 'Accepted', 'DialogCode.Accepted')
QtCompat.DialogRejected = QtCompat._get_attr(
    QDialog, 'Rejected', 'DialogCode.Rejected')

# Event
QtCompat.Resize = QtCompat._get_attr(QEvent, 'Resize', 'Type.Resize')

# ItemFlag
QtCompat.ItemIsUserCheckable = QtCompat._get_attr(
    Qt, 'ItemIsUserCheckable', 'ItemFlag.ItemIsUserCheckable')

# QSizePolicy
QtCompat.Expanding = QtCompat._get_attr(
    QSizePolicy, 'Expanding', 'Policy.Expanding')
QtCompat.Preferred = QtCompat._get_attr(
    QSizePolicy, 'Preferred', 'Policy.Preferred')
QtCompat.Minimum = QtCompat._get_attr(QSizePolicy, 'Minimum', 'Policy.Minimum')
