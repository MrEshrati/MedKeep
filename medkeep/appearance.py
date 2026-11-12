from functools import lru_cache
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
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")
            + _chunk(b"IDAT", zlib.compress(bytes(pixels))) + _chunk(b"IEND", b""))


def rounded_image(master, fill, *, radius=8, border=None, center=(4, 4)):
    return tk.PhotoImage(master=master, data=_rounded_png(fill, radius, border, center), format="png")


def _rounded_png(fill, radius, border, center):
    center_width, center_height = center
    width, height = radius * 2 + center_width, radius * 2 + center_height
    red, green, blue = _rgb(fill)
    br, bg, bb = _rgb(border or fill)
    fill_pixel = bytes((red, green, blue, 255))
    border_pixel = bytes((br, bg, bb, 255))
    outer_radius_sq, inner_radius_sq = radius ** 2, (radius - 1) ** 2
    top_rows = []
    for y in range(radius):
        corner = []
        for x in range(radius):
            count = sr = sg = sb = 0
            for sy in range(4):
                for sx in range(4):
                    dx, dy = radius - x - (sx + .5) / 4, radius - y - (sy + .5) / 4
                    distance_sq = dx * dx + dy * dy
                    if distance_sq > outer_radius_sq:
                        continue
                    count += 1
                    if distance_sq > inner_radius_sq:
                        sr, sg, sb = sr + br, sg + bg, sb + bb
                    else:
                        sr, sg, sb = sr + red, sg + green, sb + blue
            corner.append(bytes((sr // count, sg // count, sb // count, round(count * 255 / 16)))
                          if count else b"\0\0\0\0")
        edge = border_pixel if y == 0 else fill_pixel
        top_rows.append(b"\0" + b"".join(corner) + edge * center_width + b"".join(reversed(corner)))
    middle_row = b"\0" + border_pixel + fill_pixel * (width - 2) + border_pixel
    return _png(width, height, b"".join(top_rows) + middle_row * center_height + b"".join(reversed(top_rows)))


_rounded_png = lru_cache(maxsize=32)(_rounded_png)


def _distance(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    divisor = dx * dx + dy * dy
    t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / divisor)) if divisor else 0
    return (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2


def icon_image(master, name, color=SECONDARY_TEXT, size=16):
    red, green, blue = _rgb(color)
    mask = _icon_mask(name, size)
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for alpha in mask[y * size:(y + 1) * size]:
            raw.extend((red, green, blue, alpha))
    return tk.PhotoImage(master=master, data=_png(size, size, raw), format="png")


def _icon_mask(name, size):
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
    stroke = .8
    segments = tuple((ax, ay, bx, by, min(ax, bx) - stroke, max(ax, bx) + stroke,
                      min(ay, by) - stroke, max(ay, by) + stroke)
                     for path in paths for (ax, ay), (bx, by) in zip(path, path[1:]))
    mask = bytearray()
    for y in range(size):
        for x in range(size):
            count = 0
            for sy in range(3):
                for sx in range(3):
                    px, py = (x + (sx + .5) / 3) * 24 / size, (y + (sy + .5) / 3) * 24 / size
                    for ax, ay, bx, by, left, right, top, bottom in segments:
                        if (left <= px <= right and top <= py <= bottom
                                and _distance(px, py, ax, ay, bx, by) <= stroke ** 2):
                            count += 1
                            break
            mask.append(round(count * 255 / 9))
    return bytes(mask)


_icon_mask = lru_cache(maxsize=32)(_icon_mask)


class RoundedPanel(tk.Frame):
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
