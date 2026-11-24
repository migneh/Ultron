"""
core/ui_design.py — Ultron design system & modern component helpers.

Centralizes the visual language so the whole HUD speaks one dialect:
  * Typography scale (font families, sizes, weights, line heights)
  * Spacing scale (consistent margins/padding/gaps)
  * Component variants (primary/secondary/ghost/danger buttons, input states)
  * Glassmorphism panels (translucent backgrounds with hairline borders)
  * Toast notification system (non-blocking, auto-dismiss)
  * Focus-ring management (keyboard navigation accessibility)
  * WCAG AA contrast-safe colour tokens

All colours are expressed as hex strings; widgets apply them via QSS so the
accent-tinting pipeline in ui.py keeps working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import (
    QPropertyAnimation, QEasingCurve, QTimer, Qt, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSlider,
    QTextEdit, QVBoxLayout, QWidget,
)

# ═════════════════════════════════════════════════════════════════════════════
# 1. TYPOGRAPHY SCALE
# ═════════════════════════════════════════════════════════════════════════════

FONT_MONO = "Courier New"
FONT_SANS = "Inter, SF Pro Text, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"


@dataclass(frozen=True)
class TypeToken:
    family: str
    size: int
    weight: QFont.Weight
    line_height: float


TYPE_CAPTION = TypeToken(FONT_MONO, 7, QFont.Weight.Normal, 1.2)
TYPE_SMALL = TypeToken(FONT_MONO, 8, QFont.Weight.Normal, 1.3)
TYPE_BODY = TypeToken(FONT_MONO, 9, QFont.Weight.Normal, 1.4)
TYPE_MEDIUM = TypeToken(FONT_MONO, 10, QFont.Weight.Medium, 1.4)
TYPE_HEADING = TypeToken(FONT_MONO, 11, QFont.Weight.Bold, 1.2)
TYPE_DISPLAY = TypeToken(FONT_MONO, 13, QFont.Weight.Bold, 1.1)


def font(token: TypeToken) -> QFont:
    """Build a QFont from a TypeToken."""
    f = QFont(token.family, token.size)
    f.setWeight(token.weight)
    return f


# ═════════════════════════════════════════════════════════════════════════════
# 2. SPACING SCALE
# ═════════════════════════════════════════════════════════════════════════════

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 20
SPACE_2XL = 24


# ═════════════════════════════════════════════════════════════════════════════
# 3. PALETTE ACCESS
# ═════════════════════════════════════════════════════════════════════════════

def _colors() -> dict:
    """Read current palette from ui.C (imported lazily to avoid cycles)."""
    from ui import C
    return {
        "PRI": C.PRI, "PRI_DIM": C.PRI_DIM, "ACC": C.ACC,
        "TEXT": C.TEXT, "TEXT_MED": C.TEXT_MED, "TEXT_DIM": C.TEXT_DIM,
        "BG": C.BG, "PANEL": C.PANEL, "PANEL2": C.PANEL2,
        "BORDER": C.BORDER, "BORDER_B": C.BORDER_B,
        "GREEN": C.GREEN, "GREEN_D": C.GREEN_D, "RED": C.RED,
    }


def _token_size(token: TypeToken) -> int:
    return token.size


def _token_weight(token: TypeToken) -> str:
    w = token.weight
    if w == QFont.Weight.Bold:
        return "700"
    if w == QFont.Weight.Medium:
        return "500"
    return "400"


# ═════════════════════════════════════════════════════════════════════════════
# 4. BUTTON VARIANTS
# ═════════════════════════════════════════════════════════════════════════════

_BUTTON_COMMON = """
    QPushButton {{
        border: none;
        border-radius: 6px;
        font-family: "{mono}";
        font-size: {size}pt;
        font-weight: {weight};
        padding: {pad_y}px {pad_x}px;
        min-height: {h}px;
    }}
    QPushButton:disabled {{
        color: #4b5563;
        border-color: #1f2937;
    }}
    QPushButton:focus-visible {{
        outline: none;
        border: 2px solid {focus};
        border-radius: 4px;
    }}
"""


def _styled_btn(text: str, parent, base_qss: str, **fmt) -> QPushButton:
    c = _colors()
    fmt_defaults = dict(
        mono=FONT_MONO,
        size=_token_size(TYPE_MEDIUM),
        weight=_token_weight(TYPE_MEDIUM),
        pad_y=7, pad_x=16, h=36,
        focus=c["ACC"],
    )
    fmt_defaults.update(fmt)
    btn = QPushButton(text, parent)
    btn.setStyleSheet(base_qss.format(**fmt_defaults))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def primary_button(text: str, parent=None, accent: Optional[str] = None) -> QPushButton:
    """Primary action — filled, accent-coloured, high emphasis."""
    c = _colors()
    bg = accent or c["PRI"]
    return _styled_btn(text, parent, _BUTTON_COMMON + """
        QPushButton {{
            background: {bg};
            color: {fg};
        }}
        QPushButton:hover:!disabled {{
            background: {bg_hover};
        }}
        QPushButton:pressed:!disabled {{
            background: {bg_pressed};
        }}
    """, bg=bg, fg="#ffffff",
        bg_hover=_lighten(bg, 0.15), bg_pressed=_darken(bg, 0.15))


def secondary_button(text: str, parent=None) -> QPushButton:
    """Secondary action — outlined, lower emphasis."""
    c = _colors()
    return _styled_btn(text, parent, _BUTTON_COMMON + """
        QPushButton {{
            background: transparent;
            color: {fg};
            border: 1px solid {border};
        }}
        QPushButton:hover:!disabled {{
            background: rgba(255, 255, 255, 0.05);
            border-color: {border_hover};
        }}
        QPushButton:pressed:!disabled {{
            background: rgba(255, 255, 255, 0.10);
        }}
    """, fg=c["TEXT"], border=c["BORDER"], border_hover=c["BORDER_B"])


def ghost_button(text: str, parent=None) -> QPushButton:
    """Ghost button — text only, minimal emphasis."""
    c = _colors()
    return _styled_btn(text, parent, _BUTTON_COMMON + """
        QPushButton {{
            background: transparent;
            color: {fg};
        }}
        QPushButton:hover:!disabled {{
            background: rgba(255, 255, 255, 0.03);
        }}
    """, fg=c["TEXT_MED"])


def danger_button(text: str, parent=None) -> QPushButton:
    """Destructive action — red filled."""
    c = _colors()
    return _styled_btn(text, parent, _BUTTON_COMMON + """
        QPushButton {{
            background: {bg};
            color: {fg};
        }}
        QPushButton:hover:!disabled {{
            background: {bg_hover};
        }}
    """, bg=c["RED"], fg="#ffffff",
        bg_hover=_lighten(c["RED"], 0.15))


# ═════════════════════════════════════════════════════════════════════════════
# 5. INPUT & COMBO STYLES
# ═════════════════════════════════════════════════════════════════════════════

INPUT_QSS = """
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background: {bg};
        color: {fg};
        border: 1px solid {border};
        border-radius: 6px;
        font-family: "{mono}";
        font-size: {size}pt;
        padding: {pad_y}px {pad_x}px;
        min-height: {h}px;
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {focus};
        outline: none;
    }}
    QLineEdit:disabled, QTextEdit:disabled {{
        background: #111827;
        color: #4b5563;
    }}
"""


def style_input(widget, accent: Optional[str] = None) -> None:
    """Apply WCAG-safe input styling to a QLineEdit/QTextEdit."""
    c = _colors()
    focus = accent or c["ACC"]
    widget.setStyleSheet(INPUT_QSS.format(
        mono=FONT_MONO,
        size=_token_size(TYPE_BODY),
        bg=c["PANEL"], fg=c["TEXT"], border=c["BORDER"], focus=focus,
        pad_y=7, pad_x=12, h=36,
    ))


COMBO_QSS = """
    QComboBox {{
        background: {bg};
        color: {fg};
        border: 1px solid {border};
        border-radius: 6px;
        font-family: "{mono}";
        font-size: {size}pt;
        padding: {pad_y}px {pad_x}px;
        min-height: {h}px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background: {panel};
        color: {fg};
        border: 1px solid {border};
        selection-background-color: {accent};
        selection-color: #000000;
    }}
"""


def style_combo(widget, accent: Optional[str] = None) -> None:
    """Apply WCAG-safe combo styling to a QComboBox."""
    c = _colors()
    focus = accent or c["ACC"]
    widget.setStyleSheet(COMBO_QSS.format(
        mono=FONT_MONO,
        size=_token_size(TYPE_BODY),
        bg=c["PANEL"], fg=c["TEXT"], border=c["BORDER"],
        panel=c["PANEL2"], accent=focus,
        pad_y=7, pad_x=12, h=36,
    ))


# ═════════════════════════════════════════════════════════════════════════════
# 6. GLASS PANEL & CARD
# ═════════════════════════════════════════════════════════════════════════════

GLASS_PANEL_QSS = """
    QWidget {{
        background: rgba(13, 15, 21, 230);
        border: 1px solid {border};
        border-radius: 10px;
    }}
"""


def glass_panel(parent=None) -> QWidget:
    """Translucent panel with hairline border — for overlays & side panels."""
    c = _colors()
    panel = QWidget(parent)
    panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    panel.setStyleSheet(GLASS_PANEL_QSS.format(border=c["BORDER_B"]))
    return panel


GLASS_CARD_QSS = """
    QWidget {{
        background: rgba(18, 21, 31, 200);
        border: 1px solid {border};
        border-radius: 8px;
    }}
    QWidget:hover {{
        border-color: {border_hover};
        background: rgba(18, 21, 31, 230);
    }}
"""


def glass_card(parent=None) -> QWidget:
    """Elevated card — subtle hover lift, for list items & widgets."""
    c = _colors()
    card = QWidget(parent)
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setStyleSheet(GLASS_CARD_QSS.format(
        border=c["BORDER"], border_hover=c["BORDER_B"],
    ))
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(16)
    shadow.setColor(QColor(0, 0, 0, 120))
    shadow.setOffset(0, 4)
    card.setGraphicsEffect(shadow)
    return card


# ═════════════════════════════════════════════════════════════════════════════
# 7. TOAST NOTIFICATION SYSTEM
# ═════════════════════════════════════════════════════════════════════════════

TOAST_QSS = """
    QWidget {{
        background: rgba(7, 8, 12, 240);
        border: 1px solid {border};
        border-radius: 8px;
        color: {fg};
    }}
"""


class Toast(QWidget):
    """Non-blocking, auto-dismiss notification anchored to a parent widget."""

    def __init__(self, parent: QWidget, message: str, level: str = "info",
                 duration_ms: int = 4000):
        super().__init__(parent)  # type: ignore[arg-type]
        c = _colors()
        level_conf = {
            "info": (c["PRI"], c["TEXT"]),
            "success": (c["GREEN"], c["TEXT"]),
            "warning": (c["ACC2"], "#000000"),
            "error": (c["RED"], c["TEXT"]),
        }
        border, fg = level_conf.get(level, level_conf["info"])

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(TOAST_QSS.format(border=border, fg=fg))
        self.setFixedWidth(320)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)

        icon = {"info": "◈", "success": "✓", "warning": "⚠", "error": "✕"}[level]
        ic = QLabel(icon)
        ic.setFont(font(TYPE_SMALL))
        ic.setStyleSheet(f"color: {border}; background: transparent;")
        lay.addWidget(ic)

        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setFont(font(TYPE_SMALL))
        msg.setStyleSheet(f"color: {fg}; background: transparent;")
        lay.addWidget(msg)

        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.deleteLater)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade)
        self._timer.start(duration_ms)

        self.show()

    def _fade(self):
        self._anim.start()


def toast(parent: QWidget, message: str, level: str = "info",
          duration_ms: int = 4000) -> Toast:
    """Show a toast notification. Returns the Toast instance."""
    return Toast(parent, message, level, duration_ms)


# ═════════════════════════════════════════════════════════════════════════════
# 8. COLOUR UTILITIES
# ═════════════════════════════════════════════════════════════════════════════

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def _lighten(hex_str: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(hex_str)
    return _rgb_to_hex(
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )


def _darken(hex_str: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(hex_str)
    return _rgb_to_hex(
        int(r * (1 - factor)),
        int(g * (1 - factor)),
        int(b * (1 - factor)),
    )


def contrast_ratio(hex1: str, hex2: str) -> float:
    """WCAG contrast ratio between two colours."""
    def lum(c):
        r, g, b = _hex_to_rgb(c)
        r = r / 255.0
        g = g / 255.0
        b = b / 255.0
        r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
        g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
        b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    l1, l2 = lum(hex1), lum(hex2)
    return float((max(l1, l2) + 0.05) / (min(l1, l2) + 0.05))


# ═════════════════════════════════════════════════════════════════════════════
# 9. FOCUS RING HELPER
# ═════════════════════════════════════════════════════════════════════════════

def apply_focus_ring(widget: QWidget, colour: Optional[str] = None) -> None:
    """Add a visible focus-visible ring to a widget for keyboard users."""
    c = _colors()
    col = colour or c["ACC"]
    existing = widget.styleSheet()
    widget.setStyleSheet(existing + f"""
        QWidget:focus-visible {{
            border: 2px solid {col};
            border-radius: 4px;
            outline: none;
        }}
    """)


# ════════════════════════════════════════════════════════════════════════════
# 10. SUGGESTION CHIPS — intent-first quick actions
# ═════════════════════════════════════════════════════════════════════════════


def suggestion_chip(text: str) -> QPushButton:
    """A low-affordance chip that fires an intent when clicked.

    AI-first interfaces surface suggested intents rather than leaving the
    user staring at a blank composer. Chips are secondary/ghost styled so
    they never compete with the primary send action.
    """
    chip = QPushButton(text)
    chip.setCursor(Qt.CursorShape.PointingHandCursor)
    c = _colors()
    chip.setStyleSheet(f"""
        QPushButton {{
            background: rgba(255, 255, 255, 0.06);
            color: {c['FG_SECONDARY']};
            border: 1px solid {c['BORDER']};
            border-radius: 16px;
            padding: 4px 12px;
            font-size: {TYPE_BODY.size}px;
            font-weight: {TYPE_BODY.weight};
            letter-spacing: -0.2px;
            min-height: 24px;
        }}
        QPushButton:hover {{
            background: rgba(255, 255, 255, 0.10);
            border-color: {c['ACC']};
            color: {c['FG']};
        }}
        QPushButton:focus-visible {{
            border: 2px solid {c['ACC']};
            border-radius: 16px;
            outline: none;
        }}
    """)
    chip.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return chip


def suggestion_row(parent: QWidget, labels: list[str], on_click) -> QWidget:
    """Horizontal row of suggestion chips inside a scroll-friendly wrapper."""
    wrapper = QWidget(parent)
    wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    wrapper.setStyleSheet(f"""
        QWidget {{ background: transparent; }}
    """)
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(int(SPACE_XS * 0.75))
    for label in labels:
        chip = suggestion_chip(label)
        chip.clicked.connect(lambda _checked, t=label: on_click(t))
        apply_focus_ring(chip)
        layout.addWidget(chip)
    layout.addStretch()
    return wrapper


# ════════════════════════════════════════════════════════════════════════════
# 11. AI STATUS BADGE — live state indicator (listening / thinking / speaking)
# ═════════════════════════════════════════════════════════════════════════════

_AI_STATE_COLOURS = {
    "idle": "#6B7280",
    "listening": "#34D399",
    "thinking": "#60A5FA",
    "speaking": "#A78BFA",
    "error": "#F87171",
}


class AIStatusBadge(QLabel):
    """Small pill-shaped badge that shows the assistant's current AI state.

    Confidence indicators & transparency: the user always knows whether
    Ultron is listening, thinking, or speaking.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c = _colors()
        self._set_state("idle")

    def _set_state(self, state: str) -> None:
        colour = _AI_STATE_COLOURS.get(state, _AI_STATE_COLOURS["idle"])
        c = _colors()
        self.setStyleSheet(f"""
            QLabel {{
                background: rgba({_hex_to_rgb(colour)[0]}, {_hex_to_rgb(colour)[1]}, {_hex_to_rgb(colour)[2]}, 0.14);
                color: {colour};
                border: 1px solid {colour};
                border-radius: 11px;
                padding: 0 8px;
                font-size: {TYPE_CAPTION.size}px;
                font-weight: {TYPE_CAPTION.weight};
                letter-spacing: 0.4px;
            }}
        """)
        self.setText(state.upper())

    def set_state(self, state: str) -> None:
        self._set_state(state)


# ════════════════════════════════════════════════════════════════════════════
# 12. KEYBOARD SHORTCUTS HELP — discoverability
# ═════════════════════════════════════════════════════════════════════════════

_KEYBOARD_SHORTCUTS = [
    ("Enter", "Send message"),
    ("Shift+Enter", "New line in composer"),
    ("Esc", "Close overlay / cancel"),
    ("Ctrl+K", "Focus search / command palette"),
    ("Ctrl+Shift+C", "Copy last code block"),
    ("Ctrl+/", "Show this help"),
]


def keyboard_shortcuts_dialog(parent: QWidget) -> QDialog:
    """Non-blocking help dialog listing keyboard shortcuts."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Keyboard shortcuts")
    dlg.setFixedSize(420, 300)
    dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    c = _colors()
    dlg.setStyleSheet(f"""
        QDialog {{
            background: {c['SURFACE']};
            border: 1px solid {c['BORDER']};
            border-radius: 12px;
            color: {c['FG']};
        }}
        QLabel {{ color: {c['FG']}; background: transparent; }}
        QPushButton {{
            background: {c['ACC']};
            color: {c['BG']};
            border: none;
            border-radius: 6px;
            padding: 6px 14px;
            font-size: {TYPE_BODY.size}px;
            font-weight: {TYPE_MEDIUM.weight};
        }}
        QPushButton:hover {{ background: {_lighten(c['ACC'], 0.10)}; }}
    """)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(20, 20, 20, 16)
    layout.setSpacing(12)

    title = QLabel("Keyboard shortcuts")
    title.setStyleSheet(f"font-size: {TYPE_DISPLAY.size}px; font-weight: {TYPE_DISPLAY.weight}; letter-spacing: -0.5px;")
    layout.addWidget(title)

    for key, desc in _KEYBOARD_SHORTCUTS:
        row = QHBoxLayout()
        key_lbl = QLabel(key)
        key_lbl.setFixedWidth(130)
        key_lbl.setStyleSheet(f"color: {c['ACC']}; font-family: 'SF Mono', 'Monaco', monospace; font-size: {TYPE_BODY.size}px;")
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(f"color: {c['FG_SECONDARY']}; font-size: {TYPE_BODY.size}px;")
        row.addWidget(key_lbl)
        row.addWidget(desc_lbl)
        row.addStretch()
        layout.addLayout(row)

    layout.addStretch()
    close_btn = QPushButton("Got it")
    close_btn.clicked.connect(dlg.accept)
    apply_focus_ring(close_btn)
    layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
    return dlg


# ════════════════════════════════════════════════════════════════════════════
# 13. ACCESSIBILITY TOGGLES — reduced motion, high contrast, font scale
# ════════════════════════════════════════════════════════════════════════════


def accessibility_panel(parent: QWidget, on_change) -> QWidget:
    """Compact accessibility controls: reduced motion, high contrast, font scale."""
    panel = QWidget(parent)
    panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    c = _colors()
    panel.setStyleSheet(f"""
        QWidget {{ background: {c['SURFACE']}; border: 1px solid {c['BORDER']}; border-radius: 10px; }}
        QLabel {{ color: {c['FG']}; background: transparent; }}
        QCheckBox {{
            color: {c['FG_SECONDARY']};
            spacing: 8px;
            font-size: {TYPE_BODY.size}px;
        }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border: 1px solid {c['BORDER']};
            border-radius: 3px;
            background: {c['BG']};
        }}
        QCheckBox::indicator:checked {{
            background: {c['ACC']};
            border-color: {c['ACC']};
        }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: {c['BORDER']};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {c['ACC']};
            width: 14px; height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }}
    """)

    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(10)

    reduced_motion = QCheckBox("Reduce motion")
    reduced_motion.setToolTip("Disables animations and auto-scroll effects")
    reduced_motion.stateChanged.connect(lambda s: on_change("reduced_motion", bool(s)))
    apply_focus_ring(reduced_motion)
    layout.addWidget(reduced_motion)

    high_contrast = QCheckBox("High contrast")
    high_contrast.setToolTip("Increases border and text contrast for WCAG AAA")
    high_contrast.stateChanged.connect(lambda s: on_change("high_contrast", bool(s)))
    apply_focus_ring(high_contrast)
    layout.addWidget(high_contrast)

    font_row = QHBoxLayout()
    font_lbl = QLabel("Font scale")
    font_lbl.setStyleSheet(f"color: {c['FG_SECONDARY']}; font-size: {TYPE_BODY.size}px;")
    font_slider = QSlider(Qt.Orientation.Horizontal)
    font_slider.setRange(80, 150)
    font_slider.setValue(100)
    font_slider.valueChanged.connect(lambda v: on_change("font_scale", v / 100.0))
    apply_focus_ring(font_slider)
    font_row.addWidget(font_lbl)
    font_row.addWidget(font_slider)
    layout.addLayout(font_row)

    return panel


# ════════════════════════════════════════════════════════════════════════════
# 14. GESTURE STATUS BADGE — Project Minority hands-sign indicator
# ═════════════════════════════════════════════════════════════════════════════

_GESTURE_STATE_COLOURS = {
    "standby":  "#6B7280",
    "engaged":  "#00D4FF",
    "detected": "#34D399",
    "error":    "#F87171",
}


class GestureStatusBadge(QLabel):
    """Small pill-shaped badge showing Project Minority gesture engine state.

    States: standby (engine off), engaged (camera tracking), detected
    (a hand sign was just recognised), error (camera unavailable).
    """

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_state("standby")

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def _set_state(self, state: str) -> None:
        colour = _GESTURE_STATE_COLOURS.get(state, _GESTURE_STATE_COLOURS["standby"])
        c = _colors()
        self.setStyleSheet(f"""
            QLabel {{
                background: rgba({_hex_to_rgb(colour)[0]}, {_hex_to_rgb(colour)[1]}, {_hex_to_rgb(colour)[2]}, 0.14);
                color: {colour};
                border: 1px solid {colour};
                border-radius: 11px;
                padding: 0 8px;
                font-size: {TYPE_CAPTION.size}px;
                font-weight: {TYPE_CAPTION.weight};
                letter-spacing: 0.4px;
            }}
        """)
        self.setText(state.upper())

    def set_state(self, state: str) -> None:
        self._set_state(state)

    def flash_detected(self, gesture_name: str) -> None:
        """Briefly show 'detected' state with the gesture name, then return to engaged."""
        self.setText(f"DETECTED: {gesture_name}")
        self.set_state("detected")
        QTimer.singleShot(1500, lambda: self.set_state("engaged"))
