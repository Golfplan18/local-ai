#!/usr/bin/env python3
"""
Generate ◎ra (Ora) three-circle logo variants.

Each letter derives from the same base circle:
  ◎  — ring with concentric inner ring
  r  — top-half ring (arch) + left vertical stem
  a  — full ring + right vertical stem

Variants:
  A  — Equal weight (all circles same size)
  B  — Hierarchical (◎ gets additional outer ring)

Orientations:  H (horizontal)  |  V (vertical / totem)
Colors:  dark, light, amber, teal, blue, warm
"""
from PIL import Image, ImageDraw
import os
import tempfile

OUT = os.path.join(tempfile.gettempdir(), 'ora-logos')
os.makedirs(OUT, exist_ok=True)

COLORS = {
    'dark':  {'bg': (26,  26,  26),    'fg': (240, 240, 240)},
    'light': {'bg': (245, 245, 240),   'fg': (26,  26,  26)},
    'amber': {'bg': (26,  26,  26),    'fg': (255, 176,  40)},
    'teal':  {'bg': (26,  26,  26),    'fg': (64,  196, 180)},
    'blue':  {'bg': (26,  26,  26),    'fg': (90,  150, 220)},
    'warm':  {'bg': (26,  24,  20),    'fg': (224, 212, 192)},
}

SS = 4  # supersample factor for anti-aliasing


def _ring(d, cx, cy, r, sw, fg, bg):
    """Draw a ring via donut method: filled outer circle, punched inner."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg)
    ir = r - sw
    if ir > 0:
        d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=bg)


def make_logo(variant, orient, bg_rgb, fg_rgb, D=600):
    """
    Render one logo variant.

    D:  base circle diameter in 4x-supersampled drawing space.
        Output is downsampled to D/4 per circle.
    """
    hier = (variant == 'B')

    R   = D // 2                         # base circle radius
    sw  = max(int(R * 0.18), 2)          # stroke width (uniform across all strokes)
    gap = int(R * 0.38)                  # inter-letter gap (< inner ring radius per brand rule)
    ir  = int(R * 0.50)                  # inner ring radius of ◎
    hR  = int(R * 1.45) if hier else R   # hierarchical outer radius
    pad = int(R * 0.70)                  # canvas padding

    fg = (*fg_rgb, 255)
    bg = (*bg_rgb, 255)

    # ── Compute letter centres and canvas ──────────────────────────────────
    if orient == 'H':
        # O  r  a  left → right, vertically centred
        ocx = pad + hR
        rcx = ocx + hR + gap + R
        acx = rcx + R + gap + R
        W   = acx + R + pad
        H   = 2 * (pad + hR)
        cy  = H // 2
        ocy = rcy = acy = cy
    else:
        # O  r  a  top → bottom, horizontally centred
        cx  = pad + hR
        ocy = pad + hR
        rcy = ocy + hR + gap + R
        acy = rcy + R + gap + R
        W   = 2 * (pad + hR)
        H   = acy + R + pad
        ocx = rcx = acx = cx

    img  = Image.new('RGBA', (W, H), bg)
    d    = ImageDraw.Draw(img)

    # ── ◎  (O with inner ring, optionally hierarchical outer ring) ─────────
    if hier:
        _ring(d, ocx, ocy, hR, sw, fg, bg)       # outer hierarchical ring
        _ring(d, ocx, ocy, R,  sw, fg, bg)        # inner ring only (no smallest ring)
    else:
        _ring(d, ocx, ocy, R,  sw, fg, bg)        # base ring
        _ring(d, ocx, ocy, ir, sw, fg, bg)         # inner ring

    # ── r  (top-half arch + left stem) ─────────────────────────────────────
    _ring(d, rcx, rcy, R, sw, fg, bg)                                     # full ring
    d.rectangle([rcx - R - 1, rcy, rcx + R + 1, rcy + R + 1], fill=bg)   # erase bottom half
    d.rectangle([rcx - R, rcy - R, rcx - R + sw, rcy + R],    fill=fg)   # left stem

    # ── a  (full ring + right stem) ────────────────────────────────────────
    _ring(d, acx, acy, R, sw, fg, bg)                                     # full ring
    d.rectangle([acx + R - sw, acy - R, acx + R, acy + R],    fill=fg)   # right stem

    # ── Downsample 4x for anti-aliased output ─────────────────────────────
    return img.resize((W // SS, H // SS), Image.LANCZOS)


def main():
    print(f'Previews → {OUT}\n')

    # ── Standard previews: all variant × orientation × color combos ────────
    print('Standard previews:')
    for v in ('A', 'B'):
        for o in ('H', 'V'):
            for cn, cc in COLORS.items():
                img = make_logo(v, o, cc['bg'], cc['fg'])
                fn  = f'ora-{v}-{o}-{cn}.png'
                img.save(os.path.join(OUT, fn))
                print(f'  {fn}  {img.width}×{img.height}')

    # ── Large dark previews for close inspection ───────────────────────────
    print('\nLarge previews (dark):')
    for v in ('A', 'B'):
        for o in ('H', 'V'):
            img = make_logo(v, o, COLORS['dark']['bg'], COLORS['dark']['fg'], D=2000)
            fn  = f'ora-{v}-{o}-LARGE.png'
            img.save(os.path.join(OUT, fn))
            print(f'  {fn}  {img.width}×{img.height}')

    # ── High-res logo TIFFs (variant B only) ───────────────────────────────
    logo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo')
    os.makedirs(logo_dir, exist_ok=True)

    print(f'\nHigh-res logos → {logo_dir}')
    for o, label in (('H', 'horizontal'), ('V', 'vertical')):
        for cn, cc in COLORS.items():
            img = make_logo('B', o, cc['bg'], cc['fg'], D=4000)
            fn  = f'ora-{label}-{cn}.tiff'
            img.convert('RGB').save(os.path.join(logo_dir, fn), 'TIFF', compression='tiff_lzw')
            print(f'  {fn}  {img.width}×{img.height}')

    print(f'\nDone — {len(os.listdir(OUT))} previews, {len(os.listdir(logo_dir))} logos')


if __name__ == '__main__':
    main()
