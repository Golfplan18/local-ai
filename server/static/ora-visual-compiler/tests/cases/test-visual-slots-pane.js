/**
 * tests/cases/test-visual-slots-pane.js — V3 Visual tab pane suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Covers server/static/visual-slots-pane.js, the install-Chunk-11
 * replacement for the classic ConfigPanel embed on the Settings →
 * Visual tab:
 *   1. Primary cards render for image_generates + video_generates only.
 *   2. Preferred select carries the stored value; dead DALL-E padding
 *      entries are filtered out of the candidates.
 *   3. First-fallback select + read-only "Then:" chain line render the
 *      stored fallback chain.
 *   4. Advanced disclosure is collapsed by default and holds the
 *      remaining slots; image_extracts (different shape) never renders.
 *   5. A stored provider missing from the registry still renders,
 *      tagged "not in registry".
 *   6. Changing preferred POSTs a per-slot patch with the new value and
 *      drops it from the fallback chain.
 *   7. Clearing the first fallback shifts the rest of the chain up.
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
      display_name: 'GPT-5.4 Image 2  ($1/$2/M)', available: true },
    { provider_id: 'openrouter:google/gemini-3.1-flash-image-preview',
      display_name: 'Gemini 3.1 Flash Image', available: true },
    { provider_id: 'openrouter:openai/gpt-5-image',
      display_name: 'GPT-5 Image', available: true },
    { provider_id: 'local-diffusers', available: false,
      reason: 'install diffusers + torch', kind: 'local' },
    { provider_id: 'openai-dalle3', available: false, reason: 'x', kind: 'api' },
    { provider_id: 'openai-dalle2', available: false, reason: 'x', kind: 'api' },
  ],
  video_generates: [
    { provider_id: 'replicate', available: true },
    { provider_id: 'openrouter:google/veo-3', display_name: 'Veo 3', available: true },
  ],
  image_edits: [
    { provider_id: 'local-diffusers', available: true },
    { provider_id: 'replicate', available: true },
  ],
  image_critique: [{ provider_id: 'replicate', available: false, reason: '' }],
  style_trains: [{ provider_id: 'replicate', available: true }],
};

module.exports = {
  label: 'Visual slots pane (Settings → Visual capability routing)',

  run: async function (ctx, record) {
    const win = ctx.win;
    const tick = () => new Promise((r) => setTimeout(r, 0));

    // Fetch mock — GET slots, GET providers, POST patch recorder.
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

      // 2. Preferred select — stored value selected, DALL-E filtered
      const prefSel = host.querySelector(
        '[data-slot="image_generates"][data-field="preferred"]');
      record('preferred: stored value selected',
             !!prefSel && prefSel.value === 'openrouter:openai/gpt-5.4-image-2',
             prefSel && prefSel.value);
      const prefIds = prefSel
        ? Array.from(prefSel.options).map((o) => o.value) : [];
      record('preferred: dead DALL-E entries filtered out',
             prefIds.indexOf('openai-dalle3') === -1
             && prefIds.indexOf('openai-dalle2') === -1,
             prefIds.join(','));

      // 3. Fallback select + chain line
      const fbSel = host.querySelector(
        '[data-slot="image_generates"][data-field="fallback0"]');
      record('fallback: first chain entry selected',
             !!fbSel && fbSel.value === 'openrouter:google/gemini-3.1-flash-image-preview',
             fbSel && fbSel.value);
      const chain = host.querySelector(
        '[data-slot-card="image_generates"] .ora-vslots-chain');
      record('fallback: "Then:" line shows rest of chain',
             !!chain
             && chain.textContent.indexOf('GPT-5 Image') !== -1
             && chain.textContent.indexOf('local-diffusers') !== -1,
             chain && chain.textContent);

      // 4. Advanced disclosure
      const adv = host.querySelector('details.ora-vslots-advanced');
      record('advanced: disclosure present and collapsed',
             !!adv && !adv.open);
      const advRows = adv ? adv.querySelectorAll('.ora-vslots-row') : [];
      const advSlots = Array.from(advRows).map(
        (r) => r.querySelector('select').dataset.slot);
      record('advanced: holds the remaining configured slots',
             advSlots.indexOf('image_edits') !== -1
             && advSlots.indexOf('image_critique') !== -1
             && advSlots.indexOf('style_trains') !== -1,
             advSlots.join(','));
      record('advanced: image_extracts (different shape) never renders',
             !host.querySelector('[data-slot="image_extracts"]'));

      // 5. Stored-but-unregistered provider still renders, tagged
      const ghostSel = host.querySelector(
        '[data-slot="style_trains"][data-field="preferred"]');
      const ghostOpt = ghostSel && Array.from(ghostSel.options)
        .find((o) => o.value === 'ghost-provider');
      record('staleness: missing provider kept + tagged "not in registry"',
             !!ghostOpt && ghostOpt.selected
             && ghostOpt.textContent.indexOf('not in registry') !== -1,
             ghostOpt && ghostOpt.textContent);

      // 6. Preferred change → per-slot POST, value dropped from chain
      prefSel.value = 'openrouter:openai/gpt-5-image';
      prefSel.dispatchEvent(new win.Event('change'));
      await tick(); await tick();
      const post1 = posts[posts.length - 1];
      const patch1 = post1 && post1.slots && post1.slots.image_generates;
      record('save: preferred change POSTs per-slot patch',
             posts.length === 1 && !!patch1
             && patch1.preferred === 'openrouter:openai/gpt-5-image',
             JSON.stringify(post1));
      record('save: new preferred dropped from fallback chain',
             !!patch1 && JSON.stringify(patch1.fallback) === JSON.stringify([
               'openrouter:google/gemini-3.1-flash-image-preview',
               'local-diffusers',
             ]),
             patch1 && JSON.stringify(patch1.fallback));
      record('save: patch never carries underscore annotations',
             !!patch1 && Object.keys(patch1).every((k) => k[0] !== '_'),
             patch1 && Object.keys(patch1).join(','));

      // 7. Clearing fallback0 shifts the rest of the chain up
      const fbSel2 = host.querySelector(
        '[data-slot="image_generates"][data-field="fallback0"]');
      fbSel2.value = '';
      fbSel2.dispatchEvent(new win.Event('change'));
      await tick(); await tick();
      const patch2 = posts[posts.length - 1].slots.image_generates;
      record('fallback: clearing first entry shifts chain up',
             posts.length === 2
             && JSON.stringify(patch2.fallback) === JSON.stringify(['local-diffusers']),
             JSON.stringify(patch2.fallback));

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
