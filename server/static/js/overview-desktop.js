/* Overview Desktop renderer and scoped action entrances. */
(function () {
  'use strict';

  var order = ['project-priority', 'oversight', 'triggers', 'daily-note'];
  var sourceStates = new Set(['ready', 'empty', 'partial', 'missing', 'unavailable']);
  var launcher = document.getElementById('overviewDesktopOpen');
  var mount = document.getElementById('overviewDesktop');
  if (!launcher || !mount) return;

  var host = document.getElementById('overviewDesktopSources');
  var status = document.getElementById('overviewDesktopStatus');
  var closeButton = mount.querySelector('[data-overview-close]');
  var workspace = document.querySelector('.ora-shell');
  var priorFocus = null;
  var workspaceWasInert = false;
  var requestId = 0;
  var readController = null;
  var readView = null;
  var readButton = null;
  var reader = element('section', 'overview-desktop__reader');
  reader.hidden = true;
  reader.id = 'overviewDailyNoteReader';
  var backButton = element('button', 'overview-source__action', 'Back to Overview');
  backButton.type = 'button';
  backButton.dataset.overviewBack = '';
  var readerHost = element('div', 'overview-desktop__document');
  readerHost.id = 'overviewDailyNoteDocument';
  reader.append(backButton, readerHost);
  host.after(reader);

  function resetReader(restoreFocus) {
    if (readController) readController.abort();
    readController = null;
    if (readView) readView.destroy();
    readView = null;
    readerHost.replaceChildren();
    reader.hidden = true;
    host.hidden = false;
    if (readButton && readButton.isConnected) {
      readButton.disabled = false;
      readButton.textContent = 'Read in Ora';
      if (restoreFocus) readButton.focus();
    }
    readButton = null;
  }

  backButton.addEventListener('click', function () {
    resetReader(true);
    status.textContent = 'Four sources checked.';
  });

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function sourceState(value) {
    return sourceStates.has(value) ? value : 'unavailable';
  }

  function itemState(value) {
    return typeof value === 'string' && value.trim() ? value.trim() : 'unknown';
  }

  function addProjectAction(row, item) {
    var actions = Array.isArray(item.actions) ? item.actions : [];
    var scope = item.scope && typeof item.scope === 'object' ? item.scope : {};
    var nexus = typeof scope.project_nexus === 'string' ? scope.project_nexus.trim() : '';
    if (!actions.includes('open_project') || !nexus || !window.OraProjectModal
        || typeof window.OraProjectModal.open !== 'function') return;

    var button = element('button', 'overview-source__action', 'Open project');
    button.type = 'button';
    button.dataset.overviewAction = 'open_project';
    button.addEventListener('click', function () {
      close();
      window.OraProjectModal.open(nexus, item.title || nexus);
    });
    row.appendChild(button);
  }

  function addScheduledAction(row, item, sourceId) {
    var actions = Array.isArray(item.actions) ? item.actions : [];
    var itemId = typeof item.item_id === 'string' ? item.item_id : '';
    var prefix = 'trigger:';
    if (sourceId !== 'triggers' || !actions.includes('open_scheduled')
        || !itemId.startsWith(prefix) || itemId.length === prefix.length) return;

    var triggerId = itemId.slice(prefix.length);
    var button = element('button', 'overview-source__action', 'Open in Scheduled');
    button.type = 'button';
    button.dataset.overviewAction = 'open_scheduled';
    button.addEventListener('click', function () {
      close();
      document.dispatchEvent(new CustomEvent('ora:scheduled-trigger-open-requested', {
        detail: { trigger_id: triggerId },
      }));
    });
    row.appendChild(button);
  }

  function addDailyNoteAction(row, item, sourceId) {
    var actions = Array.isArray(item.actions) ? item.actions : [];
    var itemId = typeof item.item_id === 'string' ? item.item_id : '';
    if (sourceId !== 'daily-note' || itemState(item.state) !== 'available'
        || !actions.includes('open_note')
        || !/^daily-note:\d{4}-\d{2}-\d{2}$/.test(itemId)) return;

    var button = element('button', 'overview-source__action', 'Open externally');
    button.type = 'button';
    button.dataset.overviewAction = 'open_note';
    button.addEventListener('click', async function () {
      if (button.disabled) return;
      var activeRequest = requestId;
      var buttonHadFocus = document.activeElement === button;
      button.disabled = true;
      button.textContent = 'Opening…';
      status.hidden = false;
      status.textContent = 'Sending the Daily Note open request…';
      try {
        var response = await window.fetch('/api/overview/daily-note/open', {
          method: 'POST',
          headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: itemId }),
        });
        var payload;
        try {
          payload = await response.json();
        } catch (_error) {
          payload = null;
        }
        if (activeRequest !== requestId || mount.hidden) return;

        var message = payload && typeof payload.message === 'string'
          ? payload.message.trim() : '';
        var acceptedOutcome = payload && (
          (payload.outcome === 'sent' && payload.application === 'obsidian')
          || (payload.outcome === 'fallback_sent'
              && payload.application === 'default_markdown')
        );
        if (response.ok && payload && payload.ok === true
            && payload.identity === itemId && acceptedOutcome && message) {
          close(message);
          return;
        }
        if (payload && payload.ok === true) {
          message = 'Ora returned an invalid Daily Note open response.';
        } else if (!message && payload && typeof payload.error === 'string') {
          message = payload.error.trim();
        }
        status.textContent = message || (
          'The Daily Note could not be opened. Request failed with status '
          + response.status + '.'
        );
      } catch (error) {
        if (activeRequest !== requestId || mount.hidden) return;
        status.textContent = 'The Daily Note open request could not reach Ora.';
      } finally {
        if (activeRequest === requestId && !mount.hidden && button.isConnected) {
          button.disabled = false;
          button.textContent = 'Open externally';
          var currentFocus = document.activeElement;
          if (buttonHadFocus && (!currentFocus || currentFocus === document.body
              || currentFocus === button)) button.focus();
        }
      }
    });
    row.appendChild(button);
  }

  function addDailyNoteReadAction(row, item, sourceId) {
    var actions = Array.isArray(item.actions) ? item.actions : [];
    var itemId = typeof item.item_id === 'string' ? item.item_id : '';
    if (sourceId !== 'daily-note' || itemState(item.state) !== 'available'
        || !actions.includes('read_note')
        || !/^daily-note:\d{4}-\d{2}-\d{2}$/.test(itemId)) return;

    var button = element('button', 'overview-source__action', 'Read in Ora');
    button.type = 'button';
    button.dataset.overviewAction = 'read_note';
    button.addEventListener('click', async function () {
      if (button.disabled) return;
      resetReader(false);
      var controller = new AbortController();
      readController = controller;
      readButton = button;
      var activeRequest = requestId;
      var buttonHadFocus = document.activeElement === button;
      function current() {
        return activeRequest === requestId && !mount.hidden && readController === controller;
      }
      button.disabled = true;
      button.textContent = 'Reading…';
      status.hidden = false;
      status.textContent = 'Loading the Daily Note…';
      try {
        var response = await window.fetch('/api/overview/daily-note/read?id=' + encodeURIComponent(itemId), {
          method: 'GET', headers: { Accept: 'application/json' }, signal: controller.signal,
        });
        var payload;
        try { payload = await response.json(); } catch (_error) { payload = null; }
        if (!current()) return;
        if (!response.ok) {
          status.textContent = payload && typeof payload.error === 'string' && payload.error.trim()
            ? payload.error : 'The Daily Note could not be read. Request failed with status ' + response.status + '.';
          return;
        }
        if (!payload || payload.id !== itemId || payload.source !== 'daily-note'
            || typeof payload.text !== 'string') {
          status.textContent = 'Ora returned an invalid Daily Note read response.';
          return;
        }
        try {
          readView = window.OraDocumentSurface.renderRead({
            host: readerHost, markdown: payload.text, ariaLabel: 'Daily Note ' + itemId.slice(11),
          });
          if (!readView || readView.mode !== 'read' || typeof readView.destroy !== 'function') {
            throw new Error('Document surface unavailable');
          }
        } catch (_error) {
          readView = null;
          readerHost.replaceChildren(
            element('p', '', 'Formatted Read is unavailable. Showing the original Markdown.'),
            element('pre', 'overview-desktop__literal', payload.text)
          );
        }
        host.hidden = true;
        reader.hidden = false;
        status.textContent = 'Reading Daily Note ' + itemId.slice(11) + '.';
        backButton.focus();
      } catch (_error) {
        if (current()) status.textContent = 'The Daily Note read request could not reach Ora.';
      } finally {
        if (current()) {
          readController = null;
          button.disabled = false;
          button.textContent = 'Read in Ora';
          var focus = document.activeElement;
          if (reader.hidden && buttonHadFocus && (!focus || focus === document.body || focus === button)) {
            button.focus();
          }
        }
      }
    });
    row.appendChild(button);
  }

  function renderItem(item, sourceId) {
    var row = element('li', 'overview-source__item');
    row.dataset.state = itemState(item.state);
    row.appendChild(element('strong', '', item.title || 'Untitled'));
    if (item.text) row.appendChild(element('p', '', item.text));

    var details = [];
    if (item.state) details.push(itemState(item.state));
    if (item.time) details.push(item.time);
    if (Number.isFinite(item.count)) details.push(item.count + ' total');
    if (details.length) row.appendChild(element('small', '', details.join(' · ')));
    addProjectAction(row, item);
    addScheduledAction(row, item, sourceId);
    addDailyNoteReadAction(row, item, sourceId);
    addDailyNoteAction(row, item, sourceId);
    return row;
  }

  function renderSource(source) {
    var state = sourceState(source.state);
    var card = element('section', 'overview-source');
    card.dataset.sourceId = source.source_id;
    card.dataset.state = state;

    var heading = element('div', 'overview-source__heading');
    heading.appendChild(element('h2', '', source.title || source.source_id));
    heading.appendChild(element('span', 'overview-source__state', state));
    card.appendChild(heading);

    var count = Number.isFinite(source.count) ? source.count : 0;
    var freshness = source.freshness && typeof source.freshness === 'object'
      ? source.freshness : {};
    var meta = [count + ' item' + (count === 1 ? '' : 's')];
    if (freshness.observed_at) meta.push('Checked ' + freshness.observed_at);
    if (freshness.last_success_at) meta.push('Last success ' + freshness.last_success_at);
    card.appendChild(element('p', 'overview-source__meta', meta.join(' · ')));

    if (source.error && source.error.message) {
      card.appendChild(element('p', 'overview-source__error', source.error.message));
    }
    var items = Array.isArray(source.items) ? source.items : [];
    if (items.length) {
      var list = element('ol', 'overview-source__items');
      items.forEach(function (item) {
        list.appendChild(renderItem(item, source.source_id));
      });
      card.appendChild(list);
    } else {
      card.appendChild(element(
        'p', 'overview-source__empty',
        state === 'unavailable' ? 'This source is unavailable.' : 'No items.'
      ));
    }
    return card;
  }

  function render(sources) {
    var byId = new Map();
    sources.forEach(function (source) { byId.set(source.source_id, source); });
    var ordered = order.map(function (id) { return byId.get(id); }).filter(Boolean);
    if (ordered.length !== order.length) throw new Error('Ora returned incomplete Overview sources.');
    host.replaceChildren();
    ordered.forEach(function (source) { host.appendChild(renderSource(source)); });
  }

  async function load() {
    var activeRequest = ++requestId;
    host.replaceChildren();
    status.textContent = 'Loading four Overview sources…';
    try {
      var response = await window.fetch('/api/overview', {
        method: 'GET', headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error('Request failed with status ' + response.status + '.');
      var payload = await response.json();
      if (!payload || !Array.isArray(payload.sources)) {
        throw new Error('Ora returned an invalid Overview response.');
      }
      if (activeRequest !== requestId || mount.hidden) return;
      render(payload.sources);
      status.textContent = 'Four sources checked.';
    } catch (error) {
      if (activeRequest !== requestId || mount.hidden) return;
      host.replaceChildren();
      status.textContent = 'Overview could not be loaded. '
        + (error && error.message ? error.message : String(error));
    }
  }

  function open() {
    if (!mount.hidden) return;
    priorFocus = document.activeElement;
    workspaceWasInert = Boolean(workspace && workspace.hasAttribute('inert'));
    if (workspace) workspace.setAttribute('inert', '');
    mount.hidden = false;
    status.hidden = false;
    launcher.setAttribute('aria-expanded', 'true');
    document.body.classList.add('overview-desktop-open');
    closeButton.focus();
    load();
  }

  function close(finalStatus) {
    if (mount.hidden) return;
    requestId += 1;
    resetReader(false);
    var hasFinalStatus = typeof finalStatus === 'string' && finalStatus.trim();
    status.textContent = hasFinalStatus ? finalStatus.trim() : 'Overview closed.';
    status.hidden = !hasFinalStatus;
    mount.hidden = true;
    launcher.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('overview-desktop-open');
    if (workspace && !workspaceWasInert) workspace.removeAttribute('inert');
    if (priorFocus && priorFocus.isConnected) priorFocus.focus();
  }

  launcher.addEventListener('click', open);
  closeButton.addEventListener('click', close);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !mount.hidden) close();
  });
})();
