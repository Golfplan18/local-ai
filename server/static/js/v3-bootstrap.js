/* V3 Phase 6.2 — New-thread bootstrap flow.
 *
 * Listens for `ora:new-thread-requested` (dispatched by sidebar.js when
 * the user clicks Plus on the spine, the new-thread command at the top
 * of the expanded sidebar, or the new-chat icon on the collapsed
 * dashboard). Opens a topic-prompt modal; on submit, POSTs the topic to
 * /api/bootstrap and renders the assembled summary into the output pane
 * with a "Context assembled for this thread" header per spec §6.1.
 *
 * Spec references:
 *   §6.1 — bootstrapping flow steps 1–6
 *   §6.3 — bootstrap routing (dedicated /api/bootstrap endpoint)
 */
(() => {
  // ── Modal DOM (created on first open) ──────────────────────────────────
  let modal       = null;
  let modalInput  = null;
  let modalSubmit = null;
  let modalCancel = null;
  let modalStatus = null;

  const buildModal = () => {
    if (modal) return;
    modal = document.createElement('div');
    modal.id = 'bootstrapModal';
    modal.className = 'bootstrap-modal';
    modal.innerHTML = `
      <div class="bootstrap-modal-backdrop"></div>
      <div class="bootstrap-modal-card" role="dialog" aria-modal="true" aria-labelledby="bootstrapModalTitle">
        <div class="bootstrap-modal-title" id="bootstrapModalTitle">New conversation</div>
        <div class="bootstrap-modal-prompt">What topic would you like to explore?</div>
        <input type="text" class="bootstrap-modal-input" placeholder="A short topic description..." />
        <div class="bootstrap-modal-status" aria-live="polite"></div>
        <div class="bootstrap-modal-actions">
          <button type="button" class="bootstrap-modal-cancel">Cancel</button>
          <button type="button" class="bootstrap-modal-submit">Start</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    modalInput  = modal.querySelector('.bootstrap-modal-input');
    modalSubmit = modal.querySelector('.bootstrap-modal-submit');
    modalCancel = modal.querySelector('.bootstrap-modal-cancel');
    modalStatus = modal.querySelector('.bootstrap-modal-status');

    modalCancel.addEventListener('click', closeModal);
    modal.querySelector('.bootstrap-modal-backdrop').addEventListener('click', closeModal);
    modalSubmit.addEventListener('click', submitTopic);
    modalInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitTopic(); }
      if (e.key === 'Escape')                { e.preventDefault(); closeModal(); }
    });
  };

  const openModal = () => {
    buildModal();
    modalInput.value = '';
    modalStatus.textContent = '';
    modalSubmit.disabled = false;
    modal.classList.add('show');
    // Focus the input on the next tick so the modal has time to render.
    setTimeout(() => modalInput.focus(), 0);
  };

  const closeModal = () => {
    if (modal) modal.classList.remove('show');
  };

  // ── Bootstrap submission ───────────────────────────────────────────────
  const currentTag = () => {
    if (document.body.classList.contains('stealth-mode')) return 'stealth';
    if (document.body.classList.contains('private-mode')) return 'private';
    return '';
  };

  const submitTopic = async () => {
    const topic = (modalInput.value || '').trim();
    if (!topic) {
      modalStatus.textContent = 'Topic is required.';
      return;
    }

    modalSubmit.disabled    = true;
    modalStatus.textContent = 'Assembling context from prior knowledge and conversations...';

    try {
      const resp = await fetch('/api/bootstrap', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ topic, tag: currentTag() }),
      });

      let data;
      try {
        data = await resp.json();
      } catch (e) {
        const text = await resp.text();
        throw new Error(`bootstrap returned non-JSON (${resp.status}): ${text.slice(0, 120)}`);
      }

      if (!resp.ok) {
        throw new Error(data.error || `bootstrap failed (${resp.status})`);
      }

      renderBootstrapOutput(data);
      closeModal();
    } catch (err) {
      modalStatus.textContent = 'Bootstrap failed: ' + (err.message || String(err));
      modalSubmit.disabled    = false;
    }
  };

  // ── Output pane rendering ──────────────────────────────────────────────
  const renderBootstrapOutput = (data) => {
    const outputPane = document.querySelector('.output-pane');
    if (!outputPane) return;

    // Drop the demo-content marker so the placeholder styling clears.
    outputPane.classList.remove('has-content');

    const block = document.createElement('div');
    block.className = 'bootstrap-context-block';
    if (data.fallback) block.classList.add('bootstrap-context-block-fallback');

    const header = document.createElement('div');
    header.className = 'bootstrap-context-block-header';
    header.textContent = 'Context assembled for this thread';
    block.appendChild(header);

    const subhead = document.createElement('div');
    subhead.className = 'bootstrap-context-block-subhead';
    subhead.textContent = `Topic: ${data.topic}  ·  ${data.match_count} sources`;
    if (data.fallback) {
      subhead.textContent += '  ·  (model unavailable, raw context shown)';
    }
    block.appendChild(subhead);

    const body = document.createElement('div');
    body.className = 'bootstrap-context-block-body';
    // Render summary as preformatted text to preserve spacing/citations
    // without pulling in a markdown renderer for this iteration.
    body.textContent = data.summary || '';
    block.appendChild(body);

    // Replace existing output pane content with the bootstrap block. The
    // user's first real message will append below it on the next turn.
    outputPane.replaceChildren(block);

    // Notify any other listeners that a thread has been bootstrapped.
    document.dispatchEvent(new CustomEvent('ora:thread-bootstrapped', {
      detail: { topic: data.topic, match_count: data.match_count, fallback: !!data.fallback },
    }));
  };

  // ── Wire the entry point ───────────────────────────────────────────────
  document.addEventListener('ora:new-thread-requested', openModal);

  // Public API for tests / programmatic invocation.
  window.OraBootstrap = {
    open:  openModal,
    close: closeModal,
  };
})();
