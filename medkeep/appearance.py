"""The approved dark Clinical palette and small, dependency-free UI assets.

Raw PNG buffers are presentation assets only. Record collections, the request
queue, the chain and the hash schedule remain in their hand-written containers.
"""

from __future__ import annotations

import math
import tkinter as tk
import zlib

BACKGROUND = "#172323"
SURFACE = "#202f30"
TEXT = "#e3eeec"
SECONDARY_TEXT = "#a9bcb8"
BORDER = "#3a4d49"
ACCENT = "#75cbb4"
ON_ACCENT = "#102a25"
TINT = "#2e4540"
DANGER = "#ffa6b1"


def _rgb(color):
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _chunk(kind, payload):
    return (len(payload).to_bytes(4, "big") + kind + payload
            + (zlib.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(4, "big"))


def _png(width, height, pixels):
    # PNG's CRC is a file-format checksum, unrelated to the project's SHA-256.
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")
            + _chunk(b"IDAT", zlib.compress(bytes(pixels))) + _chunk(b"IEND", b""))


def _inside(x, y, width, height, radius):
    if x < 0 or y < 0 or x >= width or y >= height:
        return False
    cx = min(max(x, radius), width - radius)
    cy = min(max(y, radius), height - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def rounded_image(master, fill, *, radius=8, border=None):
    """Antialiased nine-slice skin, generated with Python and Tk only."""
    width = height = radius * 2 + 4
    red, green, blue = _rgb(fill)
    br, bg, bb = _rgb(border or fill)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            count = sr = sg = sb = 0
            for sy in range(4):
                for sx in range(4):
                    px, py = x + (sx + .5) / 4, y + (sy + .5) / 4
                    if not _inside(px, py, width, height, radius):
                        continue
                    count += 1
                    if border and not _inside(px - 1, py - 1, width - 2, height - 2, radius - 1):
                        sr, sg, sb = sr + br, sg + bg, sb + bb
                    else:
                        sr, sg, sb = sr + red, sg + green, sb + blue
            raw.extend((sr // count if count else 0, sg // count if count else 0,
                        sb // count if count else 0, round(count * 255 / 16)))
    return tk.PhotoImage(master=master, data=_png(width, height, raw), format="png")


def _distance(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    divisor = dx * dx + dy * dy
    t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / divisor)) if divisor else 0
    return (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2


def icon_image(master, name, color=SECONDARY_TEXT, size=16):
    """Small outline icons matching the preview's document/shield/list/history."""
    if name == "create":
        paths = (((8, 3), (15, 3), (20, 8), (20, 21), (8, 21), (8, 17)),
                 ((15, 3), (15, 8), (20, 8)), ((3, 12), (11, 12)), ((7, 8), (7, 16)))
    elif name == "approval":
        paths = (((12, 3), (20, 7), (19, 14), (16, 19), (12, 22), (8, 19), (5, 14), (4, 7), (12, 3)),
                 ((8, 12), (11, 15), (16, 10)))
    elif name == "queue":
        paths = (((10, 5), (21, 5)), ((10, 12), (21, 12)), ((10, 19), (21, 19)),
                 ((3, 3), (4, 2), (4, 7)), ((2, 10), (5, 10), (5, 12), (2, 14), (5, 14)),
                 ((2, 17), (5, 17), (3, 19), (5, 19), (5, 21), (2, 21)))
    elif name == "history":
        circle = tuple((12 + 8 * math.cos(math.radians(a)), 12 + 8 * math.sin(math.radians(a)))
                       for a in range(210, 541, 15))
        paths = (circle, ((3, 3), (3, 9), (9, 9)), ((12, 7), (12, 12), (16, 14)))
    else:
        paths = (((9, 4), (6, 4), (6, 21), (19, 21), (19, 4), (16, 4)),
                 ((9, 2), (15, 2), (15, 6), (9, 6), (9, 2)),
                 ((9, 13), (16, 13)), ((12.5, 9.5), (12.5, 16.5)))
    red, green, blue = _rgb(color)
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            count = 0
            for sy in range(3):
                for sx in range(3):
                    px, py = (x + (sx + .5) / 3) * 24 / size, (y + (sy + .5) / 3) * 24 / size
                    hit = False
                    for path in paths:
                        for index in range(len(path) - 1):
                            ax, ay = path[index]
                            bx, by = path[index + 1]
                            if _distance(px, py, ax, ay, bx, by) <= .8 ** 2:
                                hit = True
                                break
                        if hit:
                            break
                    count += hit
            raw.extend((red, green, blue, round(count * 255 / 9)))
    return tk.PhotoImage(master=master, data=_png(size, size, raw), format="png")


class RoundedPanel(tk.Frame):
    """A normal Tk frame with an antialiased rounded background behind children."""

    def __init__(self, parent, *, bg=SURFACE, padding=22, radius=12, border=BORDER):
        scale = max(1.0, parent.winfo_fpixels("1i") / 96)
        px, py = padding if isinstance(padding, tuple) else (padding, padding)
        outer = parent["bg"]
        super().__init__(parent, bg=outer, padx=round(px * scale), pady=round(py * scale), borderwidth=0)
        self.surface = bg
        self._drawn_size = None
        self._radius = max(2, round(radius * scale))
        self._border = border
        self._backdrop = tk.Canvas(self, bg=outer, borderwidth=0, highlightthickness=0)
        # The backdrop covers the frame's padding as well as its content.
        # The default 'inside' mode would inset it and leave square, bare gaps.
        self._backdrop.place(x=0, y=0, relwidth=1, relheight=1, bordermode="outside")
        source = rounded_image(self, bg, radius=self._radius, border=border)
        self._corners = ()
        last = source.width() - self._radius
        for x, y in ((0, 0), (last, 0), (0, last), (last, last)):
            corner = tk.PhotoImage(master=self, width=self._radius, height=self._radius)
            corner.tk.call(corner, "copy", source, "-from", x, y, x + self._radius, y + self._radius)
            self._corners += (corner,)
        self.bind("<Configure>", self._draw, add="+")

    def __getitem__(self, key):
        if key in ("bg", "background"):
            return self.surface
        return super().__getitem__(key)

    def _draw(self, event):
        width, height, radius = event.width, event.height, self._radius
        if self._drawn_size == (width, height):
            return
        self._drawn_size = (width, height)
        canvas = self._backdrop
        canvas.delete("all")
        canvas.create_rectangle(radius, 0, width - radius, height, fill=self.surface, outline="")
        canvas.create_rectangle(0, radius, width, height - radius, fill=self.surface, outline="")
        if self._border:
            canvas.create_line(radius, 0, width - radius, 0, fill=self._border)
            canvas.create_line(radius, height - 1, width - radius, height - 1, fill=self._border)
            canvas.create_line(0, radius, 0, height - radius, fill=self._border)
            canvas.create_line(width - 1, radius, width - 1, height - radius, fill=self._border)
        for image, x, y in zip(self._corners, (0, width - radius, 0, width - radius),
                               (0, 0, height - radius, height - radius)):
            canvas.create_image(x, y, image=image, anchor="nw")
