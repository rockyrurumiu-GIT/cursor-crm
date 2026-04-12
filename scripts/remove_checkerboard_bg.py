#!/usr/bin/env python3
"""
Remove baked-in checkerboard from PNG exports (opaque gray RGB, alpha=255).

首页当前素材为「渐变底」时，请改用 scripts/matte_home_icons.py（到边框色盘距离 + 洪水填充）。

Previous version flood-filled all low-saturation pixels and ate into horns / jaws.
This version:
  1. Builds a "strong foreground" mask: chroma (max-min RGB) >= strong_chroma
  2. Dilates that mask — protects a band around real icon pixels (incl. gray details)
  3. Flood-fills from the image border only through pixels with chroma <= pass_chroma
     AND not in the protected dilated region (protected pixels block the flood)

Run:  python scripts/remove_checkerboard_bg.py
Requires: pip install pillow numpy
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path


def dilate4(mask: "object", iterations: int) -> "object":
    """Binary dilation with 4-connectivity, iterations times."""
    import numpy as np

    m = mask.astype(np.bool_).copy()
    for _ in range(iterations):
        up = np.roll(m, -1, axis=0)
        down = np.roll(m, 1, axis=0)
        left = np.roll(m, -1, axis=1)
        right = np.roll(m, 1, axis=1)
        up[-1, :] = False
        down[0, :] = False
        left[:, -1] = False
        right[:, 0] = False
        m = m | up | down | left | right
    return m


def process_rgba(
    arr: "object",
    *,
    strong_chroma: int = 24,
    pass_chroma: int = 17,
    dilate_iters: int = 28,
) -> "object":
    import numpy as np

    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.int16)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    chroma = mx - mn

    strong_fg = chroma >= strong_chroma
    protect = dilate4(strong_fg, dilate_iters)

    # Walk only through "weak" pixels; protected pixels are walls
    walkable = (chroma <= pass_chroma) & (~protect)

    visited = np.zeros((h, w), dtype=np.bool_)
    q: deque[tuple[int, int]] = deque()

    def try_seed(x: int, y: int) -> None:
        if not (0 <= x < w and 0 <= y < h):
            return
        if visited[y, x] or not walkable[y, x]:
            return
        visited[y, x] = True
        q.append((x, y))

    for x in range(w):
        try_seed(x, 0)
        try_seed(x, h - 1)
    for y in range(h):
        try_seed(0, y)
        try_seed(w - 1, y)

    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx] and walkable[ny, nx]:
                visited[ny, nx] = True
                q.append((nx, ny))

    out = arr.copy()
    out[:, :, 3] = np.where(visited, 0, out[:, :, 3])
    return out


def main() -> None:
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        print("请先安装: pip install pillow numpy", file=sys.stderr)
        sys.exit(1)

    base = Path(__file__).resolve().parents[1] / "static" / "images"
    files = ["home-icon-dragon.png", "home-icon-rocket.png"]
    for name in files:
        p = base / name
        if not p.is_file():
            print("skip (missing):", p, file=sys.stderr)
            continue
        im = Image.open(p).convert("RGBA")
        arr = np.array(im)
        new = process_rgba(
            arr,
            strong_chroma=24,
            pass_chroma=17,
            dilate_iters=28,
        )
        Image.fromarray(new).save(p, optimize=True)
        a = new[:, :, 3]
        print("OK", p, "transparent%", round((a == 0).mean() * 100, 1))


if __name__ == "__main__":
    main()
