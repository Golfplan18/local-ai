/**
 * tests/cases/test-sidebar-triggers.js — V3 sidebar "Scheduled" suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Covers the Trigger half of server/static/js/sidebar-oversight.js — the only
 * screen that says what is scheduled, what fired, and what failed:
 *   1. One card per Trigger, with cause and status badges.
 *   2. The count badge counts what is ARMED, not what merely exists.
 *   3. Deadlines Ora arms for itself are counted, never listed.
 *   4. A dead firing lane is surfaced in the list, not hidden in a detail.
 *   5. …and is not surfaced when nothing is armed to be let down.
 *   6. A draft offers review-then-activate; the review shows the exact digest.
 *   7. Approving posts that exact digest — a name is not an approval.
 *   8. Run now posts to the manual-firing route.
 *   9. A failed firing shows as failed, with its error legible.
 *  10. The form builds a calendar spec carrying its named zone and reason.
 *  11. The form names the watch roots a file selector must sit inside.
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const TOOL_ACTION = { kind: 'project_tool', nexus: 'msi', tool: 'deploy-check', args: [] };

const TRIGGERS = [
  {
    spec: {
      trigger_id: 'nightly-export', name: 'Nightly export', cause: 'calendar',
      condition: { schedule: {
        timezone: 'America/New_York', local_time: '07:30', cadence: 'daily',
        weekdays: [], start_date: '2026-08-01', missed_policy: 'run_once',
        grace_seconds: 300,
      } },
      action: TOOL_ACTION,
      runtime_justification: 'The upstream feed publishes on its own clock.',
    },
    spec_digest: 'sha256:aaa', status: 'active',
    next_due_at: '2026-08-20T11:30:00+00:00',
    intermittency: 'Acts only while Ora is running.',
    firings: [{ event_id: 'evt-1', cause: 'calendar', status: 'completed',
                outcome: 'ran', claimed_at: '2026-08-19T11:30:00+00:00',
                finished_at: '2026-08-19T11:30:04+00:00' }],
  },
  {
    spec: {
      trigger_id: 'on-brief', name: 'Index the brief', cause: 'file_change',
      condition: { path_selectors: ['/Users/x/Documents/vault/Brief.md'] },
      action: TOOL_ACTION,
    },
    spec_digest: 'sha256:bbb', status: 'draft', intermittency: '',
    firings: [{ event_id: 'evt-2', cause: 'manual', status: 'failed',
                outcome: 'failed', claimed_at: '2026-08-19T09:00:00+00:00',
                finished_at: '2026-08-19T09:00:01+00:00',
                error: 'TriggerConflict: action_definition_drifted' }],
  },
];

const ACTIONS = {
  project_tools: [{ nexus: 'msi', tool: 'deploy-check', description: 'Check the deploy',
                    interface: 'argv-stdout-json' }],
  frameworks: ['deep-research-protocol'],
  channel_actions: [{ kind: 'email_send', provider: 'fastmail',
                      description: 'Send one exact approved email' }],
  watch_roots: ['/Users/x/Documents/vault', '/Users/x/Documents/Ora Resources'],
  intermittency: 'Acts only while Ora is running.',
};

const PERSONAS = {
  personas: [
    { id: 'ora', display_name: 'Ora', description: 'Packaged Persona' },
    { id: 'global-writer', display_name: 'Global Writer', description: 'Global choice' },
    { id: 'project-writer', display_name: 'Project Writer', description: 'Project choice' },
  ],
  errors: [],
  selected: { id: 'project-writer', display_name: 'Project Writer',
              source: 'project', warnings: [] },
};

function sidebarMarkup() {
  return `
  <aside class="left-sidebar"><div class="sidebar-accordion">
    <div class="sidebar-supergroup" data-super="conversations">
      <button class="sidebar-supergroup-header" data-super-toggle="conversations">
        <span class="sidebar-supergroup-arrow">&#9656;</span></button>
      <div class="sidebar-supergroup-body"></div>
    </div>
    <div class="sidebar-supergroup" data-super="processes">
      <button class="sidebar-supergroup-header" data-super-toggle="processes">
        <span class="sidebar-supergroup-arrow">&#9656;</span>
        <span class="sidebar-supergroup-count" id="sidebarProcessesCount">0</span>
      </button>
      <div class="sidebar-supergroup-body"><div class="sidebar-groups">
        <div class="sidebar-group" data-group="paused">
          <span class="sidebar-group-count" id="sidebarPausedCount">0</span>
          <div class="oversight-list" id="oversightPausedList"></div>
        </div>
        <div class="sidebar-group" data-group="operating">
          <span class="sidebar-group-count" id="sidebarOperatingCount">0</span>
          <div class="oversight-list" id="oversightOperatingList"></div>
        </div>
        <div class="sidebar-group" data-group="scheduled">
          <span class="sidebar-group-count" id="sidebarScheduledCount">0</span>
          <button id="triggerNewButton" type="button">+</button>
          <div class="oversight-lane-warning" id="triggerLaneWarning" hidden></div>
          <div class="oversight-list" id="triggerList"></div>
          <div class="oversight-footnote" id="triggerInternalNote"></div>
        </div>
      </div></div>
    </div>
  </div></aside>`;
}

module.exports = {
  label: 'V3 sidebar Scheduled panel (Triggers)',

  run: async function (ctx, record) {
    const win = ctx.win;
    const doc = win.document;
    const tick = () => new Promise((r) => setTimeout(r, 0));

    const posts = [];
    const jsonResponse = (obj, ok) =>
      Promise.resolve({ ok: ok !== false, json: () => Promise.resolve(obj) });

    let laneHealth = { available: true, running: true, deadline_lane: false,
                       event_lane: true, deadline_lane_restarts: 0,
                       event_lane_restarts: 0 };
    let triggers = JSON.parse(JSON.stringify(TRIGGERS));

    const savedFetch  = win.fetch;
    const savedBody   = doc.body.innerHTML;
    const savedSetInt = win.setInterval;
    const savedAlert  = win.alert;

    // The module installs a 12s poll on load. Neutralise the scheduler for
    // the duration of the suite so it cannot outlive this case.
    win.setInterval = () => 0;
    win.alert = () => {};

    win.fetch = function (url, opts) {
      if (opts && opts.method === 'POST') {
        posts.push({ url, body: JSON.parse(opts.body || '{}') });
        return jsonResponse({ ok: true });
      }
      if (url === '/api/oversight/paused')    return jsonResponse({ entries: [] });
      if (url === '/api/oversight/operating') return jsonResponse({ entries: [] });
      if (url === '/api/triggers') {
        return jsonResponse({
          triggers,
          internal_deadlines: { total: 2141, available: true,
                                by_event_type: { trace_retention: 2138,
                                                 daily_note: 2, log_retention: 1 } },
          lane_health: laneHealth,
        });
      }
      if (url === '/api/triggers/actions') return jsonResponse(ACTIONS);
      if (url === '/api/personas') return jsonResponse(PERSONAS);
      if (/\/api\/triggers\/[^/]+\/review$/.test(url)) {
        return jsonResponse({
          trigger_id: 'on-brief', name: 'Index the brief',
          spec_digest: 'sha256:bbb', cause: 'file_change',
          condition: TRIGGERS[1].spec.condition,
          will_run: 'project tool msi:deploy-check',
          action_binding: { command_digest: 'sha256:cmd' },
          runtime_justification: null, intermittency: '', status: 'draft',
        });
      }
      return Promise.reject(new Error('unexpected fetch: ' + url));
    };

    try {
      doc.body.innerHTML = sidebarMarkup();
      const modPath = path.join(__dirname, '..', '..', '..', 'js',
                                'sidebar-oversight.js');
      win.eval(fs.readFileSync(modPath, 'utf-8'));
      await tick(); await tick(); await tick();

      const list = doc.querySelector('#triggerList');

      // 1. One card per Trigger, badged by cause and status.
      const cards = list.querySelectorAll('.trigger-card');
      record('scheduled: one card per Trigger', cards.length === 2,
             'count=' + cards.length);
      const first = cards[0];
      record('scheduled: cause is stated in words, not a field name',
             first.textContent.includes('on a schedule'),
             first.textContent.slice(0, 120));
      record('scheduled: status badge carries the lifecycle state',
             !!first.querySelector('.trigger-status--active')
             && !!cards[1].querySelector('.trigger-status--draft'));
      record('scheduled: an armed Trigger shows its next occurrence',
             first.textContent.includes('next'));

      // 2. The count is what is armed, not what exists.
      record('scheduled: count badge counts active Triggers only',
             doc.querySelector('#sidebarScheduledCount').textContent === '1',
             doc.querySelector('#sidebarScheduledCount').textContent);

      // 3. Ora's own deadlines are counted, never listed.
      const note = doc.querySelector('#triggerInternalNote').textContent;
      record('scheduled: internal deadlines are summarised, not enumerated',
             note.includes('2,141') && note.includes('trace_retention')
             && list.querySelectorAll('.trigger-card').length === 2, note);

      // 4. A dead firing lane is visible in the list itself.
      const warning = doc.querySelector('#triggerLaneWarning');
      record('health: a stopped deadline lane is surfaced',
             !warning.hidden && /not running/.test(warning.textContent),
             warning.textContent);

      // 5. …and only when something is actually armed.
      triggers = [JSON.parse(JSON.stringify(TRIGGERS[1]))]; // draft only
      doc.querySelector('#triggerNewButton'); // no-op, keeps lint honest
      win.dispatchEvent(new win.Event('focus'));
      await win.fetch('/api/triggers'); // prime, then force a refresh
      doc.querySelector('.sidebar-supergroup[data-super="processes"] '
                        + '.sidebar-supergroup-header').click();
      await tick(); await tick();
      record('health: no warning when nothing is armed to be let down',
             doc.querySelector('#triggerLaneWarning').hidden,
             doc.querySelector('#triggerLaneWarning').textContent);

      // Restore both Triggers for the interaction assertions.
      triggers = JSON.parse(JSON.stringify(TRIGGERS));
      laneHealth = { ...laneHealth, deadline_lane: true };
      doc.querySelector('.sidebar-supergroup[data-super="processes"] '
                        + '.sidebar-supergroup-header').click();
      await tick(); await tick();

      // Every interaction re-renders the list, so cards must be re-queried
      // rather than held across a click.
      const cardFor = (id) => [...doc.querySelectorAll('.trigger-card')]
        .find(c => c.dataset.triggerId === id);

      // 9. A failed firing reads as failed.
      record('history: a failed firing is badged failed',
             !!cardFor('on-brief').querySelector('.trigger-outcome--failed'));

      // 6. Draft → review, showing the exact digest.
      cardFor('on-brief').click();
      await tick();
      const reviewBtn = [...doc.querySelectorAll('.oversight-detail-actions button')]
        .find(b => /Review and activate/.test(b.textContent));
      record('activation: a draft offers review before deployment', !!reviewBtn);
      record('activation: the drifted error is legible in the detail',
             cardFor('on-brief').textContent.includes('action_definition_drifted'),
             cardFor('on-brief').textContent.slice(0, 200));
      reviewBtn.click();
      await tick(); await tick();
      const reviewBox = doc.querySelector('.trigger-review');
      record('activation: the review shows what will run and its digest',
             !!reviewBox
             && reviewBox.textContent.includes('project tool msi:deploy-check')
             && reviewBox.textContent.includes('sha256:bbb'),
             reviewBox ? reviewBox.textContent.slice(0, 120) : 'no review box');

      // 7. Approving posts the exact digest.
      posts.length = 0;
      [...reviewBox.querySelectorAll('button')]
        .find(b => /Approve and activate/.test(b.textContent)).click();
      await tick(); await tick();
      const activation = posts.find(p => /\/activate$/.test(p.url));
      record('activation: approval carries the exact specification digest',
             !!activation && activation.body.spec_digest === 'sha256:bbb',
             JSON.stringify(activation));

      // 8. Run now posts a manual firing.
      posts.length = 0;
      cardFor('nightly-export').click();
      await tick();
      [...cardFor('nightly-export')
          .querySelectorAll('.oversight-detail-actions button')]
        .find(b => b.textContent === 'Run now').click();
      await tick(); await tick();
      record('manual: Run now posts to the firing route',
             posts.some(p => /\/api\/triggers\/nightly-export\/run$/.test(p.url)),
             JSON.stringify(posts.map(p => p.url)));

      // 10 + 11. The authoring form.
      const openForm = async () => {
        doc.querySelector('#triggerNewButton').click();
        await tick(); await tick(); await tick();
        const overlay = doc.querySelector('#triggerFormOverlay');
        return overlay && overlay.querySelector('.trigger-form');
      };
      let form = await openForm();
      record('form: opens with an action picker from the registry',
             !!form && form.querySelector('select[name="action"]')
                          .textContent.includes('msi:deploy-check'));
      record('form: names the roots a watched path must sit inside',
             form.textContent.includes('/Users/x/Documents/vault'));

      const setValue = (selector, value) => {
        const el = form.querySelector(selector);
        el.value = value;
        el.dispatchEvent(new win.Event('change'));
      };

      setValue('select[name="action"]', 'channel:email_send');
      const personaPicker = form.querySelector('select[name="email_persona"]');
      record('email form: Persona is a registry-backed picker with a global default',
             !!personaPicker && personaPicker.value === ''
             && [...personaPicker.options].map(o => o.value).join(',')
                === ',ora,global-writer,project-writer'
             && personaPicker.options[0].textContent.includes('global default'),
             personaPicker ? personaPicker.textContent : 'no Persona picker');
      form.querySelector('input[name="name"]').value = 'Default Persona email';
      form.querySelector('input[name="trigger_id"]').value = 'default-persona-email';
      form.querySelector('input[name="email_to"]').value = 'recipient@example.com';
      form.querySelector('input[name="email_from"]').value = 'sender@example.com';
      form.querySelector('input[name="email_subject"]').value = 'Default';
      form.querySelector('textarea[name="email_body"]').value = 'Exact body';
      posts.length = 0;
      form.dispatchEvent(new win.Event('submit', { cancelable: true }));
      await tick(); await tick(); await tick();
      const defaultPersonaPost = posts.find(p => p.url === '/api/triggers');
      record('email form: global default is posted as omission, never literal Ora',
             !!defaultPersonaPost
             && !Object.prototype.hasOwnProperty.call(
               defaultPersonaPost.body.action, 'persona_id'),
             JSON.stringify(defaultPersonaPost && defaultPersonaPost.body.action));

      form = await openForm();
      setValue('select[name="action"]', 'channel:email_send');
      setValue('select[name="email_persona"]', 'global-writer');
      form.querySelector('input[name="name"]').value = 'Chosen Persona email';
      form.querySelector('input[name="trigger_id"]').value = 'chosen-persona-email';
      form.querySelector('input[name="email_to"]').value = 'recipient@example.com';
      form.querySelector('input[name="email_from"]').value = 'sender@example.com';
      form.querySelector('input[name="email_subject"]').value = 'Chosen';
      form.querySelector('textarea[name="email_body"]').value = 'Exact body';
      posts.length = 0;
      form.dispatchEvent(new win.Event('submit', { cancelable: true }));
      await tick(); await tick(); await tick();
      const chosenPersonaPost = posts.find(p => p.url === '/api/triggers');
      record('email form: explicit Persona posts that exact valid id',
             !!chosenPersonaPost
             && chosenPersonaPost.body.action.persona_id === 'global-writer',
             JSON.stringify(chosenPersonaPost && chosenPersonaPost.body.action));

      form = await openForm();
      form.querySelector('input[name="name"]').value = 'Rotate credentials';
      form.querySelector('input[name="trigger_id"]').value = 'rotate-creds';
      setValue('select[name="cause"]', 'calendar');
      form.querySelector('input[name="local_time"]').value = '06:00';
      form.querySelector('input[name="timezone"]').value = 'Europe/Berlin';
      form.querySelector('textarea[name="runtime_justification"]').value =
        'The provider expires credentials on its own clock with no callback.';
      record('form: the reason field appears only for a scheduled Trigger',
             !form.querySelector('textarea[name="runtime_justification"]')
                  .closest('.trigger-form-field').hidden
             && form.querySelector('input[name="path_selectors"]')
                    .closest('.trigger-form-field').hidden);

      posts.length = 0;
      form.dispatchEvent(new win.Event('submit', { cancelable: true }));
      await tick(); await tick(); await tick();
      const created = posts.find(p => p.url === '/api/triggers');
      const schedule = created && created.body.condition.schedule;
      record('form: a scheduled Trigger posts its named zone and its reason',
             !!created && schedule.timezone === 'Europe/Berlin'
             && schedule.local_time === '06:00'
             && created.body.runtime_justification.startsWith('The provider expires'),
             JSON.stringify(created && created.body));
    } finally {
      win.fetch = savedFetch;
      win.setInterval = savedSetInt;
      win.alert = savedAlert;
      const overlay = doc.querySelector('#triggerFormOverlay');
      if (overlay) overlay.remove();
      doc.body.innerHTML = savedBody;
    }
  },
};
