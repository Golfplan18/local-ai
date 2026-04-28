/**
 * ora-visual-compiler / renderers/stub.js
 * Placeholder renderer used for all types not yet implemented.
 * Returns valid, well-formed SVG that includes the envelope's title.
 *
 * Produces semantic CSS classes only — no inline styles.
 * WP-1.4 (theme) will supply the matching CSS.
 *
 * Depends on: errors.js
 * Load order: errors.js → validator.js → renderers/stub.js → dispatcher.js → index.js
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._renderers = window.OraVisualCompiler._renderers || {};

window.OraVisualCompiler._renderers.stub = (function () {

  const { CODES, make } = window.OraVisualCompiler.errors;

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /**
   * render(envelope) → { svg: string, errors: [], warnings: [W_STUB_RENDERER] }
   *
   * envelope is a validated ora-visual spec block.
   * The SVG always contains the title (required by WP-1.1 test).
   */
  function render(envelope) {
    const warnings = [
      make(CODES.W_STUB_RENDERER,
        `Stub renderer active for type '${envelope.type}'. ` +
        `No semantic visual is produced; replace when WP-1.2/1.3 lands this type.`,
        'type'),
    ];

    const title = envelope.title ? _esc(envelope.title) : '';
    const typeLabel = _esc(envelope.type || 'unknown');
    const gist = envelope.semantic_description && envelope.semantic_description.level_1_elemental
      ? _esc(envelope.semantic_description.level_1_elemental)
      : '';

    // Semantic description level-1 (gist) used as primary accessible text.
    // aria-label set on root element; <title> inside SVG for screen readers.
    const ariaLabel = (title || typeLabel) + (gist ? ` — ${gist}` : '');

    const svg = `<svg
  xmlns="http://www.w3.org/2000/svg"
  class="ora-visual ora-visual--${_esc(envelope.type || 'unknown')} ora-visual--stub"
  role="img"
  aria-label="${_esc(ariaLabel)}"
  viewBox="0 0 480 320"
>
  <title class="ora-visual__accessible-title">${_esc(ariaLabel)}</title>

  <!-- Background placeholder area -->
  <rect
    class="ora-visual__stub-bg"
    x="0" y="0" width="480" height="320"
    rx="4"
  />

  <!-- Title -->
  ${title ? `<text
    class="ora-visual__title"
    x="240" y="48"
    text-anchor="middle"
    dominant-baseline="middle"
  >${title}</text>` : ''}

  <!-- Stub notice -->
  <text
    class="ora-visual__stub-label"
    x="240" y="${title ? '150' : '120'}"
    text-anchor="middle"
    dominant-baseline="middle"
  >[ ${typeLabel} ]</text>

  <text
    class="ora-visual__stub-notice"
    x="240" y="${title ? '178' : '148'}"
    text-anchor="middle"
    dominant-baseline="middle"
  >Renderer not yet implemented</text>

  <!-- Level-1 semantic gist (accessibility) -->
  ${gist ? `<text
    class="ora-visual__gist"
    x="240" y="${title ? '230' : '200'}"
    text-anchor="middle"
    dominant-baseline="middle"
  >${gist}</text>` : ''}
</svg>`;

    return { svg, errors: [], warnings };
  }

  return { render };
}());
