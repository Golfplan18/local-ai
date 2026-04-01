#!/usr/bin/env python3
"""
Generate ai.icns icon variants for the LocalAI app bundle.
Single-story geometric 'a' (circle + right stem) + geometric 'i' (bar + dot).
Uses 4x supersampling for smooth anti-aliasing.
"""
import os
import shutil
import subprocess
from PIL import Image, ImageDraw

VARIANTS = {
    'ai-dark':  {'bg': (26,  26,  26),   'fg': (240, 240, 240)},
    'ai-light': {'bg': (245, 245, 240),  'fg': (26,  26,  26)},
    'ai-amber': {'bg': (26,  26,  26),   'fg': (255, 176,  40)},
    'ai-teal':  {'bg': (26,  26,  26),   'fg': ( 64, 196, 180)},
    'ai-blue':  {'bg': (26,  26,  26),   'fg': ( 90, 150, 220)},
}

SIZES = [16, 32, 128, 256, 512]


def draw_icon(size, bg, fg):
    """
    Draw the 'ai' lettermark at `size` pixels using 4x supersampling.

    'a' design: full circle ring (donut method) with a vertical stem on the
    right side that descends from the top of the circle to the baseline.
    The stem overlaps the right edge of the ring, so the two forms merge.

    'i' design: thin vertical bar + circular dot above, no serifs.
    """
    S = 4          # supersample factor
    W = size * S   # working canvas size

    img = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    fg_c = (*fg, 255)
    bg_c = (*bg, 255)

    # ── Background rounded rectangle ────────────────────────────────────────
    corner_r = int(W * 0.175)
    d.rounded_rectangle([0, 0, W - 1, W - 1], radius=corner_r, fill=bg_c)

    # ── Shared metrics ───────────────────────────────────────────────────────
    stroke   = W * 0.068   # uniform stroke width for all strokes

    cap_top  = W * 0.185   # top of tallest feature
    baseline = W * 0.808   # bottom of all strokes
    letter_h = baseline - cap_top

    # ── 'a' geometry ─────────────────────────────────────────────────────────
    # Circle diameter fills ~84% of letter height; top of circle = cap_top.
    circ_d  = letter_h * 0.84
    outer_r = circ_d / 2.0
    inner_r = outer_r - stroke        # hollow centre radius

    a_cy = baseline - outer_r          # circle centre (bottom of circle = baseline)

    # ── 'i' geometry ─────────────────────────────────────────────────────────
    dot_r    = stroke * 0.75           # tittle radius — 1.5× stem width
    i_col_w  = max(stroke, 2 * dot_r)  # column width for the 'i'

    # ── Horizontal layout: centre the pair ──────────────────────────────────
    gap     = stroke * 0.90            # space between 'a' right edge and 'i'
    pair_w  = circ_d + gap + i_col_w
    x0      = (W - pair_w) / 2.0      # leftmost x of pair

    a_cx    = x0 + outer_r             # 'a' circle centre x
    i_col_x = x0 + circ_d + gap        # left edge of 'i' column
    i_cx    = i_col_x + i_col_w / 2.0  # 'i' centre x

    # ── Draw 'a' ─────────────────────────────────────────────────────────────
    # 1. Filled outer circle
    d.ellipse(
        [a_cx - outer_r, a_cy - outer_r,
         a_cx + outer_r, a_cy + outer_r],
        fill=fg_c
    )
    # 2. Hollow inner circle (punches out centre, leaving a ring)
    if inner_r > 1:
        d.ellipse(
            [a_cx - inner_r, a_cy - inner_r,
             a_cx + inner_r, a_cy + inner_r],
            fill=bg_c
        )
    # 3. Stem: right side, tangent to circle edge, runs from cap_top → baseline.
    #    Positioned so its right edge aligns with the circle's rightmost point.
    #    The stem fills the gap in the ring's hollow at the 3-o'clock position.
    stem_right = a_cx + outer_r
    stem_left  = stem_right - stroke
    # Stem height matches circle exactly: top of circle → bottom of circle
    d.rectangle([stem_left, a_cy - outer_r, stem_right, a_cy + outer_r], fill=fg_c)

    # ── Draw 'i' ─────────────────────────────────────────────────────────────
    # 'i' aligns to same top/bottom as 'a' circle
    a_top = a_cy - outer_r   # top of circle = top of 'i' column
    a_bot = a_cy + outer_r   # bottom of circle = bottom of 'i' column

    # 1. Vertical stem — same height as 'a' (a_top to a_bot)
    d.rectangle(
        [i_cx - stroke / 2, a_top,
         i_cx + stroke / 2, a_bot],
        fill=fg_c
    )
    # 2. Tittle (dot) — gap below dot matches the a–i letter gap
    dot_cy = a_top - gap - dot_r
    d.ellipse(
        [i_cx - dot_r, dot_cy - dot_r,
         i_cx + dot_r, dot_cy + dot_r],
        fill=fg_c
    )

    # ── Downsample to target size ─────────────────────────────────────────────
    return img.resize((size, size), Image.LANCZOS)


def make_iconset(variant_name, bg, fg, out_dir):
    iconset_path = os.path.join(out_dir, f'{variant_name}.iconset')
    os.makedirs(iconset_path, exist_ok=True)

    for sz in SIZES:
        draw_icon(sz,      bg, fg).save(os.path.join(iconset_path, f'icon_{sz}x{sz}.png'))
        draw_icon(sz * 2,  bg, fg).save(os.path.join(iconset_path, f'icon_{sz}x{sz}@2x.png'))

    icns_path = os.path.join(out_dir, f'{variant_name}.icns')
    subprocess.run(
        ['iconutil', '-c', 'icns', iconset_path, '-o', icns_path],
        check=True
    )
    shutil.rmtree(iconset_path)
    print(f'  {icns_path}')


def main():
    icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'icons')
    os.makedirs(icons_dir, exist_ok=True)

    # Write a debug preview PNG at 512px for visual inspection
    preview = draw_icon(512, VARIANTS['ai-dark']['bg'], VARIANTS['ai-dark']['fg'])
    preview.save('/tmp/ai_preview_v2.png')
    print('Preview: /tmp/ai_preview_v2.png')

    print('Generating icon variants…')
    for name, colors in VARIANTS.items():
        make_iconset(name, colors['bg'], colors['fg'], icons_dir)

    print('Done.')


if __name__ == '__main__':
    main()
