#!/usr/bin/env python3
"""Star-of-the-plate: a melting-cheese burger, drawn procedurally.

One hero ingredient (the cheese melt over a seared patty), rendered with
pure stdlib: a tiny SDF rasterizer + a hand-written PNG encoder
(zlib/struct). Deterministic: seeded RNG only, no clock, no network.
Writes /output/entry.png (1024x1024).
"""
import math
import os
import random
import struct
import zlib

W = H = 1024
rng = random.Random(20261123)

# ---------------------------------------------------------------- canvas
buf = [[(0.0, 0.0, 0.0)] * W for _ in range(H)]


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


def blend(x, y, color, alpha):
    if alpha <= 0.0:
        return
    r, g, b = buf[y][x]
    buf[y][x] = (lerp(r, color[0], alpha), lerp(g, color[1], alpha), lerp(b, color[2], alpha))


def hash2(x, y):
    """Deterministic value noise in [0,1)."""
    n = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def smooth_noise(x, y, scale):
    """Bilinear-interpolated hash noise."""
    gx, gy = x / scale, y / scale
    ix, iy = int(math.floor(gx)), int(math.floor(gy))
    fx, fy = gx - ix, gy - iy
    sx = fx * fx * (3 - 2 * fx)
    sy = fy * fy * (3 - 2 * fy)
    v00, v10 = hash2(ix, iy), hash2(ix + 1, iy)
    v01, v11 = hash2(ix, iy + 1), hash2(ix + 1, iy + 1)
    return lerp(lerp(v00, v10, sx), lerp(v01, v11, sx), sy)


# ---------------------------------------------------------------- shapes
def ellipse(cx, cy, rx, ry, color_fn, soft=3.0):
    """Filled ellipse with a soft edge; color_fn(x, y, d) -> rgb, d in [0,1]."""
    x0, x1 = max(0, int(cx - rx - soft - 1)), min(W - 1, int(cx + rx + soft + 1))
    y0, y1 = max(0, int(cy - ry - soft - 1)), min(H - 1, int(cy + ry + soft + 1))
    edge = min(rx, ry) / soft
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            d = math.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
            a = clamp(0.5 + (1.0 - d) * edge)
            if a > 0.0:
                blend(x, y, color_fn(x, y, d), a)


def band(y_top_fn, y_bot_fn, x_lo, x_hi, color_fn, soft=3.0, x_fade=26.0):
    """Horizontal band whose top/bottom edges are functions of x."""
    for x in range(max(0, x_lo), min(W - 1, x_hi) + 1):
        yt, yb = y_top_fn(x), y_bot_fn(x)
        xa = clamp(min(x - x_lo, x_hi - x) / x_fade + 0.5)
        for y in range(max(0, int(yt - soft - 1)), min(H - 1, int(yb + soft + 1)) + 1):
            a = clamp(min(y - yt, yb - y) / soft + 0.5) * xa
            if a > 0.0:
                t = clamp((y - yt) / max(1.0, yb - yt))
                blend(x, y, color_fn(x, y, t), a)


def glow(cx, cy, rx, ry, color, strength):
    """Soft additive-ish highlight blob (gloss / steam)."""
    x0, x1 = max(0, int(cx - rx)), min(W - 1, int(cx + rx))
    y0, y1 = max(0, int(cy - ry)), min(H - 1, int(cy + ry))
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
            if d < 1.0:
                blend(x, y, color, strength * (1.0 - d) ** 1.6)


# ---------------------------------------------------------------- scene
CX = 512  # burger centre x

# background: warm dark radial gradient + vignette
for y in range(H):
    for x in range(W):
        d = math.sqrt(((x - CX) / 760) ** 2 + ((y - 430) / 760) ** 2)
        base = mix((0.30, 0.19, 0.12), (0.10, 0.06, 0.045), clamp(d))
        grain = 0.015 * (smooth_noise(x, y, 90) - 0.5)
        buf[y][x] = (base[0] + grain, base[1] + grain, base[2] + grain)

# table shadow + plate
glow(CX, 838, 430, 66, (0.02, 0.015, 0.01), 0.85)
ellipse(CX, 806, 452, 96, lambda x, y, d: mix((0.93, 0.91, 0.88), (0.72, 0.70, 0.68), d), soft=4)
ellipse(CX, 800, 388, 74, lambda x, y, d: mix((0.97, 0.96, 0.94), (0.86, 0.85, 0.83), d), soft=4)

# bottom bun
ellipse(CX, 742, 330, 66, lambda x, y, d: mix((0.96, 0.72, 0.38), (0.78, 0.50, 0.22), clamp(d * 0.9 + 0.15 * smooth_noise(x, y, 26))), soft=4)
ellipse(CX, 728, 322, 44, lambda x, y, d: mix((0.99, 0.82, 0.52), (0.93, 0.66, 0.34), d), soft=4)

# lettuce: wavy green band
def lettuce_top(x):
    return 700 + 13 * math.sin(x / 34.0) + 6 * math.sin(x / 11.0 + 1.7)


def lettuce_bot(x):
    return lettuce_top(x) + 30 + 8 * math.sin(x / 23.0 + 0.4)


band(lettuce_top, lettuce_bot, CX - 356, CX + 356,
     lambda x, y, t: mix((0.52, 0.80, 0.30), (0.24, 0.55, 0.16), clamp(t * 0.7 + 0.3 * smooth_noise(x, y, 18))), soft=3)

# tomato slice
band(lambda x: 664 + 4 * math.sin(x / 60.0), lambda x: 700 + 4 * math.sin(x / 60.0), CX - 318, CX + 318,
     lambda x, y, t: mix((0.95, 0.30, 0.18), (0.78, 0.16, 0.10), clamp(t * 0.6 + 0.4 * smooth_noise(x, y, 30))), soft=3)

# seared patty: dark, crusty, speckled
def patty_top(x):
    return 614 + 5 * math.sin(x / 47.0 + 0.8)


def patty_bot(x):
    return 674 + 5 * math.sin(x / 47.0 + 0.8)


def patty_color(x, y, t):
    n = smooth_noise(x, y, 9)
    char = smooth_noise(x, y, 3.2)
    c = mix((0.44, 0.26, 0.14), (0.22, 0.13, 0.07), clamp(0.35 + 0.45 * n + 0.35 * t))
    if char > 0.78:  # dark char flecks
        c = mix(c, (0.10, 0.06, 0.04), 0.7)
    return c


band(patty_top, patty_bot, CX - 336, CX + 336, patty_color, soft=3.5)

# THE HERO: melting cheese sheet with drips over the patty
DRIPS = [(CX - 300, 46, 26), (CX - 196, 88, 30), (CX - 84, 58, 24),
         (CX + 28, 104, 34), (CX + 142, 66, 26), (CX + 248, 92, 30), (CX + 322, 40, 22)]


def cheese_bot(x):
    y = 612.0
    for (dx, depth, width) in DRIPS:
        u = clamp((x - dx) / width, -1.0, 1.0)
        y += depth * (math.cos(u * math.pi / 2) ** 1.35)  # rounded hanging drops
    return y


def cheese_color(x, y, t):
    gloss = math.exp(-((y - 592) / 10.0) ** 2)  # bright melt line near the top
    c = mix((1.00, 0.72, 0.16), (0.96, 0.52, 0.06), clamp(t * 0.85))
    return mix(c, (1.00, 0.90, 0.50), 0.65 * gloss)


band(lambda x: 580 + 3 * math.sin(x / 55.0), cheese_bot, CX - 346, CX + 346, cheese_color, soft=3)
# wet shine streak along the cheese top edge
glow(CX - 60, 588, 300, 10, (1.0, 0.94, 0.62), 0.35)
# drip-tip highlights (wet shine on each hanging drop)
for (dx, depth, width) in DRIPS:
    tip_y = 612 + depth - 12
    glow(dx - width * 0.22, tip_y, width * 0.45, 9, (1.0, 0.92, 0.6), 0.5)

# top bun dome
def bun_color(x, y, d):
    t = clamp((y - 296) / 300)
    n = smooth_noise(x, y, 22)
    c = mix((0.99, 0.76, 0.42), (0.82, 0.52, 0.22), clamp(t * 0.75 + 0.25 * n))
    # baked darker rim near the bottom edge of the dome
    rim = clamp((y - 545) / 40)
    return mix(c, (0.70, 0.42, 0.18), 0.45 * rim)


def dome(cx, cy, rx, ry, skirt_bot, color_fn, soft=3.5):
    """Bun dome: ellipse union a rounded skirt so the sides meet the cheese."""
    r = 46.0  # skirt corner radius
    half_w, half_h = rx - 6, (skirt_bot - cy) / 2
    mid_y = cy + half_h
    for y in range(max(0, int(cy - ry - soft - 1)), min(H - 1, int(skirt_bot + soft + 1)) + 1):
        for x in range(max(0, int(cx - rx - soft - 1)), min(W - 1, int(cx + rx + soft + 1)) + 1):
            d_ell = (math.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2) - 1.0) * min(rx, ry)
            qx = abs(x - cx) - (half_w - r)
            qy = abs(y - mid_y) - (half_h - r)
            d_box = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r
            a = clamp(0.5 - min(d_ell, d_box) / soft)
            if a > 0.0:
                blend(x, y, color_fn(x, y, 0.0), a)


dome(CX, 452, 342, 168, 586, bun_color, soft=3.5)

# sesame seeds on the dome (seeded, fixed)
for _ in range(38):
    ang = rng.uniform(0, 2 * math.pi)
    rad = math.sqrt(rng.uniform(0.02, 0.84))
    sx = CX + 342 * rad * math.cos(ang)
    sy = 452 + 168 * rad * math.sin(ang)
    if sy > 552:
        continue
    srx, sry = rng.uniform(10, 14), rng.uniform(5.0, 6.4)
    ellipse(sx, sy, srx, sry, lambda x, y, d: mix((1.0, 0.92, 0.74), (0.90, 0.77, 0.54), d), soft=1.6)
    glow(sx - 3, sy - 2, srx * 0.5, sry * 0.6, (1.0, 0.98, 0.9), 0.35)

# bun gloss: broad soft highlight, upper left
glow(CX - 130, 372, 210, 84, (1.0, 0.90, 0.66), 0.38)
glow(CX - 170, 352, 90, 34, (1.0, 0.97, 0.86), 0.45)

# steam wisps rising off the melt
for (base_x, phase, width, strength) in [(CX - 150, 0.0, 34, 0.30), (CX + 10, 1.9, 40, 0.36), (CX + 160, 3.8, 30, 0.26)]:
    for y in range(120, 300):
        t = (300 - y) / 180.0
        sx = base_x + 26 * math.sin(y / 42.0 + phase) * (0.4 + t)
        a = strength * math.sin(math.pi * clamp(t)) ** 1.4
        glow(sx, y, width * (0.6 + 0.7 * t), 14, (1.0, 0.99, 0.97), a * 0.16)

# a few glossy juice beads on the cheese
for (jx, jy, jr) in [(CX - 240, 598, 7), (CX + 90, 596, 6), (CX + 210, 600, 8)]:
    glow(jx, jy, jr, jr * 0.8, (1.0, 0.85, 0.4), 0.55)
    glow(jx - 2, jy - 2, jr * 0.4, jr * 0.3, (1.0, 0.98, 0.9), 0.7)

# ---------------------------------------------------------------- PNG out
def write_png(path, pixels):
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter: none
        for (r, g, b) in row:
            raw += bytes((int(clamp(r) * 255 + 0.5), int(clamp(g) * 255 + 0.5), int(clamp(b) * 255 + 0.5)))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


if __name__ == "__main__":
    out = "/output/entry.png" if os.path.isdir("/output") else "entry.png"
    if out.startswith("/output"):
        os.makedirs("/output", exist_ok=True)
    size = write_png(out, buf)
    print(f"wrote {out} ({size} bytes)")
