/* Tooltip migration — moves any `title="..."` attribute to
 * `data-tooltip="..."` so the custom CSS tooltip in
 * `components/tooltip.css` renders above the element instead of the
 * browser-default tooltip below the cursor. Skips elements that have
 * `data-tooltip-keep-title` (escape hatch for places that want the
 * native behavior).
 *
 * Re-runs on subsequent DOM mutations so dynamically inserted rows
 * (sidebar conversation list, paused queue cards, etc.) also get the
 * treatment without each call site needing to know about this.
 *
 * `aria-label` is intentionally left intact; screen readers still
 * announce the same string.
 */
(() => {
  const migrate = (root) => {
    if (!root || root.nodeType !== 1) return;
    const targets = (root.matches && root.matches('[title]'))
      ? [root, ...root.querySelectorAll('[title]')]
      : root.querySelectorAll
        ? [...root.querySelectorAll('[title]')]
        : [];
    targets.forEach((el) => {
      if (el.hasAttribute('data-tooltip-keep-title')) return;
      const t = el.getAttribute('title');
      if (!t) return;
      // Avoid clobbering an explicit data-tooltip if one is already set.
      if (!el.hasAttribute('data-tooltip')) {
        el.setAttribute('data-tooltip', t);
      }
      el.removeAttribute('title');
    });
  };

  const init = () => {
    migrate(document.body);
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === 'childList') {
          m.addedNodes.forEach((n) => migrate(n));
        } else if (m.type === 'attributes' && m.attributeName === 'title') {
          migrate(m.target);
        }
      }
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['title'],
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
