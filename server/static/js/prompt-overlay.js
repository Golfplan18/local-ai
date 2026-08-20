/* ============================================================
   Prompt Overlay — V3 design backlog item 8B.
   ----------------------------------------------------------------
   The output pane shows the response of the currently-displayed
   turn. The prompt is hidden by default. Clicking the expand
   button in the output pane header summons an overlay that covers
   the input pane in the left column. The overlay is read-only and
   scrollable.

   Public API on window.OraPromptOverlay:
     show(promptText)  — open the overlay; promptText optional,
                         falls back to placeholder
     hide()            — close the overlay
     toggle()          — flip state
     isOpen()          — boolean
     setPrompt(text)   — update content without changing visibility
   ============================================================ */

(() => {
  'use strict';

  const overlay        = document.getElementById('promptOverlay');
  const overlayContent = document.getElementById('promptOverlayContent');
  const overlayClose   = document.getElementById('promptOverlayCloseBtn');
  const expandBtn      = document.getElementById('outputPaneExpandBtn');
  const inputPane      = document.querySelector('.input-pane');
  const leftColumn     = document.querySelector('.left-column');

  if (!overlay || !overlayContent || !expandBtn || !inputPane || !leftColumn) {
    console.warn('[prompt-overlay] required elements missing; not initializing');
    return;
  }

  // Defensive: ensure left-column establishes a positioning context.
  if (getComputedStyle(leftColumn).position === 'static') {
    leftColumn.style.position = 'relative';
  }

  // Placeholder content shown when no prompt has been provided yet.
  const PLACEHOLDER_PROMPT = (
    'This is the prompt that generated the response currently shown in ' +
    'the Findings pane below.\n\n' +
    'Once a Dialogue turn is selected, this overlay displays that ' +
    'turn\'s actual prompt text.\n\n' +
    'The overlay is read-only — you ' +
    'cannot type into it.\n\n' +
    'Close with the ✕ button at the top right, the expander button in ' +
    'the Findings pane header, or by pressing Esc.'
  );

  // Size the overlay to cover the input pane exactly, leaving the bridge
  // strip and its Inquiry controls available below it.
  // Called when opening, on window resize, and via ResizeObserver when
  // the bridge is dragged (which resizes the input pane).
  const sizeOverlay = () => {
    overlay.style.height = inputPane.offsetHeight + 'px';
  };

  const isOpen = () => overlay.classList.contains('is-open');

  const showOverlay = () => {
    sizeOverlay();
    overlay.classList.add('is-open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('prompt-overlay-open');
    if (expandBtn) {
      expandBtn.setAttribute('aria-expanded', 'true');
      expandBtn.setAttribute('aria-label', 'Hide prompt for this turn');
    }
  };

  const hideOverlay = () => {
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('prompt-overlay-open');
    if (expandBtn) {
      expandBtn.setAttribute('aria-expanded', 'false');
      expandBtn.setAttribute('aria-label', 'Show prompt for this turn');
    }
  };

  const toggleOverlay = () => {
    if (isOpen()) hideOverlay();
    else showOverlay();
  };

  const setPrompt = (text) => {
    if (typeof text === 'string' && text.length > 0) {
      overlayContent.textContent = text;
    } else {
      overlayContent.textContent = PLACEHOLDER_PROMPT;
    }
  };

  // Initialize with placeholder so the overlay has content the first
  // time it's opened. Real data swaps in via setPrompt() later.
  setPrompt(null);

  // Wire up controls.
  expandBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleOverlay();
  });

  if (overlayClose) {
    overlayClose.addEventListener('click', (e) => {
      e.stopPropagation();
      hideOverlay();
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen()) {
      hideOverlay();
    }
  });

  // Stay in sync with bridge drag and window resize.
  window.addEventListener('resize', () => {
    if (isOpen()) sizeOverlay();
  });

  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => {
      if (isOpen()) sizeOverlay();
    });
    ro.observe(inputPane);
  }

  // Public API.
  window.OraPromptOverlay = {
    show: (promptText) => { setPrompt(promptText); showOverlay(); },
    hide: hideOverlay,
    toggle: toggleOverlay,
    isOpen,
    setPrompt,
  };
})();
