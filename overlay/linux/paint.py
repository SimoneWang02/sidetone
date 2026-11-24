"""What the bar, the details and the bubble draw (overlay/mac/Paint.swift, in QPainter). The
details are a column of blocks (a request, a banner, the card of figures, one row per session,
the history), each with its height in units, laid out from the top."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter

import draw
from draw import P, Ui, Words, alpha, end_mark, font, line, mono, now, rounded

WHITE = draw.WHITE
CAP_SIGNS = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Super", "plus": "+", "minus": "-",
             "space": "Space", "backspace": "⌫", "up": "↑", "down": "↓", "left": "←", "right": "→"}


def cap_label(key: str) -> str:
    k = key.strip()
    return CAP_SIGNS.get(k.lower(), k.upper() if len(k) == 1 else k)


class Block:
    def __init__(self, kind: str, height: float, paint, row=None):
        self.kind, self.height, self.paint, self.row = kind, height, paint, row


class Painting:
    """Mixed into the Overlay: it has the state, this draws it."""

    inner = 12.0

    # --- the bar ------------------------------------------------------------------------------

    def paint_bar(self, g: QPainter, box: QRectF) -> None:
        light, pad = self.light, self.pad
        if not self.order:
            draw.circle(g, P(pad + light / 2, pad + light / 2), 12, fill=alpha(Ui.idle, 0.06), stroke=alpha(Ui.idle, 0.35), width=1.5)
        for i, row in enumerate(self.order):
            along = pad + light * (i + 0.5)
            c = P(along, pad + light / 2) if self.island else P(pad + light / 2, along)
            lit = 0.16 if row.name == self.hot_name else 0.10 if row.focus else 0
            if lit:
                rounded(g, QRectF(c.x() - 20, c.y() - 20, 40, 40), 9, fill=alpha(WHITE, lit), stroke=alpha(WHITE, lit + 0.12), width=1)
            row.orb.hot = 1.0 if row.name == self.hot_name else 0.0
            row.orb.draw(g, c)
            if self.island:
                rounded(g, QRectF(c.x() - 8, pad + light + 1, 16, 3), 1.5, fill=draw.color(row.color, "#FFFFFF"))

    # --- the details --------------------------------------------------------------------------

    def build_panel(self) -> list:
        blocks = []
        wide = self.panel_width - 2 * self.inner
        if self.request is not None:
            blocks += [self.request_block(self.request, wide), self.divider()]
        if self.banner is not None and self.has_banner:
            blocks.append(self.banner_block(self.banner, wide))
        asked = not self.dragged and (self.listed or self.hover or self.keys_open or self.peek)
        if self.muted and self.muted_line and asked and not self.has_banner:
            key = self.wanted_keys.get("mute", "")
            blocks.append(self.voice_block(True, "Voice is muted", key + " turns it on" if key else ""))
        focus_only = self.mode == "focus"
        chosen = self.chosen()
        show_history = self.listed and (self.peek or (focus_only and self.focus_history)) and bool(self.history)
        if asked:
            card = self.card_block(chosen, wide, show_history and not self.history_all)
            if card is not None:
                blocks += [card, self.divider()]
        for row in self.order:
            if not focus_only or row is chosen:
                blocks.append(self.row_block(row, wide, focus_only))
        if not self.order:
            blocks.append(Block("empty", 34, lambda g, r: Words("No sessions yet", font(12.5), Ui.dim).draw(g, QRectF(self.inner, r.y() + 9, wide, 18))))
        if show_history and self.history_all:
            blocks.append(self.divider())
            blocks += [self.history_block(h, wide, True) for h in self.history[:8]]
        if blocks and blocks[-1].kind == "divider":
            blocks.pop()
        return blocks

    def paint_panel(self, g: QPainter, box: QRectF) -> None:
        top = 6.0
        for b in self.panel_blocks:
            b.paint(g, QRectF(0, top, self.panel_width, b.height))
            top += b.height

    def divider(self) -> Block:
        return Block("divider", 9, lambda g, r: line(g, P(self.inner - 2, r.center().y()), P(r.right() - self.inner + 2, r.center().y()), alpha(WHITE, 0.12), 1))

    def heading(self, row) -> Words:
        w = Words(row.name, font(13, "semibold"), draw.color(row.color, "#FFFFFF"))
        if row.title:
            w.add("   " + row.title, font(13), WHITE)
        return w

    def row_block(self, row, wide: float, whole: bool) -> Block:
        text, ink, bold = row.second_line()
        lines = 10 if whole else max(1, Ui.row_lines) if (row.saying or row.talk_kind is not None) else 1
        second = Words(text, font(12, "semibold" if bold else "regular"), ink)
        meta_shown = not row.saying and row.talk_kind is None and bool(row.meta)
        meta = Words(row.meta, font(11.5), Ui.faint)
        meta_width = meta.width() + 8 if meta_shown else 0
        text_height = second.height(wide - meta_width, lines) if text else 0
        height = max(self.light, 6 + 17 + text_height + 6)

        def paint(g, r):
            back = r.adjusted(6, 1, -6, -1)
            if row.lit > 0.005:
                rounded(g, back, 7, fill=alpha(WHITE, row.lit))
            if row.speaking or row.orb.listening is not None:
                draw.strip(g, back, row.orb.listening or row.orb.wave, draw.mix(Ui.mic, WHITE, 0.3) if row.orb.listening else Ui.tint(row.state))
            x, name_width = r.x() + self.inner, wide
            if not Ui.sign_in_light and row.talk_kind:
                draw.Badge.draw(g, row.talk_kind, P(x + wide - 10, r.y() + 14), now(), now() - row.orb.sign_since, False)
                name_width -= 24
            self.heading(row).draw(g, QRectF(x, r.y() + 5, name_width, 18))
            if text:
                second.draw(g, QRectF(x, r.y() + 23, wide - meta_width, text_height + 2), lines)
            if meta_shown:
                meta.draw(g, QRectF(x + wide - meta_width + 8, r.y() + 24, meta_width - 8, 16), align="right")
        return Block("row", height, paint, row)

    # --- the card of figures ------------------------------------------------------------------

    def card_block(self, row, wide: float, with_history: bool) -> Block | None:
        if row is None:
            return None
        tiles = [t for t in row.details if len(t) >= 2]
        if not tiles and not self.usage:
            return None
        lines = [h for h in self.history if h.get("name") == row.name][:4] if with_history else []
        as_line = self.details_style == "line"
        height = 10 + 20 + ((20 if as_line else 40) if tiles else 0)
        if self.usage:
            height += 8 + (len(self.usage) if self.usage_rows else 1) * 18
        heights = [self.history_height(h, wide - 20) for h in lines]
        if lines:
            height += 12 + sum(heights)
        height += 12

        def paint(g, r):
            card = QRectF(r.x() + self.inner - 3, r.y() + 2, wide + 6, height)
            rounded(g, card, 9, fill=alpha(WHITE, 0.06), stroke=alpha(WHITE, 0.08), width=1)
            x, inside, y = card.x() + 11, card.width() - 22, card.y() + 8
            self.heading(row).draw(g, QRectF(x, y, inside, 18))
            y += 20
            if tiles and as_line:
                words = Words()
                for t in tiles:
                    if str(t[1]):
                        words.add(f"{t[0]} ", font(11.5), Ui.dim).add(f"{t[1]}    ", font(11.5, "semibold"), WHITE)
                words.draw(g, QRectF(x, y + 1, inside, 16))
                y += 20
            elif tiles:
                each = inside / max(4, len(tiles))
                for i, t in enumerate(tiles):
                    tx, name, figure = x + i * each, str(t[0]), str(t[1])
                    warn = len(t) > 3 and t[3] == "warn"
                    Words(name, font(11), Ui.dim).draw(g, QRectF(tx, y, each - 4, 15))
                    big = Words()
                    if "/" in figure:
                        head, _, tail = figure.partition("/")
                        big.add(head, font(16, "bold"), Ui.context_full if warn else WHITE).add("/" + tail, font(16), Ui.dim)
                    else:
                        big.add(figure or "–", font(16, "bold"), Ui.faint if not figure else Ui.context_full if warn else WHITE)
                    big.draw(g, QRectF(tx, y + 15, each - 4, 22))
                y += 40
            if self.usage:
                y += 8
                if self.usage_rows:
                    for u in self.usage:
                        self.usage_bar(g, u, QRectF(x, y, inside, 18))
                        y += 18
                else:
                    half = inside / len(self.usage)
                    for i, u in enumerate(self.usage):
                        self.usage_bar(g, u, QRectF(x + i * half, y, half - 10, 18))
                    y += 18
            if lines:
                y += 4
                line(g, P(x, y + 2), P(x + inside, y + 2), alpha(WHITE, 0.12), 1)
                y += 8
                for h, hh in zip(lines, heights):
                    self.paint_history(g, h, QRectF(x - 2, y, inside + 2, hh), False)
                    y += hh
        return Block("card", height + 6, paint, row)

    def usage_bar(self, g, u, r: QRectF) -> None:
        if len(u) < 2:
            return
        share = float(u[1] or 0) / 100
        warn = len(u) > 2 and u[2] == "warn"
        Words(str(u[0]), font(11, "semibold"), Ui.dim).draw(g, QRectF(r.x(), r.y() + 1, 34, 15))
        track = QRectF(r.x() + 26, r.center().y() - 1.5, r.width() - 26 - 42, 3)
        rounded(g, track, 1.5, fill=alpha(WHITE, 0.12))
        rounded(g, QRectF(track.x(), track.y(), track.width() * max(0.0, min(1.0, share)), 3), 1.5,
                fill=Ui.context_full if warn else alpha(WHITE, 0.9))
        Words(f"{share * 100:.0f}%", font(11.5, "semibold"), Ui.context_full if warn else WHITE).draw(
            g, QRectF(r.right() - 40, r.y() + 1, 40, 16), align="right")

    # --- history ------------------------------------------------------------------------------

    def history_height(self, h: dict, wide: float) -> float:
        return max(20.0, Words(str(h.get("text", "")), font(12), WHITE).height(wide - 60, 2) + 5)

    def history_block(self, h: dict, wide: float, named: bool) -> Block:
        height = self.history_height(h, wide)
        return Block("history", height, lambda g, r: self.paint_history(g, h, QRectF(r.x() + self.inner, r.y(), wide, height), named))

    def paint_history(self, g, h: dict, r: QRectF, named: bool) -> None:
        end_mark(g, str(h.get("kind", "")), bool(h.get("missed")), P(r.x(), r.y()))
        text = Words()
        if named:
            text.add(str(h.get("name", "")) + "  ", font(12, "semibold"), draw.color(str(h.get("color", "")), "#FFFFFF"))
        text.add(str(h.get("text", "")), font(12), alpha(WHITE, 0.88))
        right = "  ".join(x for x in (str(h.get("ago") or ""), str(h.get("tokens") or "")) if x)
        lines = 1 if named else 2
        text.draw(g, QRectF(r.x() + 19, r.y() + 1, r.width() - 19 - 50, r.height()), lines)
        if right:
            Words(right, font(11.5), Ui.faint).draw(g, QRectF(r.right() - 50, r.y() + 2, 50, 16), align="right")

    # --- a request to answer --------------------------------------------------------------------

    def request_block(self, m: dict, wide: float) -> Block:
        question = str(m.get("question") or "")
        options = [str(o) for o in m.get("options") or []]
        ticked = [bool(t) for t in m.get("ticked") or []]
        title = Words("▲  ", font(11), Ui.amber).add(str(m.get("name", "")) + "  ", font(13, "semibold"), draw.color(str(m.get("color", "")), "#FFFFFF"))
        if m.get("place"):
            title.add("Question " + str(m["place"]), font(13), Ui.dim)
        elif not question:
            title.add(str(m.get("text", "")), font(13), WHITE)
        title_height = 18.0
        asked = Words(question, font(13), WHITE)
        question_height = asked.height(wide, 3) + 4 if question else 0
        option_heights = [Words(o, font(12.5), WHITE).height(wide - 20, 3) + 3 for o in options]
        detail = "" if question else str(m.get("detail") or "")
        detail_words = Words(detail, mono(12), alpha(WHITE, 0.9))
        detail_height = detail_words.height(wide, 3) + 4 if detail else 0
        hints = [[str(x) for x in h] for h in m.get("hints") or [] if isinstance(h, list)]
        more = int(m.get("more") or 0)
        height = 6 + title_height + question_height + sum(option_heights) + detail_height + (28 if hints else 0) + (18 if more else 0) + 4

        def paint(g, r):
            x, y = r.x() + self.inner, r.y() + 6
            title.draw(g, QRectF(x, y, wide, title_height))
            y += title_height
            if question:
                asked.draw(g, QRectF(x, y + 2, wide, question_height), 3)
                y += question_height
            for i, option in enumerate(options):
                if i < len(ticked):
                    box = QRectF(x + 1, y + 3, 11, 11)
                    rounded(g, box, 2.5, fill=Ui.amber if ticked[i] else None, stroke=None if ticked[i] else Ui.amber, width=1.3)
                    if ticked[i]:
                        line(g, P(box.x() + 2.6, box.center().y()), P(box.x() + 4.6, box.bottom() - 2.6), draw.QColor(0, 0, 0), 1.5)
                        line(g, P(box.x() + 4.6, box.bottom() - 2.6), P(box.right() - 2.2, box.y() + 2.6), draw.QColor(0, 0, 0), 1.5)
                elif self.choice_caps:
                    self.cap(g, str(i + 1), x, y)
                else:
                    Words(str(i + 1), font(12.5, "semibold"), Ui.amber).draw(g, QRectF(x + 1, y, 14, 18))
                Words(option, font(12.5), WHITE).draw(g, QRectF(x + 20, y, wide - 20, option_heights[i]), 3)
                y += option_heights[i]
            if detail:
                detail_words.draw(g, QRectF(x, y + 2, wide, detail_height), 3)
                y += detail_height
            if hints:
                self.paint_hints(g, hints, x, y + 5)
                y += 28
            if more:
                Words(f"{more} more waiting", font(11.5), Ui.dim).draw(g, QRectF(x, y, wide, 16))
        return Block("request", height, paint)

    def paint_hints(self, g, hints: list, x: float, y: float) -> None:
        split = []
        for h in hints:
            parts = [p for p in (h[0] if h else "").split("+") if p]
            split.append((parts[:-1], parts[-1] if parts else ""))
        shared = split[0][0] if split and all(s[0] == split[0][0] for s in split) else []
        for key in shared:
            x = self.cap(g, key, x, y) + 4
        if shared:
            Words("+", font(12, "semibold"), Ui.amber).draw(g, QRectF(x, y + 1, 10, 16))
            x += 13
        for h, (mods, last) in zip(hints, split):
            if not shared:
                for key in mods:
                    x = self.cap(g, key, x, y) + 4
            until = h[2] if len(h) > 2 else ""
            if last.isdigit() and until.isdigit() and int(until) > int(last):
                for n in range(int(last), int(until) + 1):
                    x = self.cap(g, str(n), x, y) + 4
            else:
                x = self.cap(g, last, x, y) + 4
            label = Words(h[1] if len(h) > 1 else "", font(12.5), Ui.amber)
            label.draw(g, QRectF(x + 2, y + 1, 120, 17))
            x += label.width() + 14

    def cap(self, g, key: str, x: float, y: float) -> float:
        words = Words(cap_label(key), font(11, "semibold"), WHITE)
        w = max(20.0, words.width() + 12)
        box = QRectF(x, y, w, 19)
        rounded(g, box, 4, fill=alpha(Ui.amber, 0.16), stroke=alpha(Ui.amber, 0.75), width=1)
        words.draw(g, QRectF(box.x(), box.y() + 2.5, w, 15), align="center")
        return box.right()

    # --- a banner -----------------------------------------------------------------------------

    def banner_block(self, m: dict, wide: float) -> Block:
        icon = str(m.get("icon") or "")
        if icon in ("muted", "voice"):
            return self.voice_block(icon == "muted", str(m.get("text", "")), str(m.get("hint") or ""))

        def paint(g, r):
            x = r.x() + self.inner
            sign = {"clear": "✕", "end": "⏻"}.get(icon, "●")
            Words(sign, font(14, "semibold"), Ui.working).draw(g, QRectF(x, r.y() + 8, 18, 18))
            words = Words(str(m.get("text", "")), font(13, "regular" if icon in ("clear", "end") else "semibold"), Ui.dim if icon else WHITE)
            if m.get("hint"):
                words.add("   " + str(m["hint"]), font(11.5), Ui.faint)
            words.draw(g, QRectF(x + 24, r.y() + 8, wide - 24, 18))
        return Block("banner", 34, paint)

    def voice_block(self, muted: bool, text: str, hint: str) -> Block:
        def paint(g, r):
            x = r.x() + self.inner
            speaker(g, P(x + 8, r.y() + 16), muted)
            words = Words(text, font(12.5), Ui.dim)
            if hint:
                words.add("   " + hint, font(11.5), Ui.faint)
            words.draw(g, QRectF(x + 26, r.y() + 8, self.panel_width - 2 * self.inner - 26, 17))
        return Block("voice", 32, paint)

    # --- the bubble ---------------------------------------------------------------------------

    def bubble_height(self, row) -> float:
        text, _, bold = row.second_line()
        words = Words(text, font(12.5, "semibold" if bold else "regular"), WHITE)
        return 8 + 18 + (words.height(self.panel_width - 2 * self.inner, 3) if text else 0) + 10

    def paint_bubble(self, g: QPainter, r: QRectF) -> None:
        row = self.bubble_row
        if row is None:
            return
        if row.speaking or row.orb.listening is not None:
            draw.strip(g, r.adjusted(4, 4, -4, -4), row.orb.listening or row.orb.wave,
                       draw.mix(Ui.mic, WHITE, 0.3) if row.orb.listening else Ui.tint(row.state))
        wide = r.width() - 2 * self.inner
        self.heading(row).draw(g, QRectF(self.inner, 8, wide, 18))
        text, ink, bold = row.second_line()
        Words(text, font(12.5, "semibold" if bold else "regular"), WHITE if row.saying and row.talk_kind is None else ink).draw(
            g, QRectF(self.inner, 26, wide, r.height() - 30), 3)


def speaker(g: QPainter, c, muted: bool) -> None:
    """A small speaker, struck out while the voice is off."""
    from PySide6.QtGui import QPainterPath
    ink = Ui.dim if muted else WHITE
    body = QPainterPath()
    body.moveTo(c.x() - 7, c.y() - 3); body.lineTo(c.x() - 4, c.y() - 3); body.lineTo(c.x() + 1, c.y() - 7)
    body.lineTo(c.x() + 1, c.y() + 7); body.lineTo(c.x() - 4, c.y() + 3); body.lineTo(c.x() - 7, c.y() + 3); body.closeSubpath()
    g.setPen(Qt.PenStyle.NoPen)
    g.setBrush(ink)
    g.drawPath(body)
    if muted:
        line(g, P(c.x() + 4, c.y() - 4), P(c.x() + 10, c.y() + 4), ink, 1.6)
        line(g, P(c.x() + 10, c.y() - 4), P(c.x() + 4, c.y() + 4), ink, 1.6)
    else:
        draw.stroke_path(g, draw.arc_path(c, 6, -0.7, 0.7), ink, 1.5)
        draw.stroke_path(g, draw.arc_path(c, 9.5, -0.75, 0.75), ink, 1.5)
