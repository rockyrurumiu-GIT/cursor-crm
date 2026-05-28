#!/usr/bin/env python3
"""Throme logo1 (white bg) → transparent PNG for header/login."""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt


def flood_edge(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    vis = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        if mask[0, x]:
            q.append((0, x))
        if mask[h - 1, x]:
            q.append((h - 1, x))
    for y in range(h):
        if mask[y, 0]:
            q.append((y, 0))
        if mask[y, w - 1]:
            q.append((y, w - 1))
    while q:
        y, x = q.popleft()
        if vis[y, x] or not mask[y, x]:
            continue
        vis[y, x] = True
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                q.append((ny, nx))
    return vis


def white_bg_to_rgba(src: Path, *, pad: int = 8) -> np.ndarray:
    """Return RGBA uint8 array with transparent background."""
    rgb = np.array(Image.open(src).convert("RGB"), dtype=np.float64)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    chroma = mx - mn
    lum = (r + g + b) / 3.0

    # White / near-white background (incl. interior holes of the M).
    bg_like = (lum >= 250.0) & (chroma <= 20.0)
    bg = flood_edge(bg_like) | bg_like
    # All white pixels (incl. interior M loops) stay background — never fill those holes.
    fg = ~bg

    # Soft alpha only on the outer 1.5px boundary (avoids white fringes on dark UI).
    dist_out = distance_transform_edt(~fg)
    alpha = np.where(fg, 255.0, 0.0)
    edge = fg & (dist_out <= 2.0)
    alpha[edge] = np.clip(255.0 - dist_out[edge] * (255.0 / 2.0), 0, 255)

    a = alpha / 255.0
    out_rgb = rgb.copy()
    safe = np.maximum(a, 1e-6)
    for c in range(3):
        ch = out_rgb[:, :, c]
        ch = np.where(a > 0.01, (ch - 255.0 * (1.0 - a)) / safe, 0.0)
        out_rgb[:, :, c] = np.clip(ch, 0, 255)

    rgba = np.dstack([out_rgb.astype(np.uint8), alpha.astype(np.uint8)])
    a_ch = rgba[:, :, 3]
    ys, xs = np.where(a_ch > 6)
    y0 = max(int(ys.min()) - pad, 0)
    y1 = min(int(ys.max()) + 1 + pad, rgba.shape[0])
    x0 = max(int(xs.min()) - pad, 0)
    x1 = min(int(xs.max()) + 1 + pad, rgba.shape[1])
    return rgba[y0:y1, x0:x1]


def resize_rgba(arr: np.ndarray, height: int) -> np.ndarray:
    """Supersample downscale to keep thin highlights continuous."""
    im = Image.fromarray(arr)
    if im.height <= height:
        return arr
    mid_h = min(im.height, max(height * 2, 400))
    mid_w = max(1, int(im.width * mid_h / im.height))
    im = im.resize((mid_w, mid_h), Image.Resampling.LANCZOS)
    w = max(1, int(im.width * height / im.height))
    im = im.resize((w, height), Image.Resampling.LANCZOS)
    out = np.array(im)

    # Heal 1px breaks from downscale without touching outer edge.
    rgb = out[:, :, :3].astype(np.float64)
    alpha = out[:, :, 3].astype(np.float64)
    solid = alpha > 160
    for _ in range(4):
        for y in range(out.shape[0]):
            for x in range(1, out.shape[1] - 1):
                if alpha[y, x] > 20:
                    continue
                l, r = alpha[y, x - 1], alpha[y, x + 1]
                if l > 160 and r > 160:
                    alpha[y, x] = min(255.0, (l + r) * 0.5)
                    rgb[y, x] = (rgb[y, x - 1] + rgb[y, x + 1]) * 0.5
        for y in range(1, out.shape[0] - 1):
            for x in range(out.shape[1]):
                if alpha[y, x] > 20:
                    continue
                u, d = alpha[y - 1, x], alpha[y + 1, x]
                if u > 160 and d > 160:
                    alpha[y, x] = min(255.0, (u + d) * 0.5)
                    rgb[y, x] = (rgb[y - 1, x] + rgb[y + 1, x]) * 0.5

    # Extend apex rows where downscale clipped the top highlight.
    h, w = alpha.shape
    for y in range(max(0, h - 4)):
        for x in range(w):
            if alpha[y, x] > 20:
                continue
            below = alpha[y + 1, x]
            if below > 160:
                alpha[y, x] = min(255.0, below * 0.94)
                rgb[y, x] = rgb[y + 1, x]

    out[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return out


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=root / "Throme logo1.png")
    ap.add_argument("--dst", type=Path, default=root / "static/images/throme-logo.png")
    ap.add_argument("--height", type=int, default=128, help="Output height in px")
    args = ap.parse_args()

    rgba = white_bg_to_rgba(args.src)
    rgba = resize_rgba(rgba, args.height)

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba).save(args.dst, optimize=True)
    print(args.dst, rgba.shape[1], rgba.shape[0], "aspect", round(rgba.shape[1] / rgba.shape[0], 4))


if __name__ == "__main__":
    main()
