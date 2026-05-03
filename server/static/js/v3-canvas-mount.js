/* V3 — Mount the Konva visual panel into .right-pane.
 *
 * Initializes a VisualPanel instance on the right-pane element so the
 * canvas (Phase 1.6 visual canvas) becomes interactive: drawing tools,
 * shapes-with-internal-text (Phase 7.1), and serialization to
 * spatial_representation that the O submit button (Phase 7.2) can pick
 * up via OraVisualPanel.captureFromPanel().
 *
 * Operating contract:
 *   - Single VisualPanel mounted on the .right-pane element
 *   - panelId = "v3-canvas" (used by VisualPanel for IDs / aria)
 *   - Exposed on window.OraCanvas for the submit handler and tests
 *   - If Konva or VisualPanel failed to load, mount is a no-op + logs
 *     a single warning so the page still works without the canvas
 */
(() => {
  if (typeof Konva === 'undefined') {
    console.warn('[v3-canvas-mount] Konva not loaded; skipping canvas mount');
    return;
  }
  if (typeof VisualPanel === 'undefined') {
    console.warn('[v3-canvas-mount] VisualPanel not loaded; skipping canvas mount');
    return;
  }

  const mount = () => {
    const right = document.querySelector('.right-pane');
    if (!right) {
      console.warn('[v3-canvas-mount] .right-pane not found');
      return;
    }
    // Add the visual-panel class so the existing CSS styles apply.
    right.classList.add('visual-panel');

    let panel;
    try {
      panel = new VisualPanel(right, { id: 'v3-canvas' });
      panel.init();
    } catch (e) {
      console.warn('[v3-canvas-mount] VisualPanel init failed:', e);
      return;
    }

    // Stash for the submit handler + tests.
    right._oraPanel = panel;
    window.OraCanvas = {
      panel,
      // Convenience: capture the current canvas state as
      // spatial_representation JSON ready to ship to /chat/multipart.
      capture: () => {
        if (window.OraCanvasSerializer && typeof window.OraCanvasSerializer.captureFromPanel === 'function') {
          return window.OraCanvasSerializer.captureFromPanel(panel);
        }
        if (window.OraCanvasSerializer && typeof window.OraCanvasSerializer.serialize === 'function'
            && panel && panel.userInputLayer) {
          return window.OraCanvasSerializer.serialize(panel.userInputLayer);
        }
        return null;
      },
      hasContent: () => {
        if (!panel || !panel.userInputLayer) return false;
        const kids = (panel.userInputLayer.getChildren && panel.userInputLayer.getChildren()) || [];
        for (let i = 0; i < kids.length; i++) {
          const k = kids[i];
          if (k && typeof k.getAttr === 'function' && k.getAttr('name') === 'user-shape') return true;
        }
        return false;
      },
    };

    // V3 canvas UX wins — toggle the .canvas-empty class on the panel
    // host whenever the userInputLayer's shape count changes between
    // zero and non-zero. The CSS uses this to show / hide the empty
    // hint in the canvas viewport. We also toggle a `.canvas-ready`
    // class on the O wordmark so the submit affordance gains an accent
    // ring whenever there's drawn content to submit.
    const updateCanvasState = () => {
      const has = window.OraCanvas.hasContent();
      right.classList.toggle('canvas-empty', !has);
      const o = document.getElementById('logo-o');
      if (o) o.classList.toggle('canvas-ready', has);
      document.dispatchEvent(new CustomEvent('ora:canvas-state-changed', {
        detail: { hasContent: has },
      }));
    };
    // Initial state.
    updateCanvasState();
    // Konva Layer fires `add` and `remove` events on child changes.
    if (panel.userInputLayer && typeof panel.userInputLayer.on === 'function') {
      panel.userInputLayer.on('add.vp3-state remove.vp3-state', updateCanvasState);
    }

    document.dispatchEvent(new CustomEvent('ora:canvas-mounted', {
      detail: { panelId: panel.panelId },
    }));
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
