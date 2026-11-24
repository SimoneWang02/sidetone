"""The settings window on Linux: sections down the side, the settings of one beside them, drawn
from what the hub describes (hub/settings.py, `describe`). A change goes back as "this key,
this value"; the hub answers with how things stand, which is drawn again."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget,
                               QMenu, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

import draw

STYLE = """
QWidget#window { background: #1d2128; }
QListWidget { background: #171a20; border: none; color: #d8dde5; font-size: 13px; padding: 8px; }
QListWidget::item { padding: 7px 10px; border-radius: 6px; }
QListWidget::item:selected { background: #2c323c; color: white; }
QScrollArea, QWidget#page { background: #1d2128; border: none; }
QFrame#card { background: #252a33; border-radius: 10px; }
QLabel { color: #e8ecf1; font-size: 13px; }
QLabel#help { color: #9aa3ae; font-size: 11.5px; }
QLabel#title { font-size: 18px; font-weight: 600; }
QLabel#heading { font-size: 14px; font-weight: 600; }
QPushButton { background: #2f3641; color: #e8ecf1; border: 1px solid #3b4350; border-radius: 6px; padding: 4px 12px; font-size: 12px; }
QPushButton:checked { background: #006896; border-color: #0a7fb3; color: white; }
QPushButton#key { font-weight: 600; }
QComboBox { background: #2f3641; color: #e8ecf1; border: 1px solid #3b4350; border-radius: 6px; padding: 3px 8px; min-width: 180px; }
QCheckBox::indicator { width: 34px; height: 18px; }
QSlider::groove:horizontal { height: 4px; background: #3b4350; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #2e9cc9; border-radius: 2px; }
QSlider::handle:horizontal { background: white; width: 14px; margin: -6px 0; border-radius: 7px; }
"""

QT_NAMES = {Qt.Key.Key_Space: "Space", Qt.Key.Key_Backspace: "Backspace", Qt.Key.Key_Delete: "Delete", Qt.Key.Key_Return: "Return",
            Qt.Key.Key_Tab: "Tab", Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down", Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
            Qt.Key.Key_Home: "Home", Qt.Key.Key_End: "End", Qt.Key.Key_PageUp: "PageUp", Qt.Key.Key_PageDown: "PageDown",
            Qt.Key.Key_Plus: "Plus", Qt.Key.Key_Equal: "Plus", Qt.Key.Key_Minus: "Minus"}


class SettingsWindow(QWidget):
    def __init__(self, choose, closed, typing, previewing):
        super().__init__(None, Qt.WindowType.Window)
        self.choose, self.closed, self.typing, self.previewing = choose, closed, typing, previewing
        self.setObjectName("window")
        self.setStyleSheet(STYLE)
        self.resize(790, 560)
        self.sections: list = []
        self.current = ""
        self.capturing = ""
        self.confirming = ""
        self.open_groups: set = set()
        self.more_shown: set = set()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setFixedWidth(176)
        self.nav.currentTextChanged.connect(self._pick)
        row.addWidget(self.nav)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        row.addWidget(self.scroll, 1)

    # --- from the hub -------------------------------------------------------------------------

    def show_sections(self, sections: list, section: str, title: str, quiet: bool) -> None:
        self.setWindowTitle(title)
        self.sections = [s for s in sections if isinstance(s, dict)]
        names = [str(s.get("name", "")) for s in self.sections]
        if section:
            self.current = section
        if self.current not in names:
            self.current = names[0] if names else ""
        self.nav.blockSignals(True)
        self.nav.clear()
        self.nav.addItems(names)
        if self.current in names:
            self.nav.setCurrentRow(names.index(self.current))
        self.nav.blockSignals(False)
        self.fill()
        if not self.isVisible():
            self.show()
            if not quiet:
                self.raise_()
                self.activateWindow()

    def hide_window(self) -> None:
        self._stop_typing()
        self.hide()

    def closeEvent(self, e) -> None:
        self._stop_typing()
        self.closed()
        super().closeEvent(e)

    def _pick(self, name: str) -> None:
        if name and name != self.current:
            self.current = name
            self.fill()

    # --- drawing a section ----------------------------------------------------------------------

    def fill(self) -> None:
        section = next((s for s in self.sections if s.get("name") == self.current), None)
        page = QWidget()
        page.setObjectName("page")
        col = QVBoxLayout(page)
        col.setContentsMargins(24, 20, 24, 24)
        col.setSpacing(10)
        title = QLabel(self.current)
        title.setObjectName("title")
        col.addWidget(title)
        if section:
            card = None
            group, folded, hidden = "", False, 0
            for item in section.get("items") or []:
                kind = item.get("kind")
                if kind == "intro":
                    col.addWidget(self._help(item.get("help", "")))
                    continue
                if kind == "heading":
                    card = None
                    group = str(item.get("key", "")).replace("heading.", "")
                    folded = bool(item.get("fold")) and group not in self.open_groups
                    col.addWidget(self._heading(item, group, folded))
                    continue
                if kind == "pack":
                    if not folded or item.get("always"):
                        col.addWidget(self._remove(item))
                    continue
                if folded:
                    continue
                if item.get("more") and item.get("value") is not True and group not in self.more_shown:
                    hidden += 1
                    continue
                if card is None:
                    card = QFrame()
                    card.setObjectName("card")
                    QVBoxLayout(card).setContentsMargins(16, 6, 16, 6)
                    col.addWidget(card)
                card.layout().addWidget(self._line(item))
            if section.get("resettable"):
                key = "reset." + self.current
                button = QPushButton("Click Again to Reset" if self.confirming == key else "Reset")
                button.setEnabled(bool(section.get("changed")))
                button.clicked.connect(lambda: self._confirm(key, lambda: self.choose("reset", self.current)))
                col.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        col.addStretch(1)
        self.scroll.setWidget(page)

    def _help(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("help")
        label.setWordWrap(True)
        return label

    def _heading(self, item: dict, group: str, folded: bool) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 14, 0, 2)
        if item.get("fold"):
            arrow = QPushButton(("▸ " if folded else "▾ ") + str(item.get("name", "")))
            arrow.setFlat(True)
            arrow.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 14px; font-weight: 600; text-align: left; }")
            arrow.clicked.connect(lambda: (self.open_groups.symmetric_difference_update({group}), self.fill()))
            row.addWidget(arrow)
        else:
            label = QLabel(str(item.get("name", "")))
            label.setObjectName("heading")
            row.addWidget(label)
        row.addStretch(1)
        if item.get("summary"):
            row.addWidget(self._help(str(item["summary"])))
        if item.get("install"):
            if item.get("pack") == "installing":
                row.addWidget(self._help(f"{float(item.get('progress') or 0) * 100:.0f}%"))
            else:
                install = QPushButton("Try Again" if item.get("pack") == "failed" else "Install")
                install.setChecked(True)
                install.clicked.connect(lambda: self.choose(str(item["install"]), True))
                row.addWidget(install)
        elif item.get("speak"):
            switch = QCheckBox()
            switch.setChecked(bool(item.get("spoken", True)))
            switch.setEnabled(not item.get("last"))
            switch.toggled.connect(lambda on: self.choose(str(item["speak"]), on))
            row.addWidget(switch)
        return box

    def _remove(self, item: dict) -> QWidget:
        key = str(item.get("key", ""))
        button = QPushButton("Click Again to Remove" if self.confirming == key else str(item.get("name", "")))
        button.clicked.connect(lambda: self._confirm(key, lambda: self.choose(key, True)))
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 4, 0, 8)
        row.addWidget(button)
        row.addWidget(self._help(str(item.get("help", ""))), 1)
        return box

    def _confirm(self, key: str, act) -> None:
        if self.confirming == key:
            self.confirming = ""
            act()
            return
        self.confirming = key
        self.fill()

        def forget():
            if self.confirming == key:
                self.confirming = ""
                self.fill()
        QTimer.singleShot(4000, forget)

    def _line(self, item: dict) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 8, 0, 8)
        words = QVBoxLayout()
        words.setSpacing(2)
        name = str(item.get("name", ""))
        if item.get("tag"):
            name += f"   · {item['tag']}"
        words.addWidget(QLabel(name))
        if item.get("help"):
            words.addWidget(self._help(str(item["help"])))
        row.addLayout(words, 1)
        control = self._control(item)
        if control is not None:
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        return box

    def _control(self, item: dict) -> QWidget | None:
        kind, key, value = item.get("kind"), str(item.get("key", "")), item.get("value")
        options = [(str(o[0]), str(o[1])) for o in item.get("options") or [] if isinstance(o, list) and len(o) >= 2]
        if kind == "switch":
            switch = QCheckBox()
            switch.setChecked(bool(value))
            switch.toggled.connect(lambda on: self.choose(key, on))
            return switch
        if kind == "number":
            return self._slider(item)
        if kind == "choice":
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            group = QButtonGroup(box)
            for code, label in options:
                part = QPushButton(label)
                part.setCheckable(True)
                part.setChecked(str(value) == code)
                part.clicked.connect(lambda _=False, c=code: self.choose(key, c))
                group.addButton(part)
                row.addWidget(part)
            return box
        if kind == "pick":
            pick = QComboBox()
            for code, label in options:
                pick.addItem(label, code)
            codes = [c for c, _ in options]
            if str(value) in codes:
                pick.setCurrentIndex(codes.index(str(value)))
            pick.activated.connect(lambda i: self.choose(key, pick.itemData(i)))
            if item.get("play"):
                return self._with_play(pick, str(value), bool(item.get("playing")))
            return pick
        if kind == "voice":
            box = QWidget()
            row = QHBoxLayout(box)
            row.setContentsMargins(0, 0, 0, 0)
            if item.get("preview", True):
                row.addWidget(self._play(str(item.get("voice", "")), bool(item.get("playing"))))
            if item.get("switch", True):
                switch = QCheckBox()
                switch.setChecked(bool(value))
                switch.toggled.connect(lambda on: self.choose(key, on))
                row.addWidget(switch)
            return box
        if kind == "color":
            return self._color(item)
        if kind == "key":
            return self._key(key, str(value or ""))
        return None

    def _play(self, voice: str, playing: bool) -> QPushButton:
        button = QPushButton("■" if playing else "▶")
        button.setFixedWidth(32)
        button.setToolTip("Stop" if playing else "Hear this voice")
        button.clicked.connect(lambda: self.choose("stop_preview" if playing else "play", voice))
        return button

    def _with_play(self, control: QWidget, voice: str, playing: bool) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._play(voice, playing))
        row.addWidget(control)
        return box

    def _slider(self, item: dict) -> QWidget:
        key = str(item.get("key", ""))
        low, high, step = float(item.get("min", 0)), float(item.get("max", 1)), float(item.get("step", 1)) or 1
        scale = float(item.get("scale", 1))
        unit = str(item.get("unit", ""))
        places = 0 if step * scale >= 1 else 1 if step * scale >= 0.1 else 2
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setFixedWidth(150)
        slider.setRange(0, round((high - low) / step))
        now_value = float(item.get("value") if item.get("value") is not None else low)
        slider.setValue(round((now_value - low) / step))
        figure = QLabel(f"{now_value * scale:.{places}f}{unit}")
        figure.setFixedWidth(52)
        figure.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        def value():
            return round(low + slider.value() * step, 6)
        slider.valueChanged.connect(lambda _: (figure.setText(f"{value() * scale:.{places}f}{unit}"), self.previewing(key, value())))
        slider.sliderReleased.connect(lambda: self.choose(key, value()))
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(slider)
        row.addWidget(figure)
        return box

    def _color(self, item: dict) -> QWidget:
        key = str(item.get("key", ""))
        now_code = str(item.get("value") or "")
        shown = now_code or str(item.get("empty", "#3A4150"))
        swatches = [str(s) for s in item.get("swatches") or []]
        button = QPushButton("  " + shown.upper())
        button.setIcon(_dot(shown))
        menu = QMenu(button)
        for s in swatches:
            action = menu.addAction(_dot(s or str(item.get("empty", "#3A4150"))), s.upper() if s else "As It Was")
            action.triggered.connect(lambda _=False, c=s: self.choose(key, c))
        menu.addSeparator()

        def any_color():
            start = QColor(shown)
            dialog = QColorDialog(start, self)
            dialog.currentColorChanged.connect(lambda c: self.previewing(key, c.name().upper()))
            if dialog.exec():
                self.choose(key, dialog.currentColor().name().upper())
            else:
                self.previewing(key, shown)
        menu.addAction("Any Color…").triggered.connect(any_color)
        if swatches and now_code.upper() != swatches[0].upper():
            menu.addAction("Reset").triggered.connect(lambda: self.choose(key, swatches[0]))
        button.setMenu(menu)
        return button

    def _key(self, key: str, combo: str) -> QPushButton:
        typing = self.capturing == key
        shown = "Press the Keys" if typing else " + ".join(p.strip() for p in combo.split("+") if p.strip()) or "No Key"
        button = QPushButton(shown)
        button.setObjectName("key")
        button.setCheckable(True)
        button.setChecked(typing)
        button.clicked.connect(lambda: self._start_typing(key))
        return button

    # --- a hotkey being typed -------------------------------------------------------------------

    def _start_typing(self, key: str) -> None:
        if self.capturing == key:
            self._stop_typing()
        else:
            self.capturing = key
            self.typing(True)
        self.fill()
        self.activateWindow()
        self.setFocus()

    def _stop_typing(self) -> None:
        if self.capturing:
            self.capturing = ""
            self.typing(False)

    def keyPressEvent(self, e) -> None:
        if not self.capturing:
            if e.key() == Qt.Key.Key_Escape:
                self.close()
            return super().keyPressEvent(e)
        mods = e.modifiers()
        k = e.key()
        if k in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R):
            return
        if k == Qt.Key.Key_Escape and not mods:
            self._stop_typing()
            self.fill()
            return
        name = QT_NAMES.get(k) or QKeySequence(k).toString()
        is_f = name.startswith("F") and name[1:].isdigit()
        held = mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)
        if not held and not is_f:
            return  # a key alone would be taken from every app
        combo = ("Ctrl+" if mods & Qt.KeyboardModifier.ControlModifier else "") + ("Alt+" if mods & Qt.KeyboardModifier.AltModifier else "") \
            + ("Shift+" if mods & Qt.KeyboardModifier.ShiftModifier else "") + ("Win+" if mods & Qt.KeyboardModifier.MetaModifier else "") + name
        which = self.capturing
        self._stop_typing()
        self.choose(which, combo)


def _dot(code: str):
    from PySide6.QtGui import QIcon, QPainter, QPixmap
    pixmap = QPixmap(14, 14)
    pixmap.fill(Qt.GlobalColor.transparent)
    g = QPainter(pixmap)
    g.setRenderHint(QPainter.RenderHint.Antialiasing)
    g.setBrush(draw.color(code, "#808080"))
    g.setPen(QColor(255, 255, 255, 90))
    g.drawEllipse(1, 1, 12, 12)
    g.end()
    return QIcon(pixmap)



