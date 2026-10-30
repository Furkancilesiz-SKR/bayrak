#!/usr/bin/env python3
"""
Karakterlerden olusan Turk bayragi + portre animasyonu.

Ekranin ortasindan buyuyen dalgali bir daire icinde, bayrak (hilal + yildiz)
ve sag tarafta senin verdigin portre harf/rakam karakterleriyle belirir.

Kurulum:   pip install pygame numpy pillow
Calistir:  python bayrak_glyph.py portre.png
           python bayrak_glyph.py portre.jpg --size 540x960 --cell 8
           python bayrak_glyph.py portre.png --export cikti.mp4   (ffmpeg gerekir)

Portre: PNG ve seffaf arka planli (kesilmis) ise en iyi sonucu verir.
Seffaf degilse kenarlari otomatik yumusatilir. Portre vermezsen sadece bayrak cikar.

Tuslar:  R = bastan oynat   S = ekran goruntusu   ESC/Q = cikis
"""
import argparse
import math
import os
import subprocess
import sys

import numpy as np
import pygame
from PIL import Image, ImageDraw, ImageFilter, ImageOps

RED = (227, 10, 23)
WHITE = (255, 255, 255)
# koyudan aciga: karakter yogunlugu rampasi
RAMP = ".,:;il1tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


# --------------------------------------------------------------------------
# Hedef gorsel: bayrak + portre
# --------------------------------------------------------------------------
def draw_flag(w, h):
    """Dikey ekrana sigan bayrak: kirmizi zemin, sol-ortada hilal ve yildiz."""
    ss = 2  # kenar yumusatma icin 2x ciz
    img = Image.new("RGB", (w * ss, h * ss), RED)
    d = ImageDraw.Draw(img)
    cx, cy = 0.30 * w * ss, 0.40 * h * ss
    R = 0.20 * w * ss                       # dis daire yaricapi
    r = R * 0.80                            # ic daire yaricapi
    off = R * 0.25                          # ic dairenin kaymasi
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=WHITE)
    d.ellipse([cx - r + off, cy - r, cx + r + off, cy + r], fill=RED)
    # bes kollu yildiz
    sx, sy = cx + R * 0.62, cy
    ro, ri = R * 0.46, R * 0.46 * 0.382
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5 + math.pi / 2  # ucu hilale baksin
        rad = ro if i % 2 == 0 else ri
        pts.append((sx + rad * math.cos(a), sy + rad * math.sin(a)))
    d.polygon(pts, fill=WHITE)
    return img.resize((w, h), Image.LANCZOS)


def load_portrait(path, w, h):
    """Portreyi sag alta yerlestirir. Doner: (gri[0..1], alfa[0..1]) w x h."""
    gray = np.zeros((h, w), np.float32)
    alpha = np.zeros((h, w), np.float32)
    if not path:
        return gray, alpha
    im = Image.open(path)
    im = ImageOps.exif_transpose(im).convert("RGBA")
    has_alpha = np.asarray(im.split()[3]).min() < 250

    # genisligin ~%62'sini kaplasin, sag alta otursun
    tw = int(w * 0.62)
    th = int(im.height * tw / im.width)
    if th > h * 0.80:
        th = int(h * 0.80)
        tw = int(im.width * th / im.height)
    im = im.resize((tw, th), Image.LANCZOS)

    a = np.asarray(im.split()[3], np.float32) / 255.0
    g = np.asarray(ImageOps.autocontrast(im.convert("L"), cutoff=1), np.float32) / 255.0

    if not has_alpha:
        # seffaflik yoksa: elips seklinde yumusak vinyet ile kenarlari erit
        yy, xx = np.mgrid[0:th, 0:tw].astype(np.float32)
        nx = (xx - tw * 0.5) / (tw * 0.5)
        ny = (yy - th * 0.5) / (th * 0.5)
        dist = np.sqrt(nx ** 2 + ny ** 2)
        a = np.clip((1.0 - dist) / 0.35, 0, 1)
        a = np.asarray(
            Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(tw * 0.02)),
            np.float32,
        ) / 255.0

    x0 = w - tw + int(tw * 0.04)
    y0 = h - th - int(h * 0.12)
    y0 = max(y0, 0)
    xs0, ys0 = max(x0, 0), y0
    sx0 = xs0 - x0
    ww = min(tw - sx0, w - xs0)
    hh = min(th, h - ys0)
    gray[ys0:ys0 + hh, xs0:xs0 + ww] = g[:hh, sx0:sx0 + ww]
    alpha[ys0:ys0 + hh, xs0:xs0 + ww] = a[:hh, sx0:sx0 + ww]
    return gray, alpha


# --------------------------------------------------------------------------
# Glyph atlasi
# --------------------------------------------------------------------------
def make_atlas(cw, ch):
    pygame.font.init()
    size = max(6, int(ch * 1.05))
    font = pygame.font.SysFont("consolas,dejavusansmono,couriernew,monospace", size, bold=True)
    atlas = np.zeros((len(RAMP), ch, cw), np.float32)
    for i, c in enumerate(RAMP):
        s = font.render(c, True, (255, 255, 255))
        arr = pygame.surfarray.array_alpha(s).T.astype(np.float32) / 255.0  # (h, w)
        hh, ww = min(ch, arr.shape[0]), min(cw, arr.shape[1])
        oy, ox = (ch - hh) // 2, (cw - ww) // 2
        atlas[i, oy:oy + hh, ox:ox + ww] = arr[:hh, :ww]
    return atlas


# --------------------------------------------------------------------------
# Animasyon
# --------------------------------------------------------------------------
class GlyphReveal:
    def __init__(self, w, h, cell, portrait, duration):
        self.W, self.H = w, h
        self.cw = cell
        self.ch = int(round(cell * 1.25))
        self.cols = w // self.cw
        self.rows = h // self.ch
        self.W, self.H = self.cols * self.cw, self.rows * self.ch
        self.duration = duration
        self.rng = np.random.default_rng(7)

        # hedef sahne (hucre cozunurlugunde ornekle)
        flag = np.asarray(draw_flag(self.W, self.H), np.float32) / 255.0
        gray, alpha = load_portrait(portrait, self.W, self.H)
        ys = (np.arange(self.rows) * self.ch + self.ch // 2)
        xs = (np.arange(self.cols) * self.cw + self.cw // 2)
        flag_c = flag[np.ix_(ys, xs)]
        gray_c = gray[np.ix_(ys, xs)]
        alpha_c = alpha[np.ix_(ys, xs)]

        is_white = (flag_c[..., 1] > 0.6)            # hilal / yildiz
        tone_flag = np.where(is_white, 0.92, 0.55) + self.rng.uniform(-0.08, 0.08, is_white.shape)

        # portre: gri renk, ton = parlaklik
        a3 = alpha_c[..., None]
        port_col = np.repeat(np.clip(gray_c * 1.1 + 0.15, 0, 1)[..., None], 3, axis=2)
        base_col = flag_c * (1 - a3) + port_col * a3
        tone = tone_flag * (1 - alpha_c) + np.clip(gray_c, 0.05, 1) * alpha_c

        self.color = np.clip(base_col, 0, 1).astype(np.float32)           # (rows, cols, 3)
        self.base_idx = np.clip((tone * (len(RAMP) - 1)).astype(np.int32), 0, len(RAMP) - 1)
        self.atlas = make_atlas(self.cw, self.ch)

        yy, xx = np.mgrid[0:self.rows, 0:self.cols].astype(np.float32)
        self.cx = self.cols * 0.5
        self.cy = self.rows * 0.52
        self.dx, self.dy = xx - self.cx, (yy - self.cy) * (self.ch / self.cw)
        self.dist = np.hypot(self.dx, self.dy)
        self.theta = np.arctan2(self.dy, self.dx)
        self.max_r = float(np.hypot(self.cols * 0.5, self.rows * 0.5 * self.ch / self.cw)) * 1.15
        self.phase = self.rng.uniform(0, 6.28, self.dist.shape).astype(np.float32)
        self.sparks = []
        self.reset()

    def reset(self):
        self.t = 0.0
        self.sparks = []

    # yavaslayarak buyuyen (ease-out) yaricap
    def radius(self, t):
        p = min(t / self.duration, 1.0)
        return self.max_r * (1 - (1 - p) ** 2.2)

    def step(self, dt):
        self.t += dt
        t = self.t
        r = self.radius(t)
        th = self.theta
        wob = (1 + 0.09 * np.sin(3 * th + t * 1.7) + 0.05 * np.sin(5 * th - t * 2.6)
               + 0.03 * np.sin(9 * th + t * 3.3))
        if t > self.duration:  # tam dolunca dalga hemen sonsun
            wob = 1 + (wob - 1) * max(0.0, 1 - (t - self.duration) * 1.5)
        edge = r * wob
        visible = self.dist < edge
        band = np.clip((edge - self.dist) / 3.0, 0, 1)          # kenara yakinlik
        glow = (1 - band) * visible                              # 0..1 (kenarda 1)

        # glyph titresimi: her hucre yavasca ramp uzerinde gezinir
        shimmer = np.sin(t * 3.0 + self.phase) * 1.6
        idx = np.clip(self.base_idx + shimmer.astype(np.int32), 0, len(RAMP) - 1)
        # rastgele karakter degisimi
        flick = self.rng.random(idx.shape) < 0.03
        idx = np.where(flick, np.clip(idx + self.rng.integers(-5, 6, idx.shape), 0, len(RAMP) - 1), idx)

        # atlas'tan tum glyphlari tek seferde olustur
        g = self.atlas[idx]                                      # (rows, cols, ch, cw)
        g = g.transpose(0, 2, 1, 3).reshape(self.rows * self.ch, self.cols * self.cw)

        bright = 0.95 + 0.25 * np.sin(t * 2.2 + self.phase)
        col = self.color * bright[..., None]
        col = col * (1 - glow[..., None] * 0.6) + glow[..., None] * 0.6   # kenar beyaza parlar
        col = col * visible[..., None]
        col_px = np.repeat(np.repeat(col, self.ch, axis=0), self.cw, axis=1)
        frame = (g[..., None] * col_px * 255).clip(0, 255).astype(np.uint8)

        # kivilcimlar
        if t < self.duration and len(self.sparks) < 40:
            for _ in range(2):
                a = self.rng.uniform(0, 6.283)
                wb = 1 + 0.09 * math.sin(3 * a + t * 1.7) + 0.05 * math.sin(5 * a - t * 2.6)
                rr = r * wb
                px = (self.cx + rr * math.cos(a)) * self.cw
                py = (self.cy + rr * math.sin(a) * self.cw / self.ch) * self.ch
                self.sparks.append([px, py, math.cos(a) * 40, math.sin(a) * 40, 1.0])
        for s in self.sparks:
            s[0] += s[2] * 0.016
            s[1] += s[3] * 0.016
            s[4] -= 0.02
        self.sparks = [s for s in self.sparks if s[4] > 0]
        for px, py, _, _, life in self.sparks:
            x, y = int(px), int(py)
            if 1 <= x < self.W - 1 and 1 <= y < self.H - 1:
                frame[y - 1:y + 2, x - 1:x + 2] = (255, int(255 * life), int(255 * life))
        return frame  # (H, W, 3)


# --------------------------------------------------------------------------
def parse_size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser(description="Karakterlerden bayrak + portre animasyonu")
    ap.add_argument("portrait", nargs="?", help="portre gorseli (png/jpg)")
    ap.add_argument("--size", default="540x960", type=parse_size, help="pencere boyutu, ornek 540x960")
    ap.add_argument("--cell", type=int, default=8, help="karakter genisligi (px). Kucuk = daha detay")
    ap.add_argument("--duration", type=float, default=9.0, help="dairenin dolma suresi (sn)")
    ap.add_argument("--export", help="mp4 olarak kaydet (ffmpeg gerekir), pencere acmaz")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    if args.portrait and not os.path.exists(args.portrait):
        sys.exit(f"Dosya bulunamadi: {args.portrait}")

    w, h = args.size
    anim = GlyphReveal(w, h, args.cell, args.portrait, args.duration)

    if args.export:
        total = int((args.duration + 3) * args.fps)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{anim.W}x{anim.H}", "-r", str(args.fps), "-i", "-",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", args.export]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for _ in range(total):
            p.stdin.write(anim.step(1 / args.fps).tobytes())
        p.stdin.close()
        p.wait()
        print("Kaydedildi:", args.export)
        return

    pygame.init()
    screen = pygame.display.set_mode((anim.W, anim.H))
    pygame.display.set_caption("Bayrak")
    clock = pygame.time.Clock()
    running, shot = True, 0
    while running:
        dt = clock.tick(60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif e.key == pygame.K_r:
                    anim.reset()
                elif e.key == pygame.K_s:
                    pygame.image.save(screen, f"ekran_{shot}.png")
                    shot += 1
        frame = anim.step(dt)
        pygame.surfarray.blit_array(screen, frame.transpose(1, 0, 2))
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
