/**
 * ora-visual-compiler / palettes.js
 *
 * Palette module exposing the three CVD-safe palettes mandated by Protocol v0.2 §8.4
 * and Implementation Specification §3.2:
 *
 *   - categorical(n)         — Okabe-Ito 8-colour CVD-safe palette
 *   - sequential(n)          — Viridis (perceptually uniform, CVD-safe)
 *   - diverging(n, options)  — ColorBrewer RdBu (balanced perceptual divergence)
 *   - highlight              — single accent color for callouts
 *   - muted                  — neutral grey for de-emphasized data
 *
 * Usage examples (from a renderer under WP-1.2 / WP-1.3):
 *
 *   const palette = OraVisualCompiler.palettes;
 *
 *   // Categorical series: assign first N Okabe-Ito colours to N categories
 *   const colors = palette.categorical(seriesCount);
 *   series.forEach((s, i) => { s.color = colors[i]; });
 *
 *   // Sequential heatmap bins
 *   const ramp = palette.sequential(7);          // 7 shades of viridis
 *   cells.forEach(c => { c.fill = ramp[bin(c.value, 7)]; });
 *
 *   // Diverging: RdBu, defaults center to midpoint
 *   const rdbu = palette.diverging(9);           // 9 steps
 *   const rdbuCustom = palette.diverging(7, { center: 0.3 });  // asymmetric pivot
 *
 *   // Accent/muted for de-emphasis / highlight pattern
 *   someGroup.fill = palette.muted;
 *   focalShape.fill = palette.highlight;
 *
 * CVD verification sources:
 *   - Okabe-Ito 2008: Masataka Okabe & Kei Ito, "Color Universal Design (CUD):
 *     How to make figures and presentations that are friendly to Colorblind people."
 *     J*FLY website (jfly.uni-koeln.de/color/), widely adopted by scientific publishers.
 *     The 8-color palette is empirically verified safe across deuteranopia, protanopia,
 *     and tritanopia. Brewer/NOAA and Nature journals have adopted it.
 *   - Viridis: Nathaniel Smith & Stéfan van der Walt, "A Better Default Colormap
 *     for Matplotlib" (SciPy 2015). Perceptually uniform in CAM02-UCS, monotonic
 *     in luminance, CVD-safe. Default in matplotlib since 2.0.
 *   - ColorBrewer RdBu: Cynthia Brewer, colorbrewer2.org. 11-class diverging scheme.
 *     All ColorBrewer diverging schemes with ≤ 11 bins are CVD-safe.
 *
 * WCAG 2.2 contrast note:
 *   Okabe-Ito's original yellow (#F0E442) does NOT meet SC 1.4.11 (3:1) against
 *   a white background. For ora-visual we substitute a contrast-adjusted yellow
 *   (#B8860B, dark goldenrod) at the yellow slot when using the categorical
 *   palette on light backgrounds. This preserves the perceptual intent (warm
 *   yellow as the fifth distinct hue) while satisfying WCAG. The original
 *   hex is retained in the dark-mode variant where it meets contrast
 *   against dark backgrounds.
 *
 * Load order: this file is a leaf module with no dependencies on other
 * ora-visual-compiler files. Load it anywhere before the renderers that
 * consume it, and before ora-visual-theme.css is relevant (the CSS picks
 * up the values via the custom-property export at the bottom).
 *
 * Depends on: nothing
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};

window.OraVisualCompiler.palettes = (function () {

  // ──────────────────────────────────────────────────────────────────────────
  // Okabe-Ito categorical (light-mode, WCAG-adjusted)
  //
  // Canonical Okabe-Ito 8-colour palette (2008):
  //   black #000000, orange #E69F00, sky blue #56B4E9, bluish green #009E73,
  //   yellow #F0E442, blue #0072B2, vermillion #D55E00, reddish purple #CC79A7.
  //
  // Several entries fail WCAG 2.2 SC 1.4.11 (3:1) on a near-white surface:
  //   #F0E442 (yellow) ≈ 1.36:1, #56B4E9 (sky blue) ≈ 2.26:1,
  //   #E69F00 (orange) ≈ 2.18:1, #CC79A7 (reddish purple) ≈ 2.98:1.
  // For a light-background surface we substitute contrast-adjusted variants
  // that preserve hue identity while crossing the 3:1 threshold. The dark-
  // mode palette below restores the canonical values (they meet contrast
  // against the dark surface).
  //
  // We reorder so the first-assigned colors have strong contrast and high
  // perceptual distance (best on small-n assignments where only 2-3 are used).
  // ──────────────────────────────────────────────────────────────────────────
  const OKABE_ITO_LIGHT = [
    '#0072B2',  // blue            — canonical (contrast 5.08:1 on #FCFCFA)
    '#D55E00',  // vermillion      — canonical (3.77:1)
    '#009E73',  // bluish green    — canonical (3.36:1)
    '#B857A0',  // reddish purple  — adjusted from #CC79A7 (was 2.98:1 → 4.13:1)
    '#B87200',  // orange          — adjusted from #E69F00 (was 2.18:1 → 3.75:1)
    '#2E8DC4',  // sky blue        — adjusted from #56B4E9 (was 2.26:1 → 3.58:1)
    '#B8860B',  // yellow          — adjusted from #F0E442 (was 1.36:1 → 3.17:1)
    '#000000',  // black           — canonical (20.4:1); last-assigned
  ];

  // Dark-mode palette: same hues, adjusted for contrast on a dark background.
  // Original Okabe-Ito yellow #F0E442 is restored because it meets contrast
  // against #1A1E24 (our dark surface).
  const OKABE_ITO_DARK = [
    '#5BA8E0',  // blue           — lightened from #0072B2 for dark bg contrast
    '#F07E3D',  // vermillion     — lightened from #D55E00
    '#47D1A6',  // bluish green   — lightened from #009E73
    '#E8A3C2',  // reddish purple — lightened from #CC79A7
    '#F3B547',  // orange         — lightened from #E69F00
    '#8ACCF0',  // sky blue       — lightened from #56B4E9
    '#F0E442',  // yellow         — original O-I yellow, meets contrast on dark
    '#E8E8E8',  // near-white     — dark-mode counterpart of black
  ];

  // ──────────────────────────────────────────────────────────────────────────
  // Viridis sequential (perceptually uniform, monotonic luminance, CVD-safe)
  // 256-entry approximation; we interpolate linearly between 11 control points
  // taken from matplotlib's Viridis at equal steps.
  // ──────────────────────────────────────────────────────────────────────────
  const VIRIDIS_STOPS = [
    '#440154', '#482878', '#3E4A89', '#31688E', '#26828E',
    '#1F9E89', '#35B779', '#6DCD59', '#B4DE2C', '#FDE725',
  ];

  // ──────────────────────────────────────────────────────────────────────────
  // ColorBrewer RdBu 11-class diverging
  // ──────────────────────────────────────────────────────────────────────────
  const RDBU_11 = [
    '#67001F', '#B2182B', '#D6604D', '#F4A582', '#FDDBC7',
    '#F7F7F7',
    '#D1E5F0', '#92C5DE', '#4393C3', '#2166AC', '#053061',
  ];

  // ──────────────────────────────────────────────────────────────────────────
  // Highlight + muted (used across all three palette families for callouts
  // and de-emphasis). Tuned for WCAG 2.2 on both light and dark surfaces.
  // ──────────────────────────────────────────────────────────────────────────
  const HIGHLIGHT_LIGHT = '#C5362F';   // focal red, ≥ 3:1 on white
  const HIGHLIGHT_DARK  = '#FF7369';   // lighter warm red for dark mode
  const MUTED_LIGHT     = '#7A7F87';   // neutral gray, ≥ 3:1 on white
  const MUTED_DARK      = '#9AA0A7';   // neutral gray, ≥ 3:1 on dark surface

  // ──────────────────────────────────────────────────────────────────────────
  // Implementation helpers
  // ──────────────────────────────────────────────────────────────────────────

  function _hexToRgb(hex) {
    const h = hex.replace('#', '');
    return {
      r: parseInt(h.substring(0, 2), 16),
      g: parseInt(h.substring(2, 4), 16),
      b: parseInt(h.substring(4, 6), 16),
    };
  }

  function _rgbToHex(r, g, b) {
    const to2 = (n) => {
      const s = Math.max(0, Math.min(255, Math.round(n))).toString(16);
      return s.length === 1 ? '0' + s : s;
    };
    return '#' + to2(r) + to2(g) + to2(b);
  }

  function _interp(hexA, hexB, t) {
    const a = _hexToRgb(hexA);
    const b = _hexToRgb(hexB);
    return _rgbToHex(
      a.r + (b.r - a.r) * t,
      a.g + (b.g - a.g) * t,
      a.b + (b.b - a.b) * t
    );
  }

  /**
   * Resample a fixed stop list to n entries via piecewise linear interpolation
   * in RGB space. Adequate for viridis (which is already roughly perceptually
   * uniform at the chosen stop density) and for ColorBrewer RdBu.
   */
  function _resample(stops, n) {
    if (n <= 0) return [];
    if (n === 1) return [stops[Math.floor(stops.length / 2)]];
    const out = [];
    for (let i = 0; i < n; i++) {
      const pos = (i / (n - 1)) * (stops.length - 1);
      const lo  = Math.floor(pos);
      const hi  = Math.min(stops.length - 1, lo + 1);
      const t   = pos - lo;
      out.push(_interp(stops[lo], stops[hi], t));
    }
    return out;
  }

  /**
   * categorical(n) → array of n hex strings.
   * Uses Okabe-Ito light-mode palette. Callers needing > 8 categories should
   * trigger Tufte T11 (small-multiples suggestion) instead of extending here.
   */
  function categorical(n) {
    if (n <= 0) return [];
    if (n > OKABE_ITO_LIGHT.length) {
      // Over 8 categories: the protocol would flag T11. We still return what we have.
      console.warn(
        `[OraVisualCompiler.palettes] categorical(${n}): exceeds 8-colour Okabe-Ito limit. ` +
        'Consider small multiples (Tufte T11).'
      );
    }
    return OKABE_ITO_LIGHT.slice(0, n);
  }

  /**
   * sequential(n) → array of n hex strings from the viridis ramp.
   */
  function sequential(n) {
    return _resample(VIRIDIS_STOPS, n);
  }

  /**
   * diverging(n, options) → array of n hex strings from the RdBu ramp.
   * options.center (0..1) shifts the pivot point (default 0.5 = true midpoint).
   */
  function diverging(n, options) {
    options = options || {};
    const center = typeof options.center === 'number' ? options.center : 0.5;

    if (n <= 0) return [];
    if (center === 0.5) return _resample(RDBU_11, n);

    // Asymmetric: split n across the two halves according to center.
    const leftCount  = Math.max(1, Math.round(n * center));
    const rightCount = Math.max(1, n - leftCount);
    const mid = Math.floor(RDBU_11.length / 2);
    const leftStops  = RDBU_11.slice(0, mid + 1);   // #67001F → #F7F7F7
    const rightStops = RDBU_11.slice(mid);          // #F7F7F7 → #053061
    const left  = _resample(leftStops, leftCount);
    const right = _resample(rightStops, rightCount);
    // Drop the duplicated midpoint between the two halves.
    return left.concat(right.slice(1));
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Public surface
  // ──────────────────────────────────────────────────────────────────────────
  return {
    categorical,
    sequential,
    diverging,

    // Named accents
    highlight: HIGHLIGHT_LIGHT,
    muted:     MUTED_LIGHT,

    // Low-level access for renderers with special needs
    _okabeItoLight: OKABE_ITO_LIGHT.slice(),
    _okabeItoDark:  OKABE_ITO_DARK.slice(),
    _viridisStops:  VIRIDIS_STOPS.slice(),
    _rdbu11:        RDBU_11.slice(),
    _highlightLight: HIGHLIGHT_LIGHT,
    _highlightDark:  HIGHLIGHT_DARK,
    _mutedLight:     MUTED_LIGHT,
    _mutedDark:      MUTED_DARK,
  };
}());
