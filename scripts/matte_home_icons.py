#!/usr/bin/env python3
"""
Matte homepage 3D icons: gradient studio backgrounds and near-white backdrops.

- Gradient / 棋盘格：border distance + flood（matte_saturn / matte_dragon / matte_rocket）
- 纯白 / 近白底：到 (255,255,255) 的欧氏距离 + flood（matte_near_white）

Run:  python scripts/matte_home_icons.py
       python scripts/matte_home_icons.py frog data   # 只处理列出的文件

Requires: pip install pillow numpy
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def dilate4(mask: np.ndarray, iterations: int) -> np.ndarray:
    m = mask.astype(np.bool_).copy()
    for _ in range(iterations):
        up = np.roll(m, -1, axis=0)
        up[-1, :] = False
        down = np.roll(m, 1, axis=0)
        down[0, :] = False
        left = np.roll(m, -1, axis=1)
        left[:, -1] = False
        right = np.roll(m, 1, axis=1)
        right[:, 0] = False
        m = m | up | down | left | right
    return m


def border_distance_map(rgb: np.ndarray, stride: int = 2) -> np.ndarray:
    """Min Euclidean RGB distance from each pixel to any border sample."""
    h, w, _ = rgb.shape
    flat = rgb.reshape(-1, 3).astype(np.float32)
    samples: list[list[float]] = []
    for x in range(0, w, stride):
        samples.append(rgb[0, x])
        samples.append(rgb[-1, x])
    for y in range(0, h, stride):
        samples.append(rgb[y, 0])
        samples.append(rgb[y, -1])
    b = np.array(samples, dtype=np.float32)
    dmin = np.empty(h * w, dtype=np.float32)
    step = 8192
    for i in range(0, h * w, step):
        blk = flat[i : i + step, None, :]
        d = np.sqrt(((blk - b[None, :, :]) ** 2).sum(axis=2))
        dmin[i : i + step] = d.min(axis=1)
    return dmin.reshape(h, w)


def flood_from_border(walkable: np.ndarray) -> np.ndarray:
    h, w = walkable.shape
    visited = np.zeros((h, w), dtype=np.bool_)
    q: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        if not (0 <= x < w and 0 <= y < h):
            return
        if visited[y, x] or not walkable[y, x]:
            return
        visited[y, x] = True
        q.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx] and walkable[ny, nx]:
                visited[ny, nx] = True
                q.append((nx, ny))
    return visited


def matte_near_white(arr: np.ndarray, tau: float = 40.0) -> np.ndarray:
    """Remove solid / near-white background (typical Gemini 导出白底)."""
    rgb = arr[:, :, :3].astype(np.float32)
    d = np.sqrt(((rgb - 255.0) ** 2).sum(axis=2))
    walkable = d < tau
    vis = flood_from_border(walkable)
    out = arr.copy()
    out[:, :, 3] = np.where(vis, 0, out[:, :, 3])
    fringe = (d < 22.0) & (out[:, :, 3] > 0)
    out[:, :, 3] = np.where(fringe, 0, out[:, :, 3])
    return out


def matte_saturn(arr: np.ndarray) -> np.ndarray:
    rgb = arr[:, :, :3]
    d = border_distance_map(rgb, stride=2)
    tau = 28.0
    walkable = d < tau
    vis = flood_from_border(walkable)
    out = arr.copy()
    out[:, :, 3] = np.where(vis, 0, out[:, :, 3])
    return out


def matte_dragon(arr: np.ndarray) -> np.ndarray:
    """与背景同色系时用「远距前景保护 + 窄阈值洪水」，减少蓝边晕圈。"""
    rgb = arr[:, :, :3]
    d = border_distance_map(rgb, stride=2)
    fg_far = d > 13.5
    protect = dilate4(fg_far, 24)
    walkable = (d < 9.0) & (~protect)
    vis = flood_from_border(walkable)
    out = arr.copy()
    out[:, :, 3] = np.where(vis, 0, out[:, :, 3])
    # 去掉与边框仍极相近的残留溢色
    fringe = (d < 7.5) & (out[:, :, 3] > 0)
    out[:, :, 3] = np.where(fringe, 0, out[:, :, 3])
    return out


def matte_rocket(arr: np.ndarray) -> np.ndarray:
    rgb = arr[:, :, :3]
    d = border_distance_map(rgb, stride=2)
    fg_far = d > 24.0
    protect = dilate4(fg_far, 26)
    walkable = (d < 10.5) & (~protect)
    vis = flood_from_border(walkable)
    out = arr.copy()
    out[:, :, 3] = np.where(vis, 0, out[:, :, 3])
    fringe = (d < 8.0) & (out[:, :, 3] > 0)
    out[:, :, 3] = np.where(fringe, 0, out[:, :, 3])
    return out


def feather_alpha_rgba(arr: np.ndarray, radius: float = 1.05) -> np.ndarray:
    """对 Alpha 轻量高斯羽化，柔化抠图硬边，便于与深色底融合。"""
    im = Image.fromarray(arr, "RGBA")
    r, g, b, a = im.split()
    a = a.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.array(Image.merge("RGBA", (r, g, b, a)))


def alpha_opening_remove_specks(arr: np.ndarray, min_filter: int = 3, max_filter: int = 7) -> np.ndarray:
    """形态学 opening：去掉火箭周围小的紫/白飞点，再略膨胀回主轮廓。"""
    im = Image.fromarray(arr, "RGBA")
    r, g, b, a = im.split()
    a = a.filter(ImageFilter.MinFilter(min_filter))
    a = a.filter(ImageFilter.MaxFilter(max_filter))
    return np.array(Image.merge("RGBA", (r, g, b, a)))


def main() -> None:
    base = Path(__file__).resolve().parents[1] / "static" / "images"
    # 首页当前三枚：青蛙 / 龙 / 底部土星（白底）；tau 可按素材微调
    jobs: list[tuple[str, tuple[str, ...], float]] = [
        ("home-icon-frog.png", ("feather",), 40.0),
        ("home-icon-dragon.png", ("feather",), 38.0),
        ("home-icon-bottom-saturn.png", ("feather",), 42.0),
    ]
    only = [f"home-icon-{x}.png" if not x.endswith(".png") else x for x in sys.argv[1:]]
    for name, post, tau in jobs:
        if only and name not in only:
            continue
        p = base / name
        if not p.is_file():
            print("skip (missing):", p, file=sys.stderr)
            continue
        im = Image.open(p).convert("RGBA")
        arr = np.array(im)
        m = matte_near_white(arr, tau=tau)
        if "open" in post:
            m = alpha_opening_remove_specks(m, min_filter=3, max_filter=7)
        if "feather" in post:
            m = feather_alpha_rgba(m, radius=1.05)
        Image.fromarray(m).save(p, optimize=True)
        a = m[:, :, 3]
        print("OK", p, "transparent%", round((a == 0).mean() * 100, 1), "post", post or "-")


if __name__ == "__main__":
    main()
