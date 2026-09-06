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
  var projectScene = null;
  var sceneObserver = null;
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
    layoutProjects();
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

  var projectDestinations = [
    ['open_project', 'Overview', null],
    ['open_project_files', 'Files', 'files'],
    ['open_project_dialogues', 'Dialogues', 'dialogues'],
    ['open_project_knowledge', 'Knowledge', 'engrams'],
  ];

  function addProjectAction(row, item, allDestinations) {
    var actions = Array.isArray(item.actions) ? item.actions : [];
    var scope = item.scope && typeof item.scope === 'object' ? item.scope : {};
    var nexus = typeof scope.project_nexus === 'string' ? scope.project_nexus.trim() : '';
    var valid = /^[a-z0-9][a-z0-9_-]*$/.test(nexus)
      && !['commons', 'general'].includes(nexus) && item.item_id === 'project:' + nexus;
    var destinationList = allDestinations ? projectDestinations : projectDestinations.slice(0, 1);
    var actionHost = element('div', 'overview-project__actions');
    destinationList.forEach(function (destination) {
      var label = allDestinations ? destination[1] : 'Open project';
      var button = element('button', 'overview-source__action', label);
      button.type = 'button';
      button.dataset.overviewAction = destination[0];
      button.setAttribute('aria-label', label + ': ' + (item.title || nexus || 'Unknown project'));
      button.disabled = !valid || !actions.includes(destination[0]);
      if (button.disabled) button.title = 'This project destination is unavailable in the source record.';
      button.addEventListener('click', function () {
        var owner = destination[2] ? window.OraLibraryWorkspace : window.OraProjectModal;
        if (!owner || typeof owner.open !== 'function') {
          status.hidden = false;
          status.textContent = destination[1] + ' is unavailable. The destination could not be opened.';
          return;
        }
        close();
        if (destination[2]) owner.open({
          projectId: nexus, sources: [destination[2]], cleanBrowse: true, returnFocus: launcher,
        });
        else owner.open(nexus, item.title || nexus);
      });
      actionHost.appendChild(button);
    });
    row.appendChild(actionHost);
    if (!valid || destinationList.some(function (destination) { return !actions.includes(destination[0]); })) {
      row.appendChild(element('small', 'overview-source__error', 'Some project destinations are unavailable in this source record.'));
    }
  }

  function projectCount(source) {
    var state = sourceState(source.state);
    if (state === 'unavailable' || state === 'missing') return 'Project count unavailable';
    if (!Number.isInteger(source.count) || source.count < 0) return 'Project count unavailable';
    return source.count + (state === 'partial' ? ' known active projects · Partial inventory' : ' active project' + (source.count === 1 ? '' : 's'));
  }

  function renderProjects(source) {
    var scene = element('div', 'overview-projects');
    scene.dataset.state = sourceState(source.state);
    scene.setAttribute('role', 'region');
    scene.setAttribute('aria-label', 'Active projects in priority order');
    var heading = element('div', 'overview-projects__heading');
    heading.append(element('h2', '', 'Your projects'), element('p', '', projectCount(source)),
      element('small', '', 'Priority sets the order. Activity is shown without moving projects.'));
    scene.appendChild(heading);
    var canvas = element('div', 'overview-projects__canvas');
    var identity = document.getElementById('overviewDesktopIdentity');
    if (identity) canvas.appendChild(identity.content.cloneNode(true));
    var list = element('ol', 'overview-projects__ring');
    var items = Array.isArray(source.items) ? source.items : [];
    items.forEach(function (value, index) {
      var item = value && typeof value === 'object' ? value : {};
      var project = element('li', 'overview-project');
      project.dataset.projectId = item.scope && item.scope.project_nexus || '';
      project.dataset.slot = String(index);
      project.dataset.state = itemState(item.state);
      var title = element('h3', '', item.title || 'Unknown project');
      title.title = item.title || 'Unknown project';
      project.append(element('small', 'overview-project__position', 'Position ' + (index + 1)), title,
        element('p', '', item.text || itemState(item.state)),
        element('small', 'overview-project__activity', item.time ? 'Last activity: ' + item.time : 'Activity time unavailable'));
      addProjectAction(project, item, true);
      list.appendChild(project);
    });
    canvas.appendChild(list);
    if (!items.length) canvas.appendChild(element('p', 'overview-projects__empty',
      sourceState(source.state) === 'empty' ? 'No active projects. Your other Overview sources remain available.' : 'Active projects are unavailable from this source.'));
    if (source.error && source.error.message) heading.appendChild(element('p', 'overview-source__error', source.error.message));
    scene.appendChild(canvas);
    return scene;
  }

  function layoutProjects() {
    if (!projectScene || mount.hidden || host.hidden) return;
    var canvas = projectScene.querySelector('.overview-projects__canvas');
    var projects = Array.from(projectScene.querySelectorAll('.overview-project'));
    var width = canvas.clientWidth;
    var height = Math.max(640, Math.min(860, window.innerHeight - 210));
    var gap = 18;
    // Measure the same native controls in each density; use an ellipse only
    // when every box fits the canvas and clears every other box and the O.
    for (var density of ['full', 'compact']) {
      projectScene.dataset.layout = density;
      var boxWidth = Math.max(0, ...projects.map(function (node) { return node.offsetWidth; }));
      var boxHeight = Math.max(0, ...projects.map(function (node) { return node.offsetHeight; }));
      var rx = (width - boxWidth - gap * 2) / 2;
      var ry = (height - boxHeight - gap * 2) / 2;
      var positions = projects.map(function (_node, index) {
        var angle = -Math.PI / 2 + index * Math.PI * 2 / projects.length;
        return { x: Math.cos(angle) * rx, y: Math.sin(angle) * ry };
      });
      var fits = width >= 560 && boxWidth > 0 && rx > 0 && ry > 0 && positions.every(function (point, index) {
        if (Math.abs(point.x) < boxWidth / 2 + 62 && Math.abs(point.y) < boxHeight / 2 + 62) return false;
        return positions.slice(index + 1).every(function (other) {
          return Math.abs(point.x - other.x) >= boxWidth + gap || Math.abs(point.y - other.y) >= boxHeight + gap;
        });
      });
      if (fits) {
        canvas.style.height = height + 'px';
        projects.forEach(function (node, index) {
          node.style.left = (width / 2 + positions[index].x) + 'px';
          node.style.top = (height / 2 + positions[index].y) + 'px';
        });
        return;
      }
    }
    projectScene.dataset.layout = 'wrap';
    canvas.style.height = '';
    projects.forEach(function (node) { node.style.left = ''; node.style.top = ''; });
  }

  function disconnectScene() {
    if (sceneObserver) sceneObserver.disconnect();
    sceneObserver = null;
    projectScene = null;
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
    if (sourceId === 'project-priority') addProjectAction(row, item, false);
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
    var meta = [source.source_id === 'project-priority' ? projectCount(source) : count + ' item' + (count === 1 ? '' : 's')];
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
        list.appendChild(renderItem(item && typeof item === 'object' ? item : {}, source.source_id));
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
    sources.forEach(function (source) { if (source && typeof source === 'object') byId.set(source.source_id, source); });
    var ordered = order.map(function (id) { return byId.get(id); }).filter(Boolean);
    if (ordered.length !== order.length) throw new Error('Ora returned incomplete Overview sources.');
    host.replaceChildren();
    projectScene = renderProjects(byId.get('project-priority'));
    host.appendChild(projectScene);
    ordered.forEach(function (source) { host.appendChild(renderSource(source)); });
    layoutProjects();
    if (window.ResizeObserver) {
      sceneObserver = new ResizeObserver(layoutProjects);
      sceneObserver.observe(projectScene);
    }
  }

  async function load() {
    var activeRequest = ++requestId;
    disconnectScene();
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
    // The document sees the editor's shadow host, not its focused content.
    while (priorFocus && priorFocus.shadowRoot && priorFocus.shadowRoot.activeElement) {
      priorFocus = priorFocus.shadowRoot.activeElement;
    }
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
    disconnectScene();
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
  window.addEventListener('resize', layoutProjects);
  closeButton.addEventListener('click', close);
  document.addEventListener('keydown', function (event) {
    if (mount.hidden) return;
    if (event.key === 'Escape') { close(); return; }
    if (event.key !== 'Tab') return;
    var controls = [];
    function collect(root) {
      Array.from(root.children || []).forEach(function (node) {
        var style = window.getComputedStyle(node);
        if (node.hidden || node.hasAttribute('inert') || style.display === 'none' || style.visibility === 'hidden') return;
        if (node.matches('button, input, select, textarea, a[href], [tabindex]')
            && !node.matches(':disabled') && node.tabIndex >= 0) controls.push(node);
        if (node.shadowRoot) collect(node.shadowRoot);
        else collect(node);
      });
    }
    collect(mount);
    var active = document.activeElement;
    while (active && active.shadowRoot && active.shadowRoot.activeElement) active = active.shadowRoot.activeElement;
    var index = controls.indexOf(active);
    if (index < 0 || (!event.shiftKey && index === controls.length - 1) || (event.shiftKey && index === 0)) {
      event.preventDefault();
      (controls.length ? controls[event.shiftKey ? controls.length - 1 : 0] : closeButton).focus();
    }
  });
})();
