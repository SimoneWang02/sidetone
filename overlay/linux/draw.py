"""Colors, motion and the drawing of a session's light, for the Linux overlay. A port of the Mac
overlay's Theme.swift and Orb.swift (themselves after the Windows overlay's Ui, Orb, Badge and
Wave), with QPainter in place of Core Graphics; y grows downward in all three."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen


def now() -> float:
    return time.monotonic()


def color(hex_: str, fallback: str | None = None) -> QColor | None:
    """"#RRGGBB" or "#AARRGGBB"; the fallback (or None) for anything else."""
    text = (hex_ or "").strip().lstrip("#")
    if len(text) in (6, 8):
        try:
            value = int(text, 16)
        except ValueError:
            value = None
        if value is not None:
            a = (value >> 24) & 0xFF if len(text) == 8 else 255
            return QColor((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF, a)
    return color(fallback) if fallback else None


def alpha(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(max(0.0, min(1.0, a)) * c.alphaF())
    return out


def mix(a: QColor, b: QColor, share: float) -> QColor:
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * share, a.greenF() + (b.greenF() - a.greenF()) * share,
                           a.blueF() + (b.blueF() - a.blueF()) * share, a.alphaF() + (b.alphaF() - a.alphaF()) * share)


WHITE = QColor(255, 255, 255)


class Ui:
    working = color("#4FC3F7")
    amber = color("#FFB300")
    done = color("#66BB6A")
    failed = color("#EF5350")
    idle = color("#B0B6C0")
    mic = color("#006896")
    waiting = color("#FF3B30")
    context = QColor(WHITE)
    context_full = color("#FF8A3D")
    context_warn = 80.0
    glass_tint = ""
    glass_clear = 50.0
    waiting_mark = "number"
    waiting_size = 9.2
    waiting_hold = 0.9
    waiting_many = "face"
    waiting_cover = "never"
    sign_in_light = True
    row_lines = 1
    motionless = False
    zoom = 1.0
    dim = alpha(WHITE, 0.72)
    faint = alpha(WHITE, 0.5)
    slate = color("#3A4150")
    accent = color("#006896")

    @staticmethod
    def tint(state: str) -> QColor:
        return {"working": Ui.working, "needs_you": Ui.amber, "done": Ui.done, "failed": Ui.failed}.get(state, Ui.idle)

    @staticmethod
    def set_state_colors(msg: dict) -> None:
        for key, attr, fallback in (("working_color", "working", "#4FC3F7"), ("needs_you_color", "amber", "#FFB300"),
                                    ("done_color", "done", "#66BB6A"), ("failed_color", "failed", "#EF5350"),
                                    ("idle_color", "idle", "#B0B6C0")):
            if key in msg:
                setattr(Ui, attr, color(str(msg[key] or ""), fallback))
        if "glass_color" in msg:
            Ui.glass_tint = str(msg["glass_color"] or "")

    @staticmethod
    def glass_top() -> QColor:
        return color(Ui.glass_tint) or Ui.slate


def clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out(x: float) -> float:
    y = 1 - clamp(x)
    return 1 - y * y * y


def overshoot(x: float) -> float:
    y = clamp(x) - 1
    return 1 + 2.4 * y * y * y + 1.4 * y * y


def font(size: float, weight: str = "regular") -> QFont:
    f = QFont()
    f.setPixelSize(max(1, round(size * 1.0)))
    f.setWeight({"regular": QFont.Weight.Normal, "medium": QFont.Weight.Medium, "semibold": QFont.Weight.DemiBold,
                 "bold": QFont.Weight.Bold}[weight])
    return f


def mono(size: float) -> QFont:
    f = QFont("monospace")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPixelSize(round(size))
    return f


# --- drawing helpers ---------------------------------------------------------------------------

def pen(c: QColor, width: float) -> QPen:
    p = QPen(c, width)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def circle(g: QPainter, c: QPointF, r: float, fill: QColor | None = None, stroke: QColor | None = None, width: float = 1) -> None:
    g.setPen(pen(stroke, width) if stroke is not None else Qt.PenStyle.NoPen)
    g.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
    g.drawEllipse(c, r, r)


def line(g: QPainter, a: QPointF, b: QPointF, c: QColor, width: float) -> None:
    g.setPen(pen(c, width))
    g.drawLine(a, b)


def arc_path(c: QPointF, r: float, a: float, b: float) -> QPainterPath:
    """An arc from angle a to b (radians, clockwise on screen since y grows downward)."""
    path = QPainterPath()
    steps = max(4, int(abs(b - a) / (math.pi / 36)))
    for i in range(steps + 1):
        t = a + (b - a) * i / steps
        p = QPointF(c.x() + r * math.cos(t), c.y() + r * math.sin(t))
        path.moveTo(p) if i == 0 else path.lineTo(p)
    return path


def stroke_path(g: QPainter, path: QPainterPath, c: QColor, width: float) -> None:
    g.setPen(pen(c, width))
    g.setBrush(Qt.BrushStyle.NoBrush)
    g.drawPath(path)


def rounded(g: QPainter, rect: QRectF, r: float, fill: QColor | None = None, stroke: QColor | None = None, width: float = 1) -> None:
    g.setPen(pen(stroke, width) if stroke is not None else Qt.PenStyle.NoPen)
    g.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
    r = min(r, rect.width() / 2, rect.height() / 2)
    g.drawRoundedRect(rect, r, r)


def P(x: float, y: float) -> QPointF:
    return QPointF(x, y)


# --- words ---------------------------------------------------------------------------------------

class Words:
    """A run of words with their own fonts and colors."""

    def __init__(self, text: str = "", f: QFont | None = None, c: QColor | None = None):
        self.parts: list[tuple[str, QFont, QColor]] = []
        if text and f is not None:
            self.parts.append((text, f, c or WHITE))

    def add(self, text: str, f: QFont, c: QColor) -> "Words":
        if text:
            self.parts.append((text, f, c))
        return self

    def width(self) -> float:
        return sum(QFontMetricsF(f).horizontalAdvance(t) for t, f, _ in self.parts)

    def line_height(self) -> float:
        return max((QFontMetricsF(f).lineSpacing() for _, f, _ in self.parts), default=16.0)

    def height(self, width: float, lines: int = 1) -> float:
        if not self.parts:
            return 0.0
        if lines == 1 or len(self.parts) > 1:
            return self.line_height()
        text, f, _ = self.parts[0]
        box = QFontMetricsF(f).boundingRect(QRectF(0, 0, width, 10000), int(Qt.TextFlag.TextWordWrap), text)
        most = self.line_height() * lines if lines > 0 else 1e9
        return min(math.ceil(box.height()), most)

    def draw(self, g: QPainter, rect: QRectF, lines: int = 1, align: str = "left") -> None:
        """One line (the last part cut with dots where it does not fit), or one wrapped part."""
        if not self.parts:
            return
        if lines != 1 and len(self.parts) == 1:
            text, f, c = self.parts[0]
            g.setFont(f)
            g.setPen(c)
            most = self.line_height() * lines if lines > 0 else rect.height()
            g.save()
            g.setClipRect(QRectF(rect.x(), rect.y(), rect.width(), min(rect.height(), most) + 1))
            g.drawText(QRectF(rect.x(), rect.y(), rect.width(), 10000), int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignLeft), text)
            g.restore()
            return
        x = rect.x()
        if align != "left":
            spare = rect.width() - self.width()
            x += spare if align == "right" else spare / 2
        base = rect.y() + max(QFontMetricsF(f).ascent() for _, f, _ in self.parts)
        for text, f, c in self.parts:
            metrics = QFontMetricsF(f)
            room = rect.right() - x
            if room <= 4:
                break
            shown = metrics.elidedText(text.replace("\n", " "), Qt.TextElideMode.ElideRight, room)
            g.setFont(f)
            g.setPen(c)
            g.drawText(QPointF(x, base), shown)
            x += metrics.horizontalAdvance(shown)


# --- a voice's loudness over time ---------------------------------------------------------------

class Wave:
    lag = 0.05

    def __init__(self):
        self.times: list[float] = []
        self.levels: list[float] = []
        self.step = 0.04
        self.synthetic = False
        self.since = float("inf")

    def add(self, start: float, every: float, values: list[float]) -> None:
        self.step = every
        old = next((i for i, t in enumerate(self.times) if t >= now() - 6), len(self.times))
        del self.times[:old]
        del self.levels[:old]
        if self.times and start < self.times[-1] + self.step:
            start = self.times[-1] + self.step
        for i, v in enumerate(values):
            self.times.append(start + i * self.step)
            self.levels.append(v)

    def clear(self) -> None:
        self.times.clear()
        self.levels.clear()
        self.since = float("inf")

    def at(self, t: float) -> float:
        if self.synthetic:
            if t < self.since:
                return 0.0
            syllable = abs(math.sin(t * 9.1)) * (0.55 + 0.45 * math.sin(t * 2.3 + 1.0))
            return max(0.08, min(1.0, 0.15 + 0.85 * syllable * (0.6 + 0.4 * math.sin(t * 0.9))))
        for i in range(len(self.times) - 1, -1, -1):
            if self.times[i] > t:
                continue
            after = t - self.times[i]
            if i + 1 < len(self.times) and self.times[i + 1] - self.times[i] < 3 * self.step:
                return self.levels[i] + (self.levels[i + 1] - self.levels[i]) * after / (self.times[i + 1] - self.times[i])
            return self.levels[i] * (1 - after / 0.2) if after < 0.2 else 0.0
        return 0.0


# --- one session's light ------------------------------------------------------------------------

class Orb:
    size = 36
    weights = (0.5, 0.8, 1.0, 0.8, 0.5)
    gauge_at, gauge_grows, mark_move = 16.5, 0.6, 0.55

    def __init__(self):
        self.state = "idle"
        self.sign = ""
        self.speaking = False
        self.waiting = 0
        self.waiting_since = -10.0
        self.covers = True
        self.wave = Wave()
        self.listening: Wave | None = None
        self.born = now()
        self.changed = -10.0
        self.hot = 0.0
        self.sign_since = 0.0
        self.context = -1.0
        self._context_from = 0.0
        self._context_since = -10.0

    def set_context(self, percent: float) -> None:
        if abs(percent - self.context) < 0.05:
            return
        self._context_from = max(0.0, self._context_now(now()))
        self._context_since = now()
        self.context = percent

    def _context_now(self, t: float) -> float:
        k = 1 if Ui.motionless else ease_out((t - self._context_since) / Orb.gauge_grows)
        return self._context_from + (self.context - self._context_from) * k

    def show_sign(self, kind: str) -> None:
        if kind != self.sign:
            self.sign = kind
            self.sign_since = now()

    @property
    def _signed(self) -> bool:
        return bool(self.sign) and self.sign != "mic" and self.listening is None

    @property
    def moving(self) -> bool:
        t = now()
        if self._signed and (self.sign in ("dots", "wait") or t - self.sign_since < 0.5):
            return True
        if self.waiting > 0 and (Ui.waiting_mark != "number" or t - self.waiting_since < Ui.waiting_hold + Orb.mark_move + 0.1):
            return True
        if self.context >= 0 and t - self._context_since < Orb.gauge_grows + 0.1:
            return True
        return (self.speaking or self.listening is not None or self.state in ("working", "needs_you")
                or t - self.changed < 0.8 or t - self.born < 0.45)

    def draw(self, g: QPainter, c: QPointF) -> None:
        t = now()
        age = t - self.changed
        signed = self._signed
        if signed:
            tint = Ui.tint("done") if self.sign == "sent" else Ui.tint("failed") if self.sign in ("failed", "stop") else Ui.mic
        else:
            tint = Ui.mic if self.listening is not None else Ui.tint(self.state)
        wave = self.listening or self.wave
        bump = 0.2 * math.sin(math.pi * age / 0.4) if age < 0.4 else 0
        scale = (1 if Ui.motionless else overshoot((t - self.born) / 0.4)) * (1 + bump + 0.14 * self.hot)
        g.save()
        g.translate(c)
        g.scale(scale, scale)
        o = P(0, 0)
        self._gauge(g, t)
        if age < 0.8 and self.listening is None and (signed or (not self.speaking and self.state not in ("idle", "working"))) and not Ui.motionless:
            ring = ease_out(age / 0.8)
            circle(g, o, 13 + 9 * ring, stroke=alpha(tint, 0.7 * (1 - ring)), width=2)
        if signed:
            circle(g, o, 13, fill=alpha(tint, 0.30), stroke=alpha(tint, 0.95), width=1.5)
            Badge.draw(g, self.sign, o, t, t - self.sign_since, True)
            if self.sign != "wait":
                self._mark(g, t)
            g.restore()
            return
        if self.speaking or self.listening is not None:
            level = wave.at(t - Wave.lag)
            circle(g, o, 13.5 + 4 * level, fill=alpha(tint, 0.10 + 0.22 * level))
            circle(g, o, 13, fill=alpha(tint, 0.30), stroke=alpha(tint, 0.95), width=1.5)
            for i in range(5):
                h = 3 + 17 * Orb.weights[i] * wave.at(t - Wave.lag - abs(i - 2) * 0.07)
                rounded(g, QRectF((i - 2) * 4.4 - 1.3, -h / 2, 2.6, h), 1.3, fill=WHITE)
            self._mark(g, t)
            g.restore()
            return
        motion = 0 if Ui.motionless else t
        if self.state == "working":
            circle(g, o, 12, fill=alpha(tint, 0.14), stroke=alpha(tint, 0.28), width=2)
            a = motion * 4.6
            b = a + 1.5 + 0.9 * math.sin(motion * 2.1)
            stroke_path(g, arc_path(o, 12, a, b), tint, 2.2)
            circle(g, o, 3 + 0.5 * math.sin(motion * 4.2), fill=alpha(tint, 0.95))
        elif self.state == "needs_you":
            pulse = 0.6 if Ui.motionless else 0.5 + 0.5 * math.sin(t * 4.5)
            circle(g, o, 13 + 4.5 * pulse, fill=alpha(tint, 0.14 * pulse))
            circle(g, o, 13, fill=alpha(tint, 0.38 + 0.30 * pulse), stroke=tint, width=1.5)
            line(g, P(0, -6.5), P(0, 1.5), WHITE, 2.6)
            circle(g, P(0, 6.3), 1.6, fill=WHITE)
        elif self.state == "done":
            circle(g, o, 13, fill=alpha(tint, 0.26), stroke=alpha(tint, 0.95), width=1.5)
            drawn = 1 if Ui.motionless else ease_out(age / 0.35)
            first, second = min(1, drawn / 0.4), clamp((drawn - 0.4) / 0.6)
            p0, p1, p2 = P(-5.6, 0.4), P(-1.8, 4.4), P(5.8, -4.2)
            ink = alpha(WHITE, 0.95)
            line(g, p0, P(p0.x() + (p1.x() - p0.x()) * first, p0.y() + (p1.y() - p0.y()) * first), ink, 2.3)
            if second > 0:
                line(g, p1, P(p1.x() + (p2.x() - p1.x()) * second, p1.y() + (p2.y() - p1.y()) * second), ink, 2.3)
        elif self.state == "failed":
            circle(g, o, 13, fill=alpha(tint, 0.30), stroke=alpha(tint, 0.95), width=1.5)
            reach = 4.6 * (1 if Ui.motionless else ease_out(age / 0.3))
            ink = alpha(WHITE, 0.95)
            line(g, P(-reach, -reach), P(reach, reach), ink, 2.3)
            line(g, P(reach, -reach), P(-reach, reach), ink, 2.3)
        else:
            circle(g, o, 12, fill=alpha(tint, 0.08), stroke=alpha(tint, 0.65), width=1.5)
            circle(g, o, 2.5, fill=alpha(tint, 0.65))
        self._mark(g, t)
        g.restore()

    def _gauge(self, g: QPainter, t: float) -> None:
        if self.context < 0:
            return
        share = clamp(self._context_now(t) / 100)
        ink = Ui.context_full if Ui.context_warn > 0 and self.context >= Ui.context_warn else Ui.context
        circle(g, P(0, 0), Orb.gauge_at, stroke=alpha(WHITE, 0.12), width=2)
        if share >= 0.995:
            circle(g, P(0, 0), Orb.gauge_at, stroke=alpha(ink, 0.85), width=2)
            return
        a = -math.pi / 2
        stroke_path(g, arc_path(P(0, 0), Orb.gauge_at, a, a + 2 * math.pi * max(share, 0.004)), alpha(ink, 0.85), 2)

    def _mark(self, g: QPainter, t: float) -> None:
        if self.waiting <= 0:
            return
        corner = P(10.5, -10.5)
        count = "9+" if self.waiting > 9 else str(self.waiting)
        rim = QColor(20, 20, 24, 230)
        if Ui.waiting_mark == "number":
            age = t - self.waiting_since
            k = 1 if Ui.motionless or not self.covers else clamp((age - Ui.waiting_hold) / Orb.mark_move)
            k = k * k * (3 - 2 * k)
            pop = 1 if Ui.motionless else overshoot(age / 0.3) if self.covers else 1 + (0.4 * math.sin(math.pi * age / 0.4) if age < 0.4 else 0)
            r = (13.5 + (Ui.waiting_size - 13.5) * k) * pop
            inward = max(0, Ui.waiting_size - 7.7) * k
            at = P(corner.x() * k - inward, corner.y() * k + inward)
            if self.waiting > 9 and Ui.waiting_many == "face":
                dismayed(g, at, r)
                return
            circle(g, at, r, fill=alpha(Ui.waiting, 0.97))
            number(g, count, at, (0.95 if len(count) > 1 else 1.25) * r)
            return
        if Ui.waiting_mark == "dot":
            breath = 0.5 + 0.5 * math.sin(t * 3.2)
            circle(g, corner, 5.2 + 2 * breath, fill=alpha(Ui.waiting, 0.22 * breath))
            circle(g, corner, 5.2, fill=rim)
            circle(g, corner, 3.8, fill=alpha(Ui.waiting, 0.85 + 0.15 * breath))
            return
        if self.waiting > 9:
            big = max(Ui.waiting_size, 8.4)
            at = P(corner.x() - (big - 6.4), corner.y() + (big - 6.4))
            if Ui.waiting_many == "face":
                dismayed(g, at, big)
                return
            circle(g, at, big + 1.6, fill=rim)
            circle(g, at, big, fill=alpha(Ui.waiting, 0.95), stroke=alpha(WHITE, 0.9), width=1.1)
            number(g, count, at, 0.95 * big)
            return
        circle(g, corner, 8, fill=rim)
        circle(g, corner, 6.4, fill=alpha(Ui.waiting, 0.95), stroke=alpha(WHITE, 0.9), width=1.1)
        if self.waiting > 1:
            number(g, count, corner, 9.5)
            return
        turn = t * 1.8
        line(g, corner, P(corner.x(), corner.y() - 4), WHITE, 1.3)
        line(g, corner, P(corner.x() + 3 * math.sin(turn), corner.y() - 3 * math.cos(turn)), WHITE, 1.3)


def dismayed(g: QPainter, at: QPointF, r: float) -> None:
    """More than nine messages: a dismayed face in the yellow of a smiley."""
    skin, ink = QColor(255, 206, 74), QColor(94, 64, 10)

    def p(x, y):
        return P(at.x() + x * r, at.y() + y * r)
    circle(g, at, r, fill=skin)
    path = QPainterPath()
    path.moveTo(p(-0.70, -0.28)); path.quadTo(p(-0.34, -0.30), p(-0.24, -0.52))
    path.moveTo(p(0.66, -0.28)); path.quadTo(p(0.28, -0.30), p(0.18, -0.54))
    path.moveTo(p(-0.36, 0.66)); path.quadTo(p(-0.26, 0.44), p(-0.04, 0.47))
    path.quadTo(p(0.14, 0.50), p(0.22, 0.42)); path.quadTo(p(0.38, 0.36), p(0.42, 0.60))
    stroke_path(g, path, ink, max(1.1, 0.12 * r))
    g.setPen(Qt.PenStyle.NoPen)
    g.setBrush(ink)
    g.drawEllipse(p(-0.36, -0.06), 0.13 * r, 0.17 * r)
    g.drawEllipse(p(0.36, -0.06), 0.13 * r, 0.17 * r)
    line(g, p(-0.46, 0.14), p(-0.24, 0.10), ink, max(0.9, 0.08 * r))
    line(g, p(0.22, 0.10), p(0.52, 0.09), ink, max(0.9, 0.08 * r))


def number(g: QPainter, text: str, at: QPointF, size: float) -> None:
    """A number set by the middle of its own strokes on the middle of its disc."""
    path = QPainterPath()
    path.addText(P(0, 0), font(size, "bold"), text)
    box = path.boundingRect()
    g.save()
    g.translate(at.x() - box.center().x(), at.y() - box.center().y())
    g.setPen(Qt.PenStyle.NoPen)
    g.setBrush(WHITE)
    g.drawPath(path)
    g.restore()


class Badge:
    """Push-to-talk's sign: in the light (white) or at the right of a row (in color)."""

    @staticmethod
    def draw(g: QPainter, kind: str, c: QPointF, t: float, age: float, in_light: bool) -> None:
        pop = (1 if Ui.motionless else overshoot(age / 0.35)) * (0.9 if in_light else 1)
        g.save()
        g.translate(c)
        g.scale(pop, pop)
        o = P(0, 0)
        if kind == "mic":
            microphone(g, alpha(WHITE if in_light else Ui.mic, 0.75 + 0.25 * math.sin(t * 5)))
        elif kind == "dots":
            for i in range(3):
                up = max(0.0, math.sin(t * 6 - i * 0.9))
                circle(g, P((i - 1) * 6, 2 - 4 * up), 2, fill=alpha(WHITE, 0.45 + 0.5 * up))
        elif kind == "sent":
            back = (1 - (1 if Ui.motionless else ease_out(age / 0.4))) * -9
            ink = WHITE if in_light else Ui.tint("done")

            def aim(along, across):
                cos_a, sin_a = 0.8192, -0.5736
                return P(along * cos_a - across * sin_a, along * sin_a + across * cos_a)
            nose, notch = aim(9 + back, 0), aim(-2.6 + back, 0)
            plane = QPainterPath(nose)
            plane.lineTo(aim(-6.2 + back, -6.5)); plane.lineTo(notch); plane.lineTo(aim(-6.2 + back, 6.5)); plane.closeSubpath()
            g.setPen(pen(ink, 1.5))
            g.setBrush(alpha(ink, 0.35))
            g.drawPath(plane)
            line(g, notch, nose, ink, 1.5)
        elif kind == "stop":
            rounded(g, QRectF(-5, -5, 10, 10), 2, fill=WHITE if in_light else Ui.tint("failed"))
        elif kind == "wait":
            ink = WHITE if in_light else Ui.mic
            turn = t * 1.8
            circle(g, o, 7.2, stroke=alpha(ink, 0.95), width=1.6)
            line(g, o, P(0, -4.8), ink, 1.7)
            line(g, o, P(3.6 * math.sin(turn), -3.6 * math.cos(turn)), ink, 1.7)
        elif kind == "failed":
            if in_light:
                microphone(g, alpha(WHITE, 0.6))
                reach = 7.5 * (1 if Ui.motionless else ease_out(age / 0.3))
                line(g, P(-reach, -reach), P(reach, reach), Ui.tint("failed"), 5)
                line(g, P(-reach, -reach), P(reach, reach), WHITE, 2)
            else:
                line(g, P(-4.5, -4.5), P(4.5, 4.5), Ui.tint("failed"), 2)
                line(g, P(4.5, -4.5), P(-4.5, 4.5), Ui.tint("failed"), 2)
        g.restore()


def microphone(g: QPainter, ink: QColor) -> None:
    rounded(g, QRectF(-2.6, -8, 5.2, 9.5), 2.6, fill=ink)
    stroke_path(g, arc_path(P(0, -1.5), 5.2, 0, math.pi), ink, 1.6)  # the cup under it, through its lowest point
    line(g, P(0, 3.7), P(0, 7), ink, 1.6)
    line(g, P(-3, 7), P(3, 7), ink, 1.6)


def end_mark(g: QPainter, kind: str, missed: bool, o: QPointF) -> None:
    """The small sign before a line of the history: how that turn ended."""
    g.save()
    g.translate(o)
    if kind == "done":
        line(g, P(2.5, 8.6), P(5.1, 11.2), Ui.tint("done"), 1.7)
        line(g, P(5.1, 11.2), P(10.4, 5.4), Ui.tint("done"), 1.7)
    elif kind == "failed":
        line(g, P(3.4, 5.4), P(9.4, 11.4), Ui.tint("failed"), 1.7)
        line(g, P(9.4, 5.4), P(3.4, 11.4), Ui.tint("failed"), 1.7)
    elif kind == "needs_you":
        line(g, P(6.4, 4.6), P(6.4, 9.2), Ui.amber, 1.8)
        circle(g, P(6.4, 12.2), 1.1, fill=Ui.amber)
    elif kind == "progress":
        circle(g, P(6.4, 8.4), 3.1, stroke=Ui.tint("working"), width=1.5)
    elif kind == "aside":
        rounded(g, QRectF(2.2, 4.4, 8.6, 6.2), 2, stroke=alpha(WHITE, 0.7), width=1.3)
        line(g, P(4.6, 10.6), P(3.6, 12.8), alpha(WHITE, 0.7), 1.3)
    else:
        circle(g, P(6.4, 8.4), 1.6, fill=alpha(WHITE, 0.45))
    if missed:
        circle(g, P(12, 4), 1.8, fill=WHITE)
    g.restore()


def strip(g: QPainter, rect: QRectF, wave: Wave, tint: QColor) -> None:
    """The voice behind a line: thin bars of its loudness, the newest at the right, fading left."""
    t, count, gap = now(), 34, 4.2
    for i in range(count):
        x = rect.right() - 8 - i * gap
        if x < rect.left() + rect.width() * 0.35:
            break
        level = wave.at(t - Wave.lag - i * 0.05)
        h = max(2.0, level * (rect.height() - 10))
        rounded(g, QRectF(x - 1.2, rect.center().y() - h / 2, 2.4, h), 1.2, fill=alpha(tint, 0.55 * (1 - i / count)))
