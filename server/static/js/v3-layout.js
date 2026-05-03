/* V3 Phase 3 + 4.6 — Horizontal spine drag + universal collapse mechanic.
 *
 * Coexists with the existing inline script in index-v3.html that handles
 * the vertical bridge-strip drags. This module is purely for the
 * left-right axis: drag the spine horizontally to resize the left and
 * right columns, with event-horizon collapse when either pane shrinks
 * below its minimum useful width.
 *
 * Spec references:
 *   §1.2 — horizontal spine drag, full-travel pane collapse
 *   §1.7 — universal collapse mechanic (event horizon, click-to-expand
 *          asymmetry: button-collapse → last width / drag-collapse → default)
 *
 * Operating contract:
 *   - The spine background is the drag handle. Clicks on buttons or the
 *     wordmark do NOT initiate drag (they fall through to their own
 *     handlers).
 *   - During drag, column widths update live so the user can see what
 *     they're doing.
 *   - At mouseup (the "event horizon"):
 *       * If a column is below MIN_PANE_W → snap-collapse it
 *       * If a column was just released within snap-back distance →
 *         snap to MIN_PANE_W and stay open
 *       * Otherwise commit the width and remember it as the last
 *         non-collapsed width
 *   - Clicking on a collapsed column expands it:
 *       * If it was collapsed by an explicit button → restore last width
 *       * If it was collapsed by drag → restore to default (centered)
 *
 * Collapsed columns are CSS-styled with a thin double-border treatment;
 * internal content is hidden via overflow.
 */
(() => {
  const shell    = document.querySelector('.ora-shell');
  const spine    = document.querySelector('.spine');
  const leftCol  = document.querySelector('.left-column');
  const rightCol = document.querySelector('.right-column');
  if (!shell || !spine || !leftCol || !rightCol) return;

  const COLLAPSED_W   = 40;   // icon-width when collapsed
  const MIN_PANE_W    = 220;  // event horizon threshold
  const SNAP_BACK_PX  = 30;   // pull-back-from-edge tolerance

  let leftCollapsed         = false;
  let rightCollapsed        = false;
  let leftLastUncollapsedW  = null;
  let rightLastUncollapsedW = null;
  let leftCollapsedBy       = null;  // 'drag' | 'button'
  let rightCollapsedBy      = null;

  // Persist column widths to the shell as CSS custom properties. The grid
  // template in layout.css consumes these when set, falling back to 1fr
  // when unset (so the un-resized initial layout matches what was there).
  const applyWidths = (leftW, rightW) => {
    shell.style.setProperty('--ora-left-w',  leftW  + 'px');
    shell.style.setProperty('--ora-right-w', rightW + 'px');
  };

  const totalRoom = () => leftCol.offsetWidth + rightCol.offsetWidth;

  // ── Drag state ─────────────────────────────────────────────────────────
  let dragging      = false;
  let dragStartX    = 0;
  let dragStartLeft = 0;
  let dragStartRight = 0;

  const onSpineMouseDown = (e) => {
    // Only initiate drag from non-interactive regions of the spine.
    if (e.target.closest('button')) return;
    if (e.target.closest('.spine-wordmark')) return;
    if (e.target.closest('[role="button"]')) return;

    dragging       = true;
    dragStartX     = e.clientX;
    dragStartLeft  = leftCol.offsetWidth;
    dragStartRight = rightCol.offsetWidth;
    document.body.classList.add('spine-dragging');
    e.preventDefault();
  };

  const onMouseMove = (e) => {
    if (!dragging) return;
    const dx          = e.clientX - dragStartX;
    const total       = dragStartLeft + dragStartRight;
    let   newLeft     = dragStartLeft + dx;
    let   newRight    = dragStartRight - dx;

    // Allow widths to go below MIN during drag; the event-horizon test
    // happens at mouseup. Just clamp at zero so we don't compute negatives.
    if (newLeft  < 0) { newRight = total; newLeft  = 0; }
    if (newRight < 0) { newLeft  = total; newRight = 0; }

    applyWidths(newLeft, newRight);
  };

  const onMouseUp = () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove('spine-dragging');

    const leftNow  = leftCol.offsetWidth;
    const rightNow = rightCol.offsetWidth;

    // Event-horizon check on whichever side is below threshold.
    if (leftNow < MIN_PANE_W) {
      // Released past the event horizon → commit collapse.
      if (leftNow < MIN_PANE_W - SNAP_BACK_PX) {
        collapsePane('left', 'drag');
      } else {
        // In the snap-back zone → restore to MIN_PANE_W.
        const total = totalRoom();
        applyWidths(MIN_PANE_W, total - MIN_PANE_W);
        leftLastUncollapsedW = MIN_PANE_W;
        rightLastUncollapsedW = total - MIN_PANE_W;
      }
    } else if (rightNow < MIN_PANE_W) {
      if (rightNow < MIN_PANE_W - SNAP_BACK_PX) {
        collapsePane('right', 'drag');
      } else {
        const total = totalRoom();
        applyWidths(total - MIN_PANE_W, MIN_PANE_W);
        leftLastUncollapsedW = total - MIN_PANE_W;
        rightLastUncollapsedW = MIN_PANE_W;
      }
    } else {
      // Both above minimum → remember as the last uncollapsed widths.
      leftLastUncollapsedW  = leftNow;
      rightLastUncollapsedW = rightNow;
    }
  };

  const collapsePane = (side, by) => {
    const total = totalRoom();
    if (side === 'left') {
      const w = leftCol.offsetWidth;
      if (w > COLLAPSED_W) leftLastUncollapsedW = w;
      leftCol.classList.add('collapsed');
      leftCollapsed   = true;
      leftCollapsedBy = by;
      applyWidths(COLLAPSED_W, total - COLLAPSED_W);
    } else {
      const w = rightCol.offsetWidth;
      if (w > COLLAPSED_W) rightLastUncollapsedW = w;
      rightCol.classList.add('collapsed');
      rightCollapsed   = true;
      rightCollapsedBy = by;
      applyWidths(total - COLLAPSED_W, COLLAPSED_W);
    }
  };

  const expandPane = (side) => {
    const total = totalRoom();
    if (side === 'left') {
      const target = (leftCollapsedBy === 'button' && leftLastUncollapsedW)
        ? leftLastUncollapsedW
        : total / 2;  // drag-collapsed defaults to centered
      leftCol.classList.remove('collapsed');
      leftCollapsed   = false;
      leftCollapsedBy = null;
      applyWidths(target, total - target);
    } else {
      const target = (rightCollapsedBy === 'button' && rightLastUncollapsedW)
        ? rightLastUncollapsedW
        : total / 2;
      rightCol.classList.remove('collapsed');
      rightCollapsed   = false;
      rightCollapsedBy = null;
      applyWidths(total - target, target);
    }
  };

  // Click on a collapsed pane's border → expand. Use mousedown so the
  // gesture is responsive; capture-phase so internal content (already
  // hidden by CSS, but defensive) doesn't intercept.
  const onLeftMouseDown = (e) => {
    if (leftCollapsed) {
      e.stopPropagation();
      e.preventDefault();
      expandPane('left');
    }
  };
  const onRightMouseDown = (e) => {
    if (rightCollapsed) {
      e.stopPropagation();
      e.preventDefault();
      expandPane('right');
    }
  };

  spine.addEventListener('mousedown', onSpineMouseDown);
  leftCol.addEventListener('mousedown', onLeftMouseDown, true);
  rightCol.addEventListener('mousedown', onRightMouseDown, true);
  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup',   onMouseUp);

  // ── QQB (chat-zone) collapse — V3 Phase 4.7 ────────────────────────────
  // The right column hosts the QQB (chat-zone) above a bridge above the
  // canvas (right-pane). Resolution 2026-04-30: the logo's travel limits
  // are hard (mode buttons block upward, session buttons block downward)
  // and the bridge clamp keeps the QQB at or above its minimum height —
  // there is no auto-collapse via logo drag. The QQB is collapsed only
  // programmatically (e.g., spine dragged fully right per §1.6, or a
  // Phase 5 mode dropdown calling OraLayout.collapseQQB()) and
  // re-expanded by clicking the collapsed border.
  const chatZone = document.querySelector('.chat-zone');
  let qqbCollapsed       = false;
  let qqbLastUncollapsedH = null;
  let qqbCollapsedBy     = null;
  // Snapshot the inline-style height so click-to-expand can restore it.
  // The existing inline script writes chatZone.style.height during the
  // bridge drag — that value is the canonical "current QQB height".
  const recordQQBHeight = () => {
    if (!chatZone) return;
    const h = chatZone.offsetHeight;
    if (h > 40) qqbLastUncollapsedH = h;
  };

  const collapseQQB = (by = 'button') => {
    if (!chatZone || qqbCollapsed) return;
    recordQQBHeight();
    chatZone.classList.add('collapsed');
    qqbCollapsed   = true;
    qqbCollapsedBy = by;
  };

  const expandQQB = () => {
    if (!chatZone || !qqbCollapsed) return;
    chatZone.classList.remove('collapsed');
    qqbCollapsed = false;
    if (qqbCollapsedBy === 'button' && qqbLastUncollapsedH) {
      chatZone.style.height = qqbLastUncollapsedH + 'px';
    } else {
      // Drag-collapse → default. Without a hard "default", clear inline
      // height and let the existing bridge drag re-clamp on next interaction.
      chatZone.style.height = '';
    }
    qqbCollapsedBy = null;
  };

  // Click on collapsed QQB → expand. Fires before the bridge mousedown
  // because chat-zone is above the bridge in DOM and event order; using
  // capture phase to stop the bridge handler from also firing.
  if (chatZone) {
    chatZone.addEventListener('mousedown', (e) => {
      if (qqbCollapsed) {
        e.stopPropagation();
        e.preventDefault();
        expandQQB();
      }
    }, true);
  }

  // Public API. Phase 5 dropdowns (Stealth/Private New/Fork/Exit) and
  // Phase 6 (bootstrap) hooks will call these explicitly. The collapse
  // mechanic is the same shape as the horizontal pane collapse so callers
  // can reason about the whole interface uniformly.
  window.OraLayout = {
    collapseLeft:  () => collapsePane('left',  'button'),
    collapseRight: () => collapsePane('right', 'button'),
    expandLeft:    () => expandPane('left'),
    expandRight:   () => expandPane('right'),
    collapseQQB:   () => collapseQQB('button'),
    expandQQB,
    state: () => ({
      leftCollapsed, rightCollapsed,
      leftCollapsedBy, rightCollapsedBy,
      leftLastUncollapsedW, rightLastUncollapsedW,
      qqbCollapsed, qqbCollapsedBy, qqbLastUncollapsedH,
    }),
  };
})();
