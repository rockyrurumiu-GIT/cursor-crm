#!/usr/bin/env python3
"""Strip checkerboard from octopus mascot PNG → transparent PNG + tight crop."""

from __future__ import annotations

from collections import deque

import numpy as np
from PIL import Image
import argparse
from pathlib import Path


def flood_edge_mask(spec: np.ndarray, *, eight_connected: bool = True) -> np.ndarray:
    """Pixels reachable from image border via moves within truthy spec."""
    h, w = spec.shape[:2]
    cand = spec.astype(np.uint8)
    vis = np.zeros((h, w), dtype=np.uint8)
    q: deque[tuple[int, int]] = deque()

    for x in range(w):
        if cand[0, x]:
            q.append((0, x))
        if cand[h - 1, x]:
            q.append((h - 1, x))
    for y in range(h):
        if cand[y, 0]:
            q.append((y, 0))
        if cand[y, w - 1]:
            q.append((y, w - 1))

    neigh4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
    neigh8 = neigh4 + ((-1, -1), (-1, 1), (1, -1), (1, 1))
    neigh = neigh8 if eight_connected else neigh4

    while q:
        y, x = q.popleft()
        if vis[y, x]:
            continue
        if not cand[y, x]:
            continue
        vis[y, x] = 1
        for dy, dx in neigh:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                q.append((ny, nx))

    return vis.astype(bool)


def largest_blob(mask: np.ndarray) -> np.ndarray:
    """Keep largest 4-connected True region."""
    h, w = mask.shape
    lbl = np.zeros((h, w), dtype=np.int32)
    best_lab = 0
    best_n = 0
    cur = 0
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or lbl[y, x]:
                continue
            cur += 1
            stack = [(y, x)]
            lbl[y, x] = cur
            nloc = 0
            while stack:
                yy, xx = stack.pop()
                nloc += 1
                for ny, nx in (yy - 1, xx), (yy + 1, xx), (yy, xx - 1), (yy, xx + 1):
                    if (
                        0 <= ny < h
                        and 0 <= nx < w
                        and mask[ny, nx]
                        and lbl[ny, nx] == 0
                    ):
                        lbl[ny, nx] = cur
                        stack.append((ny, nx))
            if nloc > best_n:
                best_n = nloc
                best_lab = cur
    return lbl == best_lab


def gray_cluster_centers(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Light / dark checker neutrals from low-chroma pixels."""
    r = rgb[:, :, 0].astype(np.float64)
    gch = rgb[:, :, 1].astype(np.float64)
    bch = rgb[:, :, 2].astype(np.float64)
    mx = np.maximum(np.maximum(r, gch), bch)
    mn = np.minimum(np.minimum(r, gch), bch)
    chroma = mx - mn
    pix = np.stack([r, gch, bch], axis=-1)
    muted = chroma < 43
    muted_pix = pix[muted]
    lum_m = muted_pix.reshape(-1, 3).mean(axis=1)
    split = np.median(lum_m)
    hi = muted_pix[lum_m > split]
    lo = muted_pix[lum_m <= split]
    if len(hi) < 8000 or len(lo) < 8000:
        # Fallback if median split uneven
        hi = muted_pix[lum_m > 178]
        lo = muted_pix[lum_m <= 178]
    mean_hi = hi.mean(axis=0)
    mean_lo = lo.mean(axis=0)
    return mean_hi, mean_lo


def checkerboard_via_distance(
    rgb: np.ndarray,
    *,
    chroma_lim: float,
    dist_lim: float,
    cluster_hi: np.ndarray | None = None,
    cluster_lo: np.ndarray | None = None,
) -> np.ndarray:
    """Mask of pixels that visually match checkerboard neutrals."""
    r = rgb[:, :, 0].astype(np.float64)
    gch = rgb[:, :, 1].astype(np.float64)
    bch = rgb[:, :, 2].astype(np.float64)
    mx = np.maximum(np.maximum(r, gch), bch)
    mn = np.minimum(np.minimum(r, gch), bch)
    chroma = mx - mn
    pix = np.stack([r, gch, bch], axis=-1)

    if cluster_hi is None or cluster_lo is None:
        mean_hi, mean_lo = gray_cluster_centers(rgb)
    else:
        mean_hi = cluster_hi
        mean_lo = cluster_lo
    dh = np.linalg.norm(pix - mean_hi, axis=-1)
    dl = np.linalg.norm(pix - mean_lo, axis=-1)
    dmin = np.minimum(dh, dl)

    neutral = chroma < chroma_lim
    close = dmin < dist_lim
    return neutral & close


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--src",
        type=Path,
        default=root / "static/images/_source/octopus-raw.png",
        help="Flattened PNG with fake checkerboard background",
    )
    ap.add_argument(
        "--dst",
        type=Path,
        default=root / "static/images/chatbot-octopus.png",
        help="Output transparent PNG",
    )
    args = ap.parse_args()

    src = args.src
    dst = args.dst

    pad = 10

    rgba = np.array(Image.open(src).convert("RGBA"))
    rgb = rgba[:, :, :3]

    mean_hi, mean_lo = gray_cluster_centers(rgb)

    # Tuned on this asset: clears both light / dark squares without eating pink body.
    bg_candidate = checkerboard_via_distance(
        rgb,
        chroma_lim=42.0,
        dist_lim=50.5,
        cluster_hi=mean_hi,
        cluster_lo=mean_lo,
    )
    bg_reachable = flood_edge_mask(bg_candidate, eight_connected=True)
    fg_initial = ~bg_reachable
    fg = largest_blob(fg_initial)

    alpha = fg.astype(np.uint8) * 255
    out = np.dstack([rgba[:, :, :3], alpha])

    ys, xs = np.where(fg)
    y0 = max(int(ys.min()) - pad, 0)
    y1 = min(int(ys.max()) + 1 + pad, rgba.shape[0])
    x0 = max(int(xs.min()) - pad, 0)
    x1 = min(int(xs.max()) + 1 + pad, rgba.shape[1])
    cropped = out[y0:y1, x0:x1]

    Image.fromarray(cropped).save(str(dst), optimize=True)
    print(
        str(dst),
        "crop",
        cropped.shape[:2],
        "opaque_px",
        int(fg.sum()),
        "opaque_frac",
        round(float(fg.mean()), 4),
        "gray_hi",
        np.round(mean_hi, 1).tolist(),
        "gray_lo",
        np.round(mean_lo, 1).tolist(),
    )


if __name__ == "__main__":
    main()
