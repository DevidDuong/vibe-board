"""Design tokens, QSS, and light/dark/system theme switching. Pure Qt (portable)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTemporaryDir, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from clipflow.ui.icons import glyph_pixmap

# Spacing scale (logical px; Qt scales for Retina / display scaling).
SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_5 = 4, 8, 12, 16, 24
RADIUS_CARD = 10
RADIUS_CONTROL = 8


@dataclass(frozen=True, slots=True)
class Theme:
    name: str
    bg: str
    surface: str
    code_bg: str
    hover: str
    selected: str
    border: str
    text: str
    muted: str
    accent: str
    on_accent: str
    success: str
    danger: str
    danger_bg: str

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


DARK = Theme(
    name="dark",
    bg="#10131B",
    surface="#1A1F2A",
    code_bg="#131824",
    hover="#242D3B",
    selected="#252E4A",
    border="#333C4C",
    text="#F4F6FB",
    muted="#A1AABA",
    accent="#8295FF",
    on_accent="#0B0E15",
    success="#53C6A0",
    danger="#F07178",
    danger_bg="#3A1E24",
)

LIGHT = Theme(
    name="light",
    bg="#F7F8FB",
    surface="#FFFFFF",
    code_bg="#F2F4F8",
    hover="#EEF1F7",
    selected="#E8EBFD",
    border="#E2E6EF",
    text="#1B2433",
    muted="#606A7C",  # spec #667184, darkened for AA on selected cards
    accent="#5669E9",
    on_accent="#FFFFFF",
    success="#17795A",
    danger="#C5363E",
    danger_bg="#FDECEE",
)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.x contrast ratio between two hex colors."""

    def luminance(hex_color: str) -> float:
        color = QColor(hex_color)
        channels = []
        for value in (color.redF(), color.greenF(), color.blueF()):
            channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
        r, g, b = channels
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    hi, lo = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def build_palette(t: Theme) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.bg,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.surface,
        QPalette.ColorRole.AlternateBase: t.code_bg,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.surface,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.on_accent,
        QPalette.ColorRole.PlaceholderText: t.muted,
        QPalette.ColorRole.ToolTipBase: t.surface,
        QPalette.ColorRole.ToolTipText: t.text,
        QPalette.ColorRole.Link: t.accent,
        QPalette.ColorRole.BrightText: t.danger,
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.muted))
    return palette


def _combo_arrow_qss(chevron: str | None) -> str:
    if not chevron:
        return ""
    return (
        "QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right;"
        " width: 24px; border: none; background: transparent; }\n"
        f'QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}\n'
    )


def build_qss(t: Theme, chevron: str | None = None) -> str:
    return (
        _combo_arrow_qss(chevron)
        + f"""
QWidget#paletteRoot, QDialog {{ background: {t.bg}; }}
QWidget {{ color: {t.text}; }}
QLabel#muted, QLabel#hint, QLabel#count {{ color: {t.muted}; }}
QLabel#heading {{ font-size: 15px; font-weight: 600; }}
QLabel#sectionTitle {{ font-weight: 600; color: {t.muted}; }}
QLabel#detailTitle {{ font-size: 16px; font-weight: 600; }}
QLabel#emptyTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#fieldLabel {{ font-weight: 600; }}
QLabel#fieldHint {{ color: {t.muted}; }}
QLabel#formError {{ color: {t.danger}; }}

QLineEdit, QPlainTextEdit, QComboBox {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {RADIUS_CONTROL}px;
    padding: 6px 10px;
    selection-background-color: {t.accent};
    selection-color: {t.on_accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 2px solid {t.accent};
    padding: 5px 9px;
}}
QLineEdit#search {{
    font-size: 16px;
    padding: 10px 12px;
    border-radius: {RADIUS_CARD}px;
}}
QLineEdit#search:focus {{ padding: 9px 11px; }}
QPlainTextEdit#codeView, QPlainTextEdit#commandInput {{ background: {t.code_bg}; }}
QComboBox QAbstractItemView {{
    background: {t.surface};
    border: 1px solid {t.border};
    selection-background-color: {t.hover};
    selection-color: {t.text};
}}

QPushButton {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {RADIUS_CONTROL}px;
    padding: 6px 12px;
    min-height: 20px;
}}
QPushButton:hover {{ background: {t.hover}; }}
QPushButton:pressed {{ background: {t.selected}; }}
QPushButton:focus {{ border: 2px solid {t.accent}; padding: 5px 11px; }}
QPushButton:disabled {{ color: {t.muted}; background: transparent; border-color: {t.border}; }}
QPushButton#primary {{
    background: {t.accent};
    color: {t.on_accent};
    border: 1px solid {t.accent};
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {QColor(t.accent).lighter(108).name()}; }}
QPushButton#primary:focus {{ border: 2px solid {t.text}; }}
QPushButton#primary:disabled {{
    background: {t.border}; border-color: {t.border}; color: {t.muted};
}}
QPushButton#danger {{ color: {t.danger}; }}
QPushButton#danger:disabled {{ color: {t.muted}; }}
QPushButton#iconButton {{ background: transparent; border: 1px solid transparent; padding: 6px; }}
QPushButton#iconButton:hover {{ background: {t.hover}; }}
QPushButton#iconButton:focus {{ border: 2px solid {t.accent}; padding: 5px; }}
QPushButton#chip {{
    background: transparent;
    color: {t.muted};
    border: 1px solid {t.border};
    border-radius: 13px;
    padding: 3px 12px;
    min-height: 18px;
}}
QPushButton#chip:hover {{ background: {t.hover}; color: {t.text}; }}
QPushButton#chip:checked {{
    background: {t.accent};
    color: {t.on_accent};
    border-color: {t.accent};
    font-weight: 600;
}}
QPushButton#chip:focus {{ border: 2px solid {t.text}; padding: 2px 11px; }}

QListView#commandList {{ background: transparent; border: none; outline: none; }}
QFrame#detailPane {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {RADIUS_CARD + 2}px;
}}
QFrame#banner {{
    background: {t.danger_bg};
    border: 1px solid {t.danger};
    border-radius: {RADIUS_CONTROL}px;
}}
QFrame#toast {{
    background: {t.surface};
    border: 1px solid {t.success};
    border-radius: {RADIUS_CARD}px;
}}
QLabel#toastText {{ color: {t.text}; font-weight: 600; }}
QFrame#secretNote {{
    background: {t.code_bg};
    border: 1px solid {t.border};
    border-radius: {RADIUS_CONTROL}px;
}}
QScrollArea#chipScroller {{ background: transparent; border: none; }}
QScrollArea#chipScroller > QWidget > QWidget {{ background: transparent; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 3px; min-height: 28px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 1px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 3px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {RADIUS_CONTROL}px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.hover}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 8px; }}
QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; padding: 4px; }}
QCheckBox {{ spacing: 8px; }}
"""
    )


class ThemeManager(QObject):
    """Applies the resolved theme app-wide and follows the OS appearance in "system" mode."""

    theme_changed = Signal(object)  # Theme

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._mode = "system"
        self.theme: Theme = LIGHT
        # Private, auto-removed folder for generated style images (combo-box chevrons).
        self._assets = QTemporaryDir()
        app.setStyle("Fusion")  # consistent, fully stylable rendering on macOS and Windows
        app.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> Theme:
        self._mode = mode if mode in ("system", "light", "dark") else "system"
        hints = self._app.styleHints()
        # Forcing the scheme also makes native chrome (title bar, standard dialogs) match.
        if self._mode == "dark":
            hints.setColorScheme(Qt.ColorScheme.Dark)
        elif self._mode == "light":
            hints.setColorScheme(Qt.ColorScheme.Light)
        else:
            hints.unsetColorScheme()
        return self._apply()

    def _resolve(self) -> Theme:
        if self._mode == "dark":
            return DARK
        if self._mode == "light":
            return LIGHT
        return DARK if self.system_scheme() == Qt.ColorScheme.Dark else LIGHT

    def system_scheme(self) -> Qt.ColorScheme:
        return QGuiApplication.styleHints().colorScheme()

    def _apply(self) -> Theme:
        theme = self._resolve()
        self.theme = theme
        self._app.setPalette(build_palette(theme))
        self._app.setStyleSheet(build_qss(theme, self._chevron(theme)))
        self.theme_changed.emit(theme)
        return theme

    def _chevron(self, theme: Theme) -> str | None:
        if not self._assets.isValid():
            return None
        base = Path(self._assets.path()) / f"chevron-{theme.name}"
        for suffix, dpr in (("", 1.0), ("@2x", 2.0)):
            target = Path(f"{base}{suffix}.png")
            if not target.exists():
                glyph_pixmap("chevron", theme.muted, 12, dpr).save(str(target))
        return f"{base}.png"

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._mode == "system":
            self._apply()
