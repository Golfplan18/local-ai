/**
 * tests/cases/test-visual-slots-pane.js — V3 Visual tab pane suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Covers server/static/visual-slots-pane.js, the install-Chunk-11
 * replacement for the classic ConfigPanel embed on the Settings →
 * Visual tab:
 *   1. Primary cards render for image_generates + video_generates only.
 *   2. Preferred select carries the stored value.
 *   3. Fallback-chain editor: one removable chip per chain entry, an
 *      "+ add fallback" select offering unused providers, removal POSTs
 *      the shortened chain, adding appends to the end.
 *   4. Advanced routing renders as an always-visible section (no
 *      disclosure) holding the remaining slots with capability
 *      summaries, marks empty slots "off", and survives an edit
 *      re-render; image_extracts (different shape) never renders.
 *   5. A stored provider missing from the registry still renders,
 *      tagged "not in registry".
 *   6. Changing preferred POSTs a per-slot patch with the new value and
 *      drops it from the fallback chain.
 *   7. Provider notices: an unusable preferred shows its setup reason
 *      with an "Open External APIs" jump (dispatches the open-settings
 *      event); an available-but-noteworthy provider (async video) shows
 *      an info note without the warning glyph.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const SLOTS = {
  image_generates: {
    preferred: 'openrouter:openai/gpt-5.4-image-2',
    fallback: [
      'openrouter:google/gemini-3.1-flash-image-preview',
      'openrouter:openai/gpt-5-image',
      'local-diffusers',
    ],
    _note: 'annotation that must survive client edits',
  },
  video_generates: { preferred: 'replicate', fallback: [] },
  image_edits: { preferred: 'local-diffusers', fallback: ['replicate'] },
  image_critique: { preferred: null, fallback: [] },
  style_trains: { preferred: 'ghost-provider', fallback: [] },
  image_extracts: { interactive: 'openrouter:openai/gpt-5', agent: 'x' },
};

const PROVIDERS = {
  image_generates: [
    { provider_id: 'openrouter:openai/gpt-5.4-image-2',
      display_name: 'GPT-5.4 Image 2  ($8.0/$15.0/M)', available: true },
    { provider_id: 'openrouter:google/gemini-3.1-flash-image-preview',
      display_name: 'Gemini 3.1 Flash Image', available: true },
    { provider_id: 'openrouter:openai/gpt-5-image',
      display_name: 'GPT-5 Image', available: true },
    { provider_id: 'local-diffusers', available: false,
      reason: 'install diffusers + torch to enable offline image generation',
      kind: 'local' },
  ],
  video_generates: [
    { provider_id: 'replicate', available: false,
      reason: 'set Replicate token in Settings → External APIs', kind: 'api' },
    { provider_id: 'openrouter:google/veo-3', display_name: 'Veo 3',
      available: true,
      reason: 'Async — submission returns immediately; generation takes '
            + '30s–10min and requires OpenRouter credits.' },
  ],
  image_edits: [
    { provider_id: 'local-diffusers', available: true },
    { provider_id: 'replicate', available: true },
  ],
  image_critique: [{ provider_id: 'replicate', available: false, reason: '' }],
  style_trains: [{ provider_id: 'replicate', available: true }],
};

const CAPABILITIES = {
  slots: {
    image_edits: { summary: 'Modify a region of an existing image (inpaint).' },
    image_critique: { summary: 'Structured critique against a rubric.' },
    style_trains: { summary: 'Train a style adapter / LoRA from reference images.' },
  },
};

module.exports = {
  label: 'Visual slots pane (Settings → Visual capability routing)',

  run: async function (ctx, record) {
    const win = ctx.win;
    const tick = () => new Promise((r) => setTimeout(r, 0));

    // Fetch mock — GET slots, GET providers, GET capabilities, POST recorder.
    const posts = [];
    const jsonResponse = (obj) =>
      Promise.resolve({ json: () => Promise.resolve(obj) });
    const savedFetch = win.fetch;
    win.fetch = function (url, opts) {
      if (url === '/config/routing/slots' && opts && opts.method === 'POST') {
        posts.push(JSON.parse(opts.body));
        return jsonResponse({ ok: true, router_reloaded: true });
      }
      if (url === '/config/routing/slots') {
        return jsonResponse({ slots: JSON.parse(JSON.stringify(SLOTS)) });
      }
      if (url === '/api/capability/providers') {
        return jsonResponse({ slots: PROVIDERS });
      }
      if (url === '/static/config/capabilities.json') {
        return jsonResponse(CAPABILITIES);
      }
      return Promise.reject(new Error('unexpected fetch: ' + url));
    };

    try {
      const modPath = path.join(__dirname, '..', '..', '..', 'visual-slots-pane.js');
      win.eval(fs.readFileSync(modPath, 'utf-8'));

      const P = win.OraVisualSlotsPane;
      record('pane: module exposed on window',
             !!P && typeof P.init === 'function');
      if (!P) return;

      const host = win.document.createElement('div');
      win.document.body.appendChild(host);
      P.init(host);
      await tick(); await tick();

      // 1. Primary cards
      const cards = host.querySelectorAll('[data-slot-card]');
      record('primary: exactly two cards (image + video)',
             cards.length === 2
             && cards[0].dataset.slotCard === 'image_generates'
             && cards[1].dataset.slotCard === 'video_generates',
             'count=' + cards.length);

      // 2. Preferred select — stored value selected
      const prefSel = host.querySelector(
        '[data-slot="image_generates"][data-field="preferred"]');
      record('preferred: stored value selected',
             !!prefSel && prefSel.value === 'openrouter:openai/gpt-5.4-image-2',
             prefSel && prefSel.value);

      // 3. Chain editor — chips in chain order, names de-priced
      const chips = host.querySelectorAll(
        '[data-slot-card="image_generates"] .ora-vslots-chip');
      record('chain: one chip per fallback entry',
             chips.length === 3, 'count=' + chips.length);
      record('chain: chips keep chain order',
             chips.length === 3
             && chips[0].textContent.indexOf('Gemini 3.1 Flash Image') !== -1
             && chips[1].textContent.indexOf('GPT-5 Image') !== -1
             && chips[2].textContent.indexOf('local-diffusers') !== -1,
             Array.from(chips).map((c) => c.textContent).join(' | '));

      // Add-select offers only unused providers (preferred + chain used up
      // all four image_generates candidates → no add select on that card).
      const imgAdd = host.querySelector(
        '[data-slot="image_generates"][data-field="chain-add"]');
      record('chain: add-select hidden when every provider is in use',
             !imgAdd);
      const vidAdd = host.querySelector(
        '[data-slot="video_generates"][data-field="chain-add"]');
      const vidAddIds = vidAdd
        ? Array.from(vidAdd.options).map((o) => o.value).filter(Boolean) : [];
      record('chain: add-select offers unused providers only',
             vidAddIds.length === 1
             && vidAddIds[0] === 'openrouter:google/veo-3',
             vidAddIds.join(','));

      // 4. Advanced routing — always-visible section, no disclosure
      const adv = host.querySelector('.ora-vslots-advanced');
      record('advanced: always-visible section (no details disclosure)',
             !!adv && adv.tagName !== 'DETAILS'
             && adv.textContent.indexOf('Advanced routing') !== -1,
             adv && adv.tagName);
      const advRows = adv ? adv.querySelectorAll('.ora-vslots-row') : [];
      const advSlots = Array.from(advRows).map((r) => r.dataset.advRow);
      record('advanced: holds the remaining configured slots',
             advSlots.indexOf('image_edits') !== -1
             && advSlots.indexOf('image_critique') !== -1
             && advSlots.indexOf('style_trains') !== -1,
             advSlots.join(','));
      record('advanced: image_extracts (different shape) never renders',
             !host.querySelector('[data-slot="image_extracts"]'));

      // Capability summaries caption the rows
      const editsRow = adv.querySelector('[data-adv-row="image_edits"]');
      const editsHint = editsRow && editsRow.querySelector('.ora-vslots-row-hint');
      record('advanced: capability summary captions the row',
             !!editsHint
             && editsHint.textContent.indexOf('Modify a region') !== -1,
             editsHint && editsHint.textContent);

      // Empty slot reads "off"
      const critRow = adv.querySelector('[data-adv-row="image_critique"]');
      record('advanced: empty slot marked off — no provider set',
             !!critRow
             && critRow.textContent.indexOf('off — no provider set') !== -1);

      // 5. Stored-but-unregistered provider still renders, tagged
      const ghostSel = host.querySelector(
        '[data-slot="style_trains"][data-field="preferred"]');
      const ghostOpt = ghostSel && Array.from(ghostSel.options)
        .find((o) => o.value === 'ghost-provider');
      record('staleness: missing provider kept + tagged "not in registry"',
             !!ghostOpt && ghostOpt.selected
             && ghostOpt.textContent.indexOf('not in registry') !== -1,
             ghostOpt && ghostOpt.textContent);

      // 7a. Provider notice — unusable preferred warns + offers the jump
      const vidCard = host.querySelector('[data-slot-card="video_generates"]');
      const vidNotice = vidCard.querySelector('.ora-vslots-notice--warn');
      record('notice: unusable preferred shows setup reason',
             !!vidNotice
             && vidNotice.textContent.indexOf('set Replicate token') !== -1,
             vidNotice && vidNotice.textContent);
      const apiBtn = vidNotice && vidNotice.querySelector('[data-action="open-apis"]');
      record('notice: API-key problems offer the External-APIs jump', !!apiBtn);
      let openSettingsDetail = null;
      const onOpenSettings = (e) => { openSettingsDetail = e.detail; };
      win.document.addEventListener('open-settings', onOpenSettings);
      apiBtn.click();
      win.document.removeEventListener('open-settings', onOpenSettings);
      record('notice: jump dispatches open-settings with the reason',
             !!openSettingsDetail
             && String(openSettingsDetail.message).indexOf('Replicate') !== -1,
             JSON.stringify(openSettingsDetail));

      // 6. Preferred change → per-slot POST, value dropped from chain
      prefSel.value = 'openrouter:openai/gpt-5-image';
      prefSel.dispatchEvent(new win.Event('change'));
      await tick(); await tick();
      const patch1 = posts[posts.length - 1].slots.image_generates;
      record('save: preferred change POSTs per-slot patch',
             posts.length === 1
             && patch1.preferred === 'openrouter:openai/gpt-5-image',
             JSON.stringify(patch1));
      record('save: new preferred dropped from fallback chain',
             JSON.stringify(patch1.fallback) === JSON.stringify([
               'openrouter:google/gemini-3.1-flash-image-preview',
               'local-diffusers',
             ]),
             JSON.stringify(patch1.fallback));
      record('save: patch never carries underscore annotations',
             Object.keys(patch1).every((k) => k[0] !== '_'),
             Object.keys(patch1).join(','));

      // 7b. Available-but-noteworthy provider → info note (no warning)
      const vidPref = host.querySelector(
        '[data-slot="video_generates"][data-field="preferred"]');
      vidPref.value = 'openrouter:google/veo-3';
      vidPref.dispatchEvent(new win.Event('change'));
      await tick(); await tick();
      const vidCard2 = host.querySelector('[data-slot-card="video_generates"]');
      const infoNotice = vidCard2.querySelector('.ora-vslots-notice');
      record('notice: available provider with a note renders info, not warning',
             !!infoNotice
             && infoNotice.textContent.indexOf('Async') !== -1
             && !infoNotice.classList.contains('ora-vslots-notice--warn'));

      // 3b. Chain remove — × on the first image_generates chip
      const removeBtn = host.querySelector(
        '[data-slot-card="image_generates"] '
        + '[data-action="chain-remove"][data-index="0"]');
      removeBtn.click();
      await tick(); await tick();
      const patchAfterRemove = posts[posts.length - 1].slots.image_generates;
      record('chain: removing a chip POSTs the shortened chain',
             JSON.stringify(patchAfterRemove.fallback)
               === JSON.stringify(['local-diffusers']),
             JSON.stringify(patchAfterRemove.fallback));

      // 3c. Chain add — append via the add-select
      const addSel = host.querySelector(
        '[data-slot="image_generates"][data-field="chain-add"]');
      addSel.value = 'openrouter:google/gemini-3.1-flash-image-preview';
      addSel.dispatchEvent(new win.Event('change'));
      await tick(); await tick();
      const patchAfterAdd = posts[posts.length - 1].slots.image_generates;
      record('chain: add-select appends to the end of the chain',
             JSON.stringify(patchAfterAdd.fallback) === JSON.stringify([
               'local-diffusers',
               'openrouter:google/gemini-3.1-flash-image-preview',
             ]),
             JSON.stringify(patchAfterAdd.fallback));

      // 4b. Advanced section survives an edit re-render with rows intact
      const editsSel = host.querySelector(
        '[data-slot="image_edits"][data-field="preferred"]');
      editsSel.value = 'replicate';
      editsSel.dispatchEvent(new win.Event('change'));
      await tick(); await tick();
      const adv3 = host.querySelector('.ora-vslots-advanced');
      record('advanced: section intact after an edit re-render',
             !!adv3 && adv3.querySelectorAll('.ora-vslots-row').length >= 3,
             adv3 && String(adv3.querySelectorAll('.ora-vslots-row').length));

      // Status line reflects the save
      const status = host.querySelector('[data-role="status"]');
      record('status: shows Saved ✓ after a successful save',
             !!status && status.textContent.indexOf('Saved') !== -1,
             status && status.textContent);

      P.destroy();
      host.remove();
    } finally {
      win.fetch = savedFetch;
    }
  },
};
