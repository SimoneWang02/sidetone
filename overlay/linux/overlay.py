"""Sidetone's overlay for Linux desktops: the lights of the sessions, their details, the bubble
and the settings window, in Qt (PySide6, in the hub's own Python). Like the Windows and Mac
overlays it decides nothing: the hub writes one JSON object per line to its standard input,
and it writes one per line back. It ends when its input ends.

A port of overlay/mac (Overlay.swift, Paint.swift): the same units, scaled by the Size setting.
On X11 the windows go where they are put and float over the others; a Wayland desktop decides
both itself, so there the overlay runs through XWayland when it can (QT_QPA_PLATFORM).
"""
from __future__ import annotations

import json
import math
import os
import sys
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "xcb;wayland")  # X11 first: windows can be placed and kept on top
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QLinearGradient, QPainter, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import draw  # noqa: E402
from draw import Ui, alpha, now  # noqa: E402
from paint import Painting  # noqa: E402

WHITE = draw.WHITE
_out = threading.Lock()


def send(message: dict) -> None:
    with _out:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()


def note(text: str) -> None:
    send({"type": "note", "message": text})


def num(m: dict, key: str, fallback: float = 0.0) -> float:
    try:
        return float(m.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def string(m: dict, key: str, fallback: str = "") -> str:
    v = m.get(key, fallback)
    return fallback if v is None else str(v)


class Reader(QObject):
    """The hub's lines, read on a thread of their own and handed to Qt's thread in order."""
    arrived = Signal(dict)
    ended = Signal()

    def start(self) -> None:
        threading.Thread(target=self._read, name="stdin", daemon=True).start()

    def _read(self) -> None:
        for raw in sys.stdin:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                self.arrived.emit(msg)
        self.ended.emit()


class Row:
    def __init__(self):
        self.name = self.color = self.title = self.text = self.meta = ""
        self.state = "idle"
        self.details: list = []
        self.speaking = self.focus = False
        self.orb = draw.Orb()
        self.flash_text: str | None = None
        self.flash_until = 0.0
        self.talk_kind: str | None = None
        self.talk_text = ""
        self.talk_ink = WHITE
        self.talk_bold = False
        self.lit = 0.0

    @property
    def saying(self) -> bool:
        return self.flash_text is not None and (self.speaking or now() < self.flash_until)

    @property
    def showing(self) -> bool:
        return self.talk_kind is not None or self.saying

    def update(self, s: dict) -> None:
        was, before = self.speaking, self.state
        self.name, self.color, self.title = string(s, "name"), string(s, "color"), string(s, "title")
        self.state, self.text, self.meta = string(s, "state", "idle"), string(s, "text"), string(s, "meta")
        self.details = [d for d in (s.get("details") or []) if isinstance(d, list)]
        self.speaking, self.focus = bool(s.get("speaking")), bool(s.get("target"))
        self.orb.state, self.orb.speaking = self.state, self.speaking
        waits = int(num(s, "waiting"))
        if waits > self.orb.waiting:
            self.orb.waiting_since = now()
            self.orb.covers = Ui.waiting_cover == "each" or (Ui.waiting_cover == "first" and self.orb.waiting == 0)
        self.orb.waiting = waits
        self.orb.set_context(float(s["context"]) if isinstance(s.get("context"), (int, float)) else -1)
        if before and (before != self.state or was != self.speaking):
            self.orb.changed = now()
        self.orb.wave.synthetic = bool(s.get("synth"))
        if self.speaking and not was:
            self.orb.wave.since = now()
        if not self.speaking and was:
            self.orb.wave.clear()

    def second_line(self):
        if self.talk_kind is not None:
            return self.talk_text, self.talk_ink, self.talk_bold
        if self.saying:
            return self.flash_text or "", WHITE, False
        return self.text, Ui.dim, False


class Glass(QWidget):
    """One piece of glass: frameless, over every window, never taking the keyboard. Linux has no
    shared blur, so the glass is the overlay's dark tint, a little see-through."""

    def __init__(self, owner, painter, takes_mouse: bool):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.X11BypassWindowManagerHint)
        if not takes_mouse:
            flags |= Qt.WindowType.WindowTransparentForInput
        super().__init__(None, flags)
        self.owner, self.painter = owner, painter
        self.radius = 10
        self.look = "blur"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

    def paintEvent(self, _event) -> None:
        g = QPainter(self)
        g.setRenderHint(QPainter.RenderHint.Antialiasing)
        g.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        box = QRectF(self.rect())
        top = Ui.glass_top()
        c = draw.clamp(Ui.glass_clear / 100)

        def shade(share, a):
            return QColor.fromRgbF(top.redF() * share, top.greenF() * share, top.blueF() * share, a)
        solid = self.look in ("none", "solid")
        a_top = 1.0 if solid else 0.97 - 0.30 * c
        a_bottom = 1.0 if solid else 0.98 - 0.25 * c
        gradient = QLinearGradient(0, 0, 0, box.height())
        gradient.setColorAt(0, shade(0.74 if solid else 1.0, a_top))
        gradient.setColorAt(1, shade(0.35 if solid else 0.32, a_bottom))
        path = QPainterPath()
        path.addRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.radius)
        g.setPen(Qt.PenStyle.NoPen)
        g.setBrush(gradient)
        g.drawPath(path)
        edge = QLinearGradient(0, 0, box.width(), box.height())
        edge.setColorAt(0, alpha(WHITE, 0.45))
        edge.setColorAt(0.5, alpha(WHITE, 0.12))
        edge.setColorAt(1, alpha(WHITE, 0.26))
        g.setPen(draw.QPen(edge, 1))
        g.setBrush(Qt.BrushStyle.NoBrush)
        g.drawPath(path)
        g.save()
        g.scale(Ui.zoom, Ui.zoom)
        self.painter(g, QRectF(0, 0, box.width() / Ui.zoom, box.height() / Ui.zoom))
        g.restore()

    def place(self, r: QRect) -> None:
        if self.geometry() != r:
            self.setGeometry(r)
        self.update()

    def appear(self) -> None:
        if not self.isVisible():
            self.show()
            self.raise_()

    def enterEvent(self, e) -> None:
        self.owner.mouse(self, "enter", None)

    def leaveEvent(self, e) -> None:
        self.owner.mouse(self, "exit", None)

    def mouseMoveEvent(self, e) -> None:
        self.owner.mouse(self, "drag" if e.buttons() & Qt.MouseButton.LeftButton else "move", e)

    def mousePressEvent(self, e) -> None:
        self.owner.mouse(self, "down", e)

    def mouseReleaseEvent(self, e) -> None:
        self.owner.mouse(self, "up", e)

    def wheelEvent(self, e) -> None:
        self.owner.mouse(self, "wheel", e)


class Overlay(Painting, QObject):
    light, pad, panel_width, gap, inner = 44.0, 4.0, 380.0, 6.0, 12.0
    key_pressed = Signal(str)
    key_released = Signal(str)

    def __init__(self):
        super().__init__()
        self.rows: dict[str, Row] = {}
        self.order: list[Row] = []
        self.history: list = []
        self.usage: list = []
        self.muted = False
        self.request: dict | None = None
        self.banner: dict | None = None
        self.banner_until = float("inf")
        self.talk_state = self.talk_name = self.talk_text = self.talk_hint = ""
        self.talk_quiet = False
        self.talk_until = float("inf")
        self.mic = draw.Wave()
        self.live_keys: set = set()
        self.mode, self.layout, self.corner, self.glass = "dots", "bar", "top-right", "blur"
        self.offset_x, self.offset_y, self.island_x, self.island_y = 12.0, 96.0, 0.5, 10.0
        self.monitor = 0
        self.opaque = self.still_asked = False
        self.details_style, self.usage_rows, self.choice_caps = "tiles", True, False
        self.history_all, self.focus_history, self.hover_opens, self.muted_line = False, True, True, True
        self.wanted_keys: dict = {}
        self.hover_bar = self.hover_panel = self.peek = False
        self.hot_name: str | None = None
        self.drag_from: QPoint | None = None
        self.drag_start = QRect()
        self.dragged = False
        self.keys_open = False
        self.held_since: float | None = None
        self.bubble_row: Row | None = None
        self.panel_blocks: list = []
        self.bar = Glass(self, self.paint_bar, True)
        self.panel = Glass(self, self.paint_panel, True)
        self.bubble = Glass(self, self.paint_bubble, False)
        self.panel.radius = self.bubble.radius = 12
        self.settings = None
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.frame)
        self.last_frame = now()
        self.key_pressed.connect(self._pressed)
        self.key_released.connect(self._released)
        import keys
        self.keys = keys.Hotkeys(self.key_pressed.emit, self.key_released.emit, note)

    # --- messages from the hub ----------------------------------------------------------------

    def handle(self, msg: dict) -> None:
        kind = string(msg, "type")
        if kind == "config":
            self.configure(msg)
        elif kind == "state":
            self.muted = bool(msg.get("muted"))
            self.history = [h for h in (msg.get("history") or []) if isinstance(h, dict)]
            self.usage = [u for u in (msg.get("usage") or []) if isinstance(u, list)]
            self.sync_rows([s for s in (msg.get("sessions") or []) if isinstance(s, dict)])
            self.render()
        elif kind == "flash":
            row = self.rows.get(string(msg, "name"))
            if row:
                row.flash_text = string(msg, "text")
                row.flash_until = now() + num(msg, "seconds", 4)
            self.render()
        elif kind == "wave":
            row = self.rows.get(string(msg, "name"))
            if row:
                row.orb.wave.add(now() + num(msg, "delay"), num(msg, "step", 0.04), [float(v) for v in msg.get("levels") or []])
            self.run()
        elif kind == "mic":
            self.mic.add(now(), num(msg, "step", 0.05), [float(v) for v in msg.get("levels") or []])
            self.run()
        elif kind == "talk":
            self.talk(msg)
        elif kind == "request":
            self.request = msg if "text" in msg else None
            self.render()
        elif kind == "banner":
            self.banner = msg if msg.get("text") is not None else None
            seconds = num(msg, "seconds")
            self.banner_until = now() + seconds if seconds > 0 else float("inf")
            self.render()
        elif kind == "keys":
            self.live_keys = set(str(k) for k in msg.get("live") or [])
            self.register_keys()
        elif kind == "mode":
            self.set_mode(string(msg, "mode", "toggle"), tell=False)
        elif kind == "peek":
            self.peek = bool(msg.get("on"))
            self.render()
        elif kind == "settings":
            self.show_settings(msg)
        elif kind == "bounds":
            send(self.bounds())
        elif kind == "shot":  # the picture check (tests/linux_check.py): each piece saved as it is drawn
            self.shot(string(msg, "path"))
        elif kind == "quit":
            QApplication.quit()

    def configure(self, msg: dict) -> None:
        before = self.corner + self.layout
        self.corner = string(msg, "corner", self.corner)
        self.offset_x, self.offset_y = num(msg, "offset_x", self.offset_x), num(msg, "offset_y", self.offset_y)
        self.island_x, self.island_y = num(msg, "island_x", self.island_x), num(msg, "island_y", self.island_y)
        self.monitor = int(num(msg, "monitor", self.monitor))
        self.opaque = bool(msg.get("opaque", self.opaque))
        if "still" in msg:
            self.still_asked = bool(msg["still"])
        Ui.motionless = self.still_asked
        Ui.zoom = max(0.5, min(2.0, num(msg, "size", Ui.zoom * 100) / 100))
        if "mic_color" in msg:
            Ui.mic = draw.color(string(msg, "mic_color")) or Ui.mic
        if "waiting_color" in msg:
            Ui.waiting = draw.color(string(msg, "waiting_color")) or Ui.waiting
        Ui.set_state_colors(msg)
        if "details_style" in msg:
            self.details_style = "line" if msg["details_style"] == "line" else "tiles"
        if "choice_caps" in msg:
            self.choice_caps = bool(msg["choice_caps"])
        Ui.context_warn = num(msg, "context_warn", Ui.context_warn)
        if "context_color" in msg:
            Ui.context = draw.color(string(msg, "context_color")) or QColor(WHITE)
        if "context_warn_color" in msg:
            Ui.context_full = draw.color(string(msg, "context_warn_color")) or Ui.context_full
        Ui.waiting_hold = max(0.0, num(msg, "waiting_hold", Ui.waiting_hold))
        Ui.waiting_size = max(5.0, min(13.0, num(msg, "waiting_size", Ui.waiting_size)))
        if "waiting_many" in msg:
            Ui.waiting_many = "number" if msg["waiting_many"] == "number" else "face"
        if "waiting_cover" in msg:
            Ui.waiting_cover = msg["waiting_cover"] if msg["waiting_cover"] in ("each", "first") else "never"
        if "waiting_mark" in msg:
            Ui.waiting_mark = msg["waiting_mark"] if msg["waiting_mark"] in ("dot", "clock") else "number"
        self.glass = string(msg, "glass", self.glass)
        Ui.glass_clear = num(msg, "glass_clear", Ui.glass_clear)
        self.layout = "island" if string(msg, "layout", self.layout) == "island" else "bar"
        Ui.row_lines = max(1, min(3, int(num(msg, "row_lines", Ui.row_lines))))
        if "talk_sign" in msg:
            Ui.sign_in_light = msg["talk_sign"] != "line"
        if "history" in msg:
            self.history_all = msg["history"] == "all"
        if "focus_history" in msg:
            self.focus_history = msg["focus_history"] != "rest"
        if "usage_layout" in msg:
            self.usage_rows = msg["usage_layout"] != "line"
        if "hover" in msg:
            self.hover_opens = msg["hover"] != "keys"
        if "muted_line" in msg:
            self.muted_line = bool(msg["muted_line"])
        if isinstance(msg.get("hotkeys"), dict):
            self.wanted_keys = {k: str(v) for k, v in msg["hotkeys"].items()}
            self.register_keys()
        if "mode" in msg:
            self.mode = string(msg, "mode", self.mode)
        look = "solid" if self.opaque else self.glass
        for w in (self.bar, self.panel, self.bubble):
            w.look = look
        if before != self.corner + self.layout:
            self.hot_name = None
        self.render()

    def sync_rows(self, sessions: list) -> None:
        names = set()
        self.order = []
        for s in sessions:
            name = string(s, "name")
            row = self.rows.setdefault(name, Row())
            row.update(s)
            self.order.append(row)
            names.add(name)
        for gone in [n for n in self.rows if n not in names]:
            del self.rows[gone]
        if self.hot_name and self.hot_name not in self.rows:
            self.hot_name = None

    def talk(self, msg: dict) -> None:
        state = string(msg, "state")
        if state == "listening" and self.talk_state != "listening":
            self.mic.clear()
        self.talk_state, self.talk_name = state, string(msg, "name")
        self.talk_text, self.talk_hint = string(msg, "text"), string(msg, "hint")
        self.talk_quiet = bool(msg.get("quiet"))
        seconds = num(msg, "seconds")
        self.talk_until = now() + seconds if seconds > 0 else float("inf")
        self.render()

    def talk_kind(self) -> str:
        return {"listening": "mic", "transcribing": "dots", "ready": "dots", "aside": "dots", "sent": "sent",
                "queued": "wait" if Ui.waiting_mark == "clock" else "", "failed": "failed", "stopped": "stop"}.get(self.talk_state, "")

    def talk_words(self) -> str:
        quoted = "“" + self.talk_text + "”"
        return {"listening": "Release to send", "transcribing": "Working out what you said…",
                "ready": quoted + ("\n" + self.talk_hint if self.talk_hint else ""),
                "aside": quoted + ("\n" + self.talk_hint if self.talk_hint else ""),
                "sent": quoted, "queued": quoted + "\nIt gets this right after its current reply",
                "focus": "In focus"}.get(self.talk_state, self.talk_text)

    def set_mode(self, wanted: str, tell: bool = True) -> None:
        if wanted == "toggle":
            self.mode = {"dots": "list", "list": "focus"}.get(self.mode, "dots")
        else:
            self.mode = wanted if wanted in ("list", "focus") else "dots"
        if tell:
            send({"type": "mode", "mode": self.mode})
        self.render()

    # --- what shows ---------------------------------------------------------------------------

    @property
    def listed(self) -> bool:
        return self.mode in ("list", "focus")

    @property
    def hover(self) -> bool:
        return self.hover_bar or self.hover_panel

    @property
    def has_banner(self) -> bool:
        return self.banner is not None and now() < self.banner_until

    @property
    def island(self) -> bool:
        return self.layout == "island"

    def is_open(self) -> bool:
        return (self.listed or (self.hover and self.hover_opens) or self.keys_open or self.peek or self.request is not None
                or self.has_banner or self.dragged)

    def chosen(self) -> Row | None:
        if self.hot_name in self.rows:
            return self.rows[self.hot_name]
        return next((r for r in self.order if r.focus), None) or next((r for r in self.order if r.speaking), None) or (self.order[0] if self.order else None)

    def render(self) -> None:
        if now() >= self.talk_until:
            self.talk_state, self.talk_until = "", float("inf")
        if self.banner is not None and now() >= self.banner_until:
            self.banner = None
        talking = bool(self.talk_state)
        for row in self.order:
            if talking and row.name == self.talk_name:
                kind = self.talk_kind()
                listening = self.talk_state == "listening"
                changed = row.talk_kind != kind or (row.orb.listening is not None) != listening
                row.talk_kind, row.talk_text, row.talk_bold = kind, self.talk_words(), listening
                row.talk_ink = draw.mix(Ui.mic, WHITE, 0.55) if listening else WHITE if self.talk_state in ("ready", "aside", "sent", "queued") else Ui.dim
                row.orb.listening = self.mic if listening else None
                row.orb.show_sign(kind if Ui.sign_in_light else "")
                if changed:
                    row.orb.changed = now()
            elif row.talk_kind is not None:
                row.talk_kind, row.orb.listening = None, None
                row.orb.show_sign("")
                row.orb.changed = now()
        show = self.listed or self.request is not None or self.has_banner or talking or bool(self.order)
        self.layout_windows(show)
        self.run()

    # --- places -------------------------------------------------------------------------------

    def area(self) -> QRect:
        screens = QGuiApplication.screens()
        screen = screens[self.monitor] if 0 < self.monitor < len(screens) else QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def bar_size(self) -> tuple[float, float]:
        n, z = max(1, len(self.order)), Ui.zoom
        if self.island:
            return (n * self.light + 2 * self.pad) * z, (self.light + 2 * self.pad + 4) * z
        return (self.light + 2 * self.pad) * z, (n * self.light + 2 * self.pad) * z

    def bar_frame(self) -> QRect:
        if self.drag_from is not None and self.dragged:
            d = QCursor.pos() - self.drag_from
            return self.drag_start.translated(d)
        a = self.area()
        w, h = self.bar_size()
        if self.island:
            return QRect(round(a.x() + self.island_x * a.width() - w / 2), round(a.y() + self.island_y), round(w), round(h))
        right, low = self.corner.endswith("right"), self.corner.startswith("bottom")
        x = a.right() + 1 - self.offset_x - w if right else a.x() + self.offset_x
        y = a.bottom() + 1 - self.offset_y - h if low else a.y() + self.offset_y
        y = max(a.y(), min(y, a.bottom() + 1 - h))
        return QRect(round(x), round(y), round(w), round(h))

    def light_center(self, index: int, box: QRect) -> QPointF:
        z = Ui.zoom
        along = (self.pad + self.light * (index + 0.5)) * z
        if self.island:
            return QPointF(box.x() + along, box.y() + (self.pad + self.light / 2) * z)
        return QPointF(box.x() + box.width() / 2, box.y() + along)

    def layout_windows(self, show: bool) -> None:
        if not show:
            for w in (self.bar, self.panel, self.bubble):
                w.hide()
            return
        box = self.bar_frame()
        self.bar.place(box)
        self.bar.appear()
        z = Ui.zoom
        a = self.area()
        right = self.corner.endswith("right")
        if self.is_open():
            self.panel_blocks = self.build_panel()
            w = self.panel_width * z
            h = (sum(b.height for b in self.panel_blocks) + 12) * z
            if self.island:
                x, y = box.center().x() - w / 2, box.bottom() + 1 + self.gap * z
            else:
                first = next((i for i, b in enumerate(self.panel_blocks) if b.kind == "row"), None)
                above = sum(b.height for b in self.panel_blocks[:first]) if first is not None else 0
                row = self.panel_blocks[first].row if first is not None else None
                index = self.order.index(row) if row in self.order else 0
                light_top = self.light_center(index, box).y() - self.light / 2 * z
                x = box.x() - self.gap * z - w if right else box.right() + 1 + self.gap * z
                y = light_top - (above + 6) * z
            y = max(a.y(), min(y, a.bottom() + 1 - h))
            self.panel.place(QRect(round(x), round(y), round(w), round(h)))
            self.panel.appear()
        else:
            self.panel.hide()
        self.bubble_row = None
        if not self.is_open():
            talker = next((r for r in self.order if r.name == self.talk_name and r.talk_kind is not None
                           and not (self.talk_quiet and any(o.speaking for o in self.order))), None)
            self.bubble_row = talker or next((r for r in self.order if r.saying and r.speaking), None) or next((r for r in self.order if r.saying), None)
        if self.bubble_row is not None:
            index = self.order.index(self.bubble_row)
            w, h = self.panel_width * z, self.bubble_height(self.bubble_row) * z
            c = self.light_center(index, box)
            if self.island:
                x, y = c.x() - w / 2, box.bottom() + 1 + self.gap * z
            else:
                x = box.x() - self.gap * z - w if right else box.right() + 1 + self.gap * z
                y = c.y() - h / 2
            x = max(a.x(), min(x, a.right() + 1 - w))
            y = max(a.y(), min(y, a.bottom() + 1 - h))
            self.bubble.place(QRect(round(x), round(y), round(w), round(h)))
            self.bubble.appear()
        else:
            self.bubble.hide()

    # --- the frame clock ----------------------------------------------------------------------

    def glow_goal(self, row: Row) -> float:
        return max(0.11 if row.name == self.hot_name else 0, 0.085 if row.showing else 0, 0.06 if row.focus else 0)

    def moving(self) -> bool:
        if any(r.orb.moving or r.saying for r in self.order) or self.talk_state or self.has_banner or self.dragged:
            return True
        return any(abs(r.lit - self.glow_goal(r)) > 0.004 for r in self.order)

    def run(self) -> None:
        if not self.timer.isActive():
            self.last_frame = now()
            self.timer.start()

    def frame(self) -> None:
        t = now()
        dt = min(0.1, t - self.last_frame)
        self.last_frame = t
        for row in self.order:
            goal = self.glow_goal(row)
            row.lit = goal if abs(goal - row.lit) < 0.004 else row.lit + (goal - row.lit) * (1 - math.exp(-14 * dt))
        was_open, was_bubble = self.panel.isVisible(), self.bubble_row
        if (self.banner is not None and t >= self.banner_until) or t >= self.talk_until:
            self.render()
            return
        gone = was_bubble is not None and not was_bubble.showing
        if was_open != self.is_open() or gone or (was_bubble is None and not self.is_open() and any(r.saying for r in self.order)):
            self.render()
        else:
            for w in (self.bar, self.panel, self.bubble):
                if w.isVisible():
                    w.update()
        if not self.moving():
            self.timer.stop()

    # --- the mouse and the keys ---------------------------------------------------------------

    def mouse(self, window: Glass, kind: str, e) -> None:
        if window is self.bar:
            if kind == "enter":
                self.hover_bar = True
                self.render()
            elif kind == "exit":
                self.hover_bar = False
                self.close_soon()
            elif kind == "move":
                p = e.position()
                along = (p.x() if self.island else p.y()) / Ui.zoom - self.pad
                index = int(math.floor(along / self.light))
                name = self.order[index].name if 0 <= index < len(self.order) else None
                if name != self.hot_name:
                    self.hot_name = name
                    self.render()
            elif kind == "down":
                self.drag_from, self.drag_start, self.dragged = QCursor.pos(), self.bar.geometry(), False
            elif kind == "drag" and self.drag_from is not None:
                if not self.dragged and (QCursor.pos() - self.drag_from).manhattanLength() > 3:
                    self.dragged = True
                if self.dragged:
                    self.render()
            elif kind == "up":
                if self.dragged:
                    self.settle()
                self.drag_from, self.dragged = None, False
                self.render()
            elif kind == "wheel":
                dy = e.angleDelta().y()
                if abs(dy) > 2:
                    send({"type": "hotkey", "name": "focus_prev" if dy > 0 else "focus_next"})
        elif window is self.panel:
            if kind == "enter":
                self.hover_panel = True
            elif kind == "exit":
                self.hover_panel = False
                self.close_soon()
            elif kind == "move":
                y, top, found = e.position().y() / Ui.zoom - 6, 0.0, None
                for b in self.panel_blocks:
                    if b.kind == "row" and b.row is not None and top <= y < top + b.height:
                        found = b.row.name
                    top += b.height
                if found and found != self.hot_name:
                    self.hot_name = found
                    self.panel.update()

    def close_soon(self) -> None:
        def later():
            if not self.hover:
                self.hot_name = None
                self.render()
        QTimer.singleShot(250, later)

    def settle(self) -> None:
        box, a = self.bar.geometry(), self.area()
        if self.island:
            self.island_x = (box.center().x() - a.x()) / max(1, a.width())
            self.island_y = max(0, box.y() - a.y())
            send({"type": "moved", "island_x": self.island_x, "island_y": self.island_y, "monitor": self.monitor})
            return
        near_right, near_bottom = box.center().x() > a.center().x(), box.center().y() > a.center().y()
        self.corner = ("bottom" if near_bottom else "top") + "-" + ("right" if near_right else "left")
        self.offset_x = max(0, a.right() - box.right() if near_right else box.x() - a.x())
        self.offset_y = max(0, a.bottom() - box.bottom() if near_bottom else box.y() - a.y())
        send({"type": "moved", "corner": self.corner, "offset_x": self.offset_x, "offset_y": self.offset_y, "monitor": self.monitor})

    def register_keys(self) -> None:
        always = {"toggle", "talk", "repeat", "layout", "settings", "mute"}
        wanted = {}
        for name, combo in self.wanted_keys.items():
            if name in always or name in self.live_keys:
                if self.island and name in ("focus_prev", "focus_next"):
                    continue
                if not self.island and name in ("focus_left", "focus_right"):
                    continue
                wanted[name] = combo
        if self.island:
            for prev, side in (("focus_prev", "focus_left"), ("focus_next", "focus_right")):
                if prev in self.live_keys and self.wanted_keys.get(side):
                    wanted[prev] = self.wanted_keys[side]
                wanted.pop(side, None)
        self.keys.set(wanted)

    def _pressed(self, name: str) -> None:
        if name == "toggle":
            self.set_mode("toggle")
            return
        send({"type": "hotkey", "name": name})

    def _released(self, name: str) -> None:
        if name == "talk":
            send({"type": "hotkey", "name": "talk_end"})

    # --- the settings window ------------------------------------------------------------------

    def show_settings(self, msg: dict) -> None:
        if "open" in msg and not msg.get("open"):
            if self.settings:
                self.settings.hide_window()
            return
        if msg.get("toggle") and self.settings and self.settings.isVisible():
            self.settings.hide_window()
            send({"type": "settings", "open": False})
            return
        if self.settings is None:
            import settings_window
            self.settings = settings_window.SettingsWindow(
                choose=lambda key, value: send({"type": "setting", "key": key, "value": value}),
                closed=lambda: send({"type": "settings", "open": False}),
                typing=self.keys.pause, previewing=self.preview)
        self.settings.show_sections(msg.get("sections") or [], string(msg, "section"), string(msg, "title", "Sidetone"), bool(msg.get("quiet")))

    def preview(self, key: str, value) -> None:
        if not key.startswith("overlay."):
            return
        name = key[8:]
        if name == "size" and isinstance(value, (int, float)):
            Ui.zoom = value / 100
        elif name == "glass_clear" and isinstance(value, (int, float)):
            Ui.glass_clear = float(value)
        elif name == "mic_color":
            Ui.mic = draw.color(str(value)) or Ui.mic
        elif isinstance(value, str):
            Ui.set_state_colors({name: value})
        self.render()

    # --- for the picture check ----------------------------------------------------------------

    def windows(self) -> list[QWidget]:
        return [self.bar, self.panel, self.bubble] + ([self.settings] if self.settings else [])

    def bounds(self) -> dict:
        pieces = [[w.x(), w.y(), w.width(), w.height()] for w in self.windows() if w.isVisible()]
        return {"type": "bounds", "pieces": pieces, "open": self.is_open(), "platform": QGuiApplication.platformName()}

    def shot(self, path: str) -> None:
        """The visible pieces drawn together on a dark backdrop, in their places, saved to `path`."""
        from PySide6.QtGui import QImage
        shown = [w for w in self.windows() if w.isVisible()]
        if not shown:
            send({"type": "shot", "path": ""})
            return
        left = min(w.x() for w in shown) - 24
        top = min(w.y() for w in shown) - 24
        right = max(w.x() + w.width() for w in shown) + 24
        bottom = max(w.y() + w.height() for w in shown) + 24
        image = QImage(right - left, bottom - top, QImage.Format.Format_ARGB32)
        image.fill(QColor(32, 36, 44))
        g = QPainter(image)
        for w in shown:
            g.drawPixmap(w.x() - left, w.y() - top, w.grab())
        g.end()
        image.save(path)
        send({"type": "shot", "path": path})


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    overlay = Overlay()
    reader = Reader()
    reader.arrived.connect(overlay.handle)
    reader.ended.connect(app.quit)
    reader.start()
    send({"type": "ready"})
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
