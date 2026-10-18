"""
Oil pastel painting animation — run:

    python paint.py
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pygame
from PIL import Image

BASE = Path(__file__).resolve().parent
WINDOW_MAX_H = 480
FPS = 60
BATCH = 55


def find_image() -> Path:
    preferred = BASE / "images.jfif"
    if preferred.exists():
        return preferred
    for ext in (".jfif", ".jpg", ".jpeg", ".png", ".webp"):
        hits = sorted(BASE.glob(f"*{ext}"))
        if hits:
            return hits[0]
    return preferred


def clamp(v, a, b):
    return max(a, min(b, v))


def luminance(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def load_image():
    path = find_image()
    if not path.exists():
        print("Missing images.jfif next to paint.py")
        sys.exit(1)
    print(f"Using image: {path.name}", flush=True)
    img = Image.open(path).convert("RGB")
    scale = min(1.0, WINDOW_MAX_H / img.height)
    w = max(1, int(round(img.width * scale)))
    h = max(1, int(round(img.height * scale)))
    if (w, h) != img.size:
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    return img, w, h


def edge_maps(img: Image.Image):
    w, h = img.size
    pix = img.load()
    lum = [[luminance(*pix[x, y][:3]) for x in range(w)] for y in range(h)]
    ang = [[0.0] * w for _ in range(h)]
    mag = [[0.0] * w for _ in range(h)]
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            gx = (
                -lum[y - 1][x - 1]
                + lum[y - 1][x + 1]
                - 2 * lum[y][x - 1]
                + 2 * lum[y][x + 1]
                - lum[y + 1][x - 1]
                + lum[y + 1][x + 1]
            )
            gy = (
                -lum[y - 1][x - 1]
                - 2 * lum[y - 1][x]
                - lum[y - 1][x + 1]
                + lum[y + 1][x - 1]
                + 2 * lum[y + 1][x]
                + lum[y + 1][x + 1]
            )
            mag[y][x] = math.hypot(gx, gy)
            ang[y][x] = math.atan2(gy, gx) + math.pi / 2
    return ang, mag, w, h


def build_strokes(ang, mag, w, h):
    """One continuous top→bottom pass of pastel dabs."""
    strokes = []
    step = 2.8  # dense enough to match the image

    y = 0.0
    while y < h:
        x = 0.0
        wander = random.uniform(-0.6, 0.6)
        while x < w:
            jx = x + random.uniform(-0.9, 0.9)
            jy = y + wander + random.uniform(-0.9, 0.9)
            ix = int(clamp(jx, 0, w - 1))
            iy = int(clamp(jy, 0, h - 1))
            a = ang[iy][ix] + random.uniform(-0.35, 0.35)
            m = mag[iy][ix]

            if m > 40:
                length = random.uniform(7, 13)
                width = random.uniform(3.0, 5.5)
            else:
                length = random.uniform(10, 18)
                width = random.uniform(4.5, 8.0)

            strokes.append((jx, jy, a, length, width))
            x += step
        y += step

    return strokes


_brush_cache: dict[tuple, pygame.Surface] = {}


def make_brush(length: float, width: float) -> pygame.Surface:
    key = (round(length, 1), round(width, 1))
    if key in _brush_cache:
        return _brush_cache[key]

    lw = max(4, int(math.ceil(length + 4)))
    ww = max(4, int(math.ceil(width * 2 + 4)))
    brush = pygame.Surface((lw, ww), pygame.SRCALPHA)
    cx, cy = lw / 2, ww / 2
    for i in range(5, 0, -1):
        t = i / 5
        alpha = int(255 * (t ** 1.35))
        rx = max(1, int(length * 0.5 * t))
        ry = max(1, int(width * t))
        pygame.draw.ellipse(brush, (255, 255, 255, alpha), (cx - rx, cy - ry, rx * 2, ry * 2))
    _brush_cache[key] = brush
    return brush


def stamp_reveal(canvas: pygame.Surface, source: pygame.Surface, stroke):
    """Reveal real image pixels through an oil-pastel shaped dab."""
    x, y, angle, length, width = stroke
    brush = make_brush(length, width)
    rotated = pygame.transform.rotate(brush, -math.degrees(angle))
    rw, rh = rotated.get_size()
    dest = pygame.Rect(int(x - rw / 2), int(y - rh / 2), rw, rh)
    clip = dest.clip(canvas.get_rect())
    if clip.w <= 0 or clip.h <= 0:
        return

    bx = clip.x - dest.x
    by = clip.y - dest.y
    mask = rotated.subsurface((bx, by, clip.w, clip.h))

    # Must use convert_alpha so soft edges composite correctly
    patch = source.subsurface(clip).convert_alpha()
    patch.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    canvas.blit(patch, clip.topleft)


def main():
    print("Oil Pastel Studio", flush=True)
    img, w, h = load_image()
    print("Preparing…", flush=True)
    ang, mag, w, h = edge_maps(img)
    strokes = build_strokes(ang, mag, w, h)

    pix = img.load()
    top = [pix[x, 2][:3] for x in range(0, w, max(1, w // 10))]
    bg = (
        sum(c[0] for c in top) // len(top),
        sum(c[1] for c in top) // len(top),
        sum(c[2] for c in top) // len(top),
    )

    pygame.init()
    pygame.display.set_caption("Oil Pastel — R repaint · Esc quit")
    screen = pygame.display.set_mode((w, h))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("segoeui", 14)

    source = pygame.image.fromstring(img.tobytes(), img.size, "RGB").convert_alpha()
    canvas = pygame.Surface((w, h)).convert()

    def reset():
        canvas.fill(bg)
        return {"i": 0, "done": False}

    state = reset()
    print(f"One-pass painting — {len(strokes)} strokes, {w}x{h}", flush=True)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    _brush_cache.clear()
                    state = reset()

        if not state["done"]:
            if state["i"] < len(strokes):
                end = min(state["i"] + BATCH, len(strokes))
                for i in range(state["i"], end):
                    stamp_reveal(canvas, source, strokes[i])
                state["i"] = end
            else:
                # Soft close remaining pinholes with tiny dabs (still painted, not a photo dump)
                if "fill" not in state:
                    state["fill"] = 0
                    state["fill_pts"] = [
                        (fx + random.uniform(-0.4, 0.4), fy + random.uniform(-0.4, 0.4), random.uniform(0, math.pi), 5.5, 4.0)
                        for fy in range(0, h, 3)
                        for fx in range(0, w, 3)
                    ]
                pts = state["fill_pts"]
                if state["fill"] < len(pts):
                    end = min(state["fill"] + 80, len(pts))
                    for i in range(state["fill"], end):
                        stamp_reveal(canvas, source, pts[i])
                    state["fill"] = end
                else:
                    state["done"] = True

        screen.blit(canvas, (0, 0))

        if not state["done"]:
            if state["i"] < len(strokes) and state["i"] > 0:
                s = strokes[state["i"] - 1]
                pygame.draw.line(screen, (210, 130, 90), (s[0] + 4, s[1] - 16), (s[0], s[1]), 3)
                pct = int(90 * state["i"] / len(strokes))
            else:
                pct = 90 + int(10 * state.get("fill", 0) / max(1, len(state.get("fill_pts", [1]))))
            tag = font.render(f"Painting… {min(pct, 99)}%", True, (35, 32, 28))
            chip = pygame.Surface((tag.get_width() + 12, tag.get_height() + 6), pygame.SRCALPHA)
            chip.fill((250, 244, 234, 175))
            screen.blit(chip, (8, 8))
            screen.blit(tag, (14, 11))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
