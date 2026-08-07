/**
 * tests/cases/test-styles-pane-guided.js — guided values wizard suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Covers the guided-setup flow added to server/static/styles-pane.js
 * (Settings → Output Styles → user context):
 *   1. Flipping the user-context toggle ON with no mind.md opens the
 *      choice panel with Guided setup as the first (primary) action.
 *   2. guided-start fetches GET /api/mind/guided and renders step 1 with
 *      the recommended option preselected and a progress indicator.
 *   3. Picking another option selects it; Next/Back walk the steps and
 *      free-text values survive the re-render (captured into state).
 *   4. Finish POSTs {answers, free_text, confirm_overwrite:false}, then
 *      flips styles.use_custom_values via POST /api/settings.
 *   5. A 409 needs_confirm response renders the replace-confirm banner;
 *      "Replace it" re-POSTs with confirm_overwrite:true.
 *   6. Prior answers from the marker (GET answers) prefill the wizard.
 *   7. A guided mind.md's summary row carries the re-run link.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const QUESTIONS = [
  {
    id: 'lead', section: 'Communication Preferences',
    prompt: 'Where should the answer go?', help: 'Ordering.',
    options: [
      { id: 'lead_conclusions', label: 'Conclusions first', example: 'A.', prose: 'x' },
      { id: 'lead_context', label: 'Context first', example: 'B.', prose: 'y' },
    ],
  },
  {
    id: 'register', section: 'Intellectual Posture',
    prompt: 'Engagement register?', help: '',
    options: [
      { id: 'adaptive', label: 'Adapt per domain', example: 'A.', prose: 'x' },
      { id: 'peer', label: 'Peer everywhere', example: 'B.', prose: 'y' },
    ],
    free_text: { id: 'peer_domains', label: 'Peer domains', placeholder: '', multiline: false },
  },
  {
    id: 'principles', section: 'Standing Principles',
    prompt: 'Anything the AI should always or never do?', help: '',
    options: [],
    free_text: { id: 'principles', label: 'Your standing rules', placeholder: '', multiline: true },
  },
];

const REGISTRY = {
  profiles: [{
    id: 'plain', display_name: 'Plain', description: 'stock', custom: false,
    arrangement: 'a1', arrangement_label: 'a1', elaboration: 3,
    elaboration_label: 'balanced', demeanor: {}, devices: {}, glossary: {},
  }],
  custom: [],
  library: { axes: [], devices: [], schemas: [], craft: [], elaboration_scale: [] },
  settings: { default_id: 'plain', use_custom_values: false },
};

module.exports = {
  label: 'Styles pane — guided values wizard',

  run: async function (ctx, record) {
    const win = ctx.win;
    const tick = () => new Promise((r) => setTimeout(r, 0));

    // Mutable server state the fetch mock serves.
    let mindState = { exists: false, template_available: true };
    let guidedGet = {
      questions: QUESTIONS, answers: null, free_text: null,
      exists: false, is_default_template: false, is_guided: false,
    };
    let guidedPostResponses = [];   // queue of {status, body} for POST /api/mind/guided
    let projectPosts = 0;
    const guidedPosts = [];
    const settingsPosts = [];

    const jsonResponse = (obj, status) =>
      Promise.resolve({ status: status || 200, json: () => Promise.resolve(obj) });

    const savedFetch = win.fetch;
    win.fetch = function (url, opts) {
      const method = (opts && opts.method) || 'GET';
      if (url === '/api/styles/registry') return jsonResponse(JSON.parse(JSON.stringify(REGISTRY)));
      if (url === '/api/mind' && method === 'GET') return jsonResponse(JSON.parse(JSON.stringify(mindState)));
      if (url === '/api/mind/guided' && method === 'GET') return jsonResponse(JSON.parse(JSON.stringify(guidedGet)));
      if (url === '/api/mind/guided' && method === 'POST') {
        guidedPosts.push(JSON.parse(opts.body));
        const next = guidedPostResponses.shift()
          || { status: 200, body: { exists: true, is_guided: true, sections: ['S1', 'S2'] } };
        if (next.status === 200) {
          mindState = {
            exists: true, is_guided: true, is_default_template: false,
            sections: ['S1', 'S2'], content: '<!-- ora-mind-guided: {} -->',
            template_available: true, mtime: '2026-07-01T00:00:00',
          };
        }
        return jsonResponse(next.body, next.status);
      }
      if (url === '/api/personas') return jsonResponse({
        personas: [{ id: 'ora', display_name: 'Ora' }],
        selected: { id: 'ora', display_name: 'Ora', source: 'global', warnings: [] },
      });
      if (url === '/api/personas/compile' && method === 'POST') {
        projectPosts += 1;
        return jsonResponse({ ok: true, id: 'ora-personalized', active: false });
      }
      if (url === '/api/settings' && method === 'POST') {
        settingsPosts.push(JSON.parse(opts.body));
        return jsonResponse({ settings: {} });
      }
      return Promise.reject(new Error('unexpected fetch: ' + url + ' ' + method));
    };

    try {
      const modPath = path.join(__dirname, '..', '..', '..', 'styles-pane.js');
      win.eval(fs.readFileSync(modPath, 'utf-8'));

      const P = win.OraStylesPane;
      record('pane: module exposed on window', !!P && typeof P.init === 'function');
      if (!P) return;

      const host = win.document.createElement('div');
      win.document.body.appendChild(host);
      P.init(host);
      await tick(); await tick();

      // 1. Toggle ON with no mind.md → choice panel, guided first.
      const toggle = host.querySelector('input[data-toggle="use_custom_values"]');
      record('toggle: renders', !!toggle);
      toggle.checked = true;
      toggle.dispatchEvent(new win.Event('change', { bubbles: true }));
      await tick();
      const choiceBtns = host.querySelectorAll('.ora-styles-mind--choice .ora-styles-btn');
      record('choice: panel opens without committing the toggle',
             !!host.querySelector('.ora-styles-mind--choice')
             && settingsPosts.length === 0);
      record('choice: guided setup is the first, primary action',
             choiceBtns.length > 0
             && choiceBtns[0].dataset.action === 'guided-start'
             && choiceBtns[0].className.indexOf('ora-styles-btn--primary') !== -1);

      // 2. Start the wizard.
      choiceBtns[0].click();
      await tick(); await tick();
      const wiz = host.querySelector('.ora-styles-guided');
      record('wizard: renders after guided-start', !!wiz);
      record('wizard: progress shows 1 of 3',
             wiz && wiz.textContent.indexOf('1 of 3') !== -1);
      const preselected = host.querySelector('.ora-styles-gopt-on .ora-styles-gopt-label');
      record('wizard: recommended option preselected',
             !!preselected && preselected.textContent === 'Conclusions first');

      // 3. Pick the other option; walk forward; free text survives.
      const opts1 = host.querySelectorAll('[data-action="guided-pick"]');
      opts1[1].click();
      await tick();
      record('wizard: picking selects the option',
             host.querySelector('.ora-styles-gopt-on .ora-styles-gopt-label')
               .textContent === 'Context first');
      host.querySelector('[data-action="guided-next"]').click();
      await tick();
      record('wizard: step 2 renders its free-text input',
             !!host.querySelector('input[data-role="guided-free"][data-ft="peer_domains"]'));
      host.querySelector('[data-role="guided-free"]').value = 'baking';
      host.querySelector('[data-action="guided-next"]').click();
      await tick();
      record('wizard: free-text-only closing step renders a textarea + Finish',
             !!host.querySelector('textarea[data-role="guided-free"][data-ft="principles"]')
             && !!host.querySelector('[data-action="guided-finish"]'));
      host.querySelector('[data-action="guided-back"]').click();
      await tick();
      record('wizard: free text survives Back re-render',
             host.querySelector('[data-role="guided-free"]').value === 'baking');
      host.querySelector('[data-action="guided-next"]').click();
      await tick();
      host.querySelector('textarea[data-role="guided-free"]').value = 'Never use emoji.';

      // 4. Finish → POST answers, then flip the toggle.
      host.querySelector('[data-action="guided-finish"]').click();
      await tick(); await tick(); await tick(); await tick();
      record('finish: POST carries answers + free text, no confirm flag',
             guidedPosts.length === 1
             && guidedPosts[0].answers.lead === 'lead_context'
             && guidedPosts[0].answers.register === 'adaptive'
             && guidedPosts[0].free_text.peer_domains === 'baking'
             && guidedPosts[0].free_text.principles === 'Never use emoji.'
             && guidedPosts[0].confirm_overwrite === false);
      record('finish: flips styles.use_custom_values on',
             settingsPosts.length === 1
             && settingsPosts[0].updates.styles.use_custom_values === true);
      record('finish: wizard closes', !host.querySelector('.ora-styles-guided'));

      // 7. Guided summary row carries the re-run link (mind exists + toggle
      // is still reported off by the registry mock, so force the panel via
      // a fresh init with settings on).
      REGISTRY.settings.use_custom_values = true;
      P.destroy();
      const host2 = win.document.createElement('div');
      win.document.body.appendChild(host2);
      P.init(host2);
      await tick(); await tick();
      const rerun = host2.querySelector('[data-action="guided-start"]');
      record('summary: guided file shows re-run guided setup link',
             !!rerun && rerun.textContent.indexOf('re-run guided setup') !== -1);

      // 6. Prefill: prior answers preselect.
      guidedGet = {
        questions: QUESTIONS,
        answers: { lead: 'lead_context', register: 'peer' },
        free_text: { peer_domains: 'baking' },
        exists: true, is_default_template: false, is_guided: true,
      };
      rerun.click();
      await tick(); await tick();
      record('prefill: prior answer preselected on step 1',
             host2.querySelector('.ora-styles-gopt-on .ora-styles-gopt-label')
               .textContent === 'Context first');

      // 5. 409 → confirm banner → Replace re-POSTs with confirm_overwrite.
      guidedPostResponses.push({
        status: 409, body: { error: 'hand edits', needs_confirm: true },
      });
      guidedPosts.length = 0;
      host2.querySelector('[data-action="guided-next"]').click();
      await tick();
      host2.querySelector('[data-action="guided-next"]').click();
      await tick();
      host2.querySelector('[data-action="guided-finish"]').click();
      await tick(); await tick(); await tick();
      record('409: confirm banner renders with Replace action',
             !!host2.querySelector('.ora-styles-gconfirm')
             && !!host2.querySelector('[data-action="guided-confirm"]'));
      host2.querySelector('[data-action="guided-confirm"]').click();
      await tick(); await tick(); await tick(); await tick();
      record('409: Replace re-POSTs with confirm_overwrite true',
             guidedPosts.length === 2
             && guidedPosts[0].confirm_overwrite === false
             && guidedPosts[1].confirm_overwrite === true);
      record('409: wizard closes after confirmed write',
             !host2.querySelector('.ora-styles-guided'));

      // 8. Persona compilation: link appears when a self-spec archive exists;
      // clicking POSTs /api/personas/compile and leaves mind.md unchanged.
      mindState.self_spec_available = true;
      P.destroy();
      const host3 = win.document.createElement('div');
      win.document.body.appendChild(host3);
      P.init(host3);
      await tick(); await tick();
      const projLink = host3.querySelector('[data-action="mind-project"]');
      record('project: link offered when self-spec archive exists',
             !!projLink
             && projLink.textContent === 'create tailored Persona');
      projLink.click();
      await tick(); await tick(); await tick(); await tick();
      record('project: click POSTs /api/personas/compile once', projectPosts === 1);
      const projLink2 = host3.querySelector('[data-action="mind-project"]');
      record('project: link remains available because compilation does not rewrite mind.md',
             !!projLink2
             && projLink2.textContent === 'create tailored Persona');

      P.destroy();
      host.remove(); host2.remove(); host3.remove();
    } finally {
      win.fetch = savedFetch;
    }
  },
};
