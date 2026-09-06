/* Overview Desktop renderer and scoped action entrances. */
(function () {
  'use strict';

  var order = ['project-priority', 'oversight', 'triggers', 'daily-note', 'matrix-tasks'];
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
  // Drafts belong to this page's existing controller, never browser storage.
  var taskGroups = new Map();
  var tasksSource = null;
  var tasksCard = null;
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
    status.textContent = 'Five sources checked.';
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

  function validTaskGroup(group, nexus) {
    if (!group || group.nexus !== nexus || !Array.isArray(group.tasks)
        || !['ready', 'empty', 'partial', 'read-only', 'unavailable'].includes(group.state)
        || typeof group.editable !== 'boolean' || !group.counts) return false;
    if (group.state === 'unavailable') return !group.editable && group.tasks.length === 0;
    if (typeof group.identity !== 'string' || !group.identity
        || !/^[a-f0-9]{64}$/.test(group.digest) || typeof group.root_ref !== 'string'
        || typeof group.source_text !== 'string') return false;
    var prefix = group.identity + ':' + group.digest + ':';
    var refs = new Set();
    return group.root_ref === prefix + 'root' && group.tasks.every(function (task) {
      if (!task || typeof task.ref !== 'string' || !task.ref.startsWith(prefix)
          || refs.has(task.ref) || typeof task.text !== 'string' || typeof task.done !== 'boolean'
          || !Number.isInteger(task.depth) || task.depth < 0
          || (task.parent_ref !== null && !refs.has(task.parent_ref))
          || (task.completion_date !== null && typeof task.completion_date !== 'string')
          || typeof task.date_ambiguous !== 'boolean' || !task.limitations
          || typeof task.limitations !== 'object') return false;
      refs.add(task.ref);
      return true;
    });
  }

  function taskCount(group) {
    var counts = group.counts || {};
    return Number.isInteger(counts.total) && counts.total >= 0
      ? counts.total + (group.state === 'partial' ? ' known tasks' : ' tasks')
        + ' · ' + counts.completed + ' completed · ' + group.state
      : 'Task count unavailable · ' + group.state;
  }

  function tasksCount(source) {
    return Number.isInteger(source.count) && source.count >= 0
      ? source.count + (source.state === 'partial' ? ' known tasks · Partial inventory' : ' tasks')
      : 'Task count unavailable';
  }

  function taskButton(label, action, callback, reason) {
    var button = element('button', 'overview-source__action', label);
    button.type = 'button';
    button.dataset.taskAction = action;
    button.dataset.taskFocus = action;
    button.disabled = Boolean(reason);
    if (reason) button.title = reason;
    button.addEventListener('click', function () { if (!button.disabled) callback(); });
    return button;
  }

  function taskField(parent, label, control) {
    var wrapper = element('label', 'overview-tasks__field', label);
    wrapper.appendChild(control);
    parent.appendChild(wrapper);
    return control;
  }

  function taskMessage(state, message) {
    state.message = message;
    if (state.node) state.node.querySelector('.overview-tasks__message').textContent = message;
  }

  function unbindDraft(state) {
    if (!state.draft) return;
    state.draft.bound = false;
    state.draft.target = null;
    state.draft.destination = null;
  }

  function invalidateTasks() {
    taskGroups.forEach(function (state) {
      if (state.pending) {
        state.pending.abort();
        state.pending = null;
        state.message = 'The action may have been saved. Refresh and select its target before another action.';
      }
      state.needsRefresh = true;
      unbindDraft(state);
    });
  }

  function replaceTaskGroup(state, focusKey) {
    var old = state.node;
    var scroll = old ? old.querySelector('.overview-tasks__list') : null;
    var scrollTop = scroll ? scroll.scrollTop : 0;
    var next = renderTaskGroup(state);
    if (old && old.isConnected) old.replaceWith(next);
    var list = next.querySelector('.overview-tasks__list');
    if (list) list.scrollTop = scrollTop;
    if (focusKey && !mount.hidden && !host.hidden) {
      var control = Array.from(next.querySelectorAll('[data-task-focus]')).find(function (node) {
        return node.dataset.taskFocus === focusKey && !node.matches(':disabled');
      });
      (control || next.querySelector('summary')).focus();
    }
  }

  function updateTasksMeta() {
    if (!tasksCard || !tasksSource) return;
    var items = tasksSource.items || [];
    var known = items.filter(function (group) { return Number.isInteger(group.counts && group.counts.total); });
    // A skipped inventory row is not repaired by refreshing a known project.
    var inventoryError = tasksSource.error && tasksSource.error.code === 'project_records_skipped' ? tasksSource.error : null;
    var groupPartial = items.some(function (group) {
      return !['ready', 'empty'].includes(group.state) || !Number.isInteger(group.counts && group.counts.total);
    });
    var partial = Boolean(inventoryError) || groupPartial;
    tasksSource.count = known.length ? known.reduce(function (total, group) { return total + group.counts.total; }, 0)
      : items.length || partial ? null : 0;
    tasksSource.state = items.length && !known.length ? 'unavailable' : partial ? 'partial' : items.length ? 'ready' : 'empty';
    tasksSource.available = tasksSource.state !== 'unavailable';
    tasksSource.error = inventoryError || (groupPartial ? { code: 'task_source_incomplete',
      message: 'Known task counts only; some Matrix content or project authority needs attention.' } : null);
    tasksCard.dataset.state = tasksSource.state;
    tasksCard.querySelector('.overview-source__state').textContent = tasksSource.state;
    tasksCard.querySelector('.overview-source__meta').textContent = tasksCount(tasksSource) + ' · Refreshed project results';
    var warning = tasksCard.querySelector('.overview-tasks__error');
    warning.textContent = tasksSource.error ? tasksSource.error.message : '';
    warning.hidden = !warning.textContent;
  }

  function acceptTaskGroup(state, group) {
    state.group = Object.assign({}, state.group, group);
    if (tasksSource) tasksSource.items = tasksSource.items.map(function (item) {
      return item.nexus === state.group.nexus ? state.group : item;
    });
    state.needsRefresh = false;
    updateTasksMeta();
  }

  async function taskRequest(state, body, focusKey) {
    if (state.pending || mount.hidden || !state.node.isConnected) return;
    var mutation = Boolean(body);
    if (mutation && (state.needsRefresh || !state.group.editable || !state.draft || !state.draft.bound)) return;
    var generation = requestId;
    var identity = state.group.identity;
    var controller = new AbortController();
    state.pending = controller;
    taskMessage(state, mutation ? 'Saving task…' : 'Refreshing tasks…');
    replaceTaskGroup(state);
    function current() {
      return generation === requestId && !mount.hidden && state.pending === controller
        && state.group.identity === identity && state.node.isConnected;
    }
    try {
      var response = await window.fetch('/api/projects/' + encodeURIComponent(state.group.nexus) + '/tasks', {
        method: mutation ? 'POST' : 'GET',
        headers: mutation ? { Accept: 'application/json', 'Content-Type': 'application/json' } : { Accept: 'application/json' },
        ...(mutation ? { body: JSON.stringify(body) } : {}), signal: controller.signal,
      });
      var payload;
      try { payload = await response.json(); } catch (_error) { payload = null; }
      if (!current()) return;
      var valid = response.ok && payload && payload.ok === true && validTaskGroup(payload.group, state.group.nexus);
      if (mutation) {
        valid = valid && payload.group.identity === identity && typeof payload.saved === 'boolean'
          && typeof payload.changed === 'boolean' && payload.saved === payload.changed
          && payload.correspondence && typeof payload.correspondence === 'object'
          && !Array.isArray(payload.correspondence)
          && Object.values(payload.correspondence).every(function (ref) {
            return payload.group.tasks.some(function (task) { return task.ref === ref; });
          }) && state.group.tasks.every(function (task) {
            return body.operation === 'delete' && task.ref === body.target || typeof payload.correspondence[task.ref] === 'string';
          }) && new Set(Object.values(payload.correspondence)).size === Object.values(payload.correspondence).length
          && (payload.focus_ref === null || payload.group.tasks.some(function (task) { return task.ref === payload.focus_ref; }));
      }
      if (valid) {
        var draft = state.draft;
        acceptTaskGroup(state, payload.group);
        if (!mutation) {
          unbindDraft(state);
          state.message = draft ? 'Refreshed. Your draft is retained. Select its task or add position again before saving.' : 'Tasks refreshed.';
        } else {
          state.message = payload.changed ? 'Task saved.' : 'No change was needed.';
          if (body.operation === 'add') {
            state.draft = null;
            focusKey = payload.focus_ref ? 'select:' + payload.focus_ref : 'add';
          } else if (draft) {
            var mapped = payload.correspondence[draft.target];
            var task = state.group.tasks.find(function (row) { return row.ref === mapped; });
            if (task) {
              draft.target = task.ref;
              if (body.operation === 'edit') draft.textDirty = false;
              if (body.operation === 'set-date' || body.operation === 'clear-date') draft.dateDirty = false;
              if (!draft.textDirty) draft.text = task.text;
              if (!draft.dateDirty) draft.date = task.completion_date || '';
            } else if (draft.textDirty || draft.dateDirty) {
              unbindDraft(state);
              state.message += ' Your draft is retained; select a task to use it.';
              focusKey = 'retarget';
            } else {
              state.draft = null;
              focusKey = payload.focus_ref ? 'select:' + payload.focus_ref : 'add';
            }
          }
        }
      } else {
        var refused = mutation && payload && payload.ok === false && payload.saved === false
          && ['refused', 'conflict', 'unavailable'].includes(payload.code) && typeof payload.error === 'string';
        state.needsRefresh = !refused || payload.code !== 'refused';
        if (state.needsRefresh) unbindDraft(state);
        state.message = refused ? payload.error : mutation
          ? 'The save outcome is unknown. Refresh before another action; this action will not be replayed.'
          : 'Tasks could not be refreshed. Your draft is retained. Try Refresh tasks again.';
      }
    } catch (_error) {
      if (!current()) return;
      state.needsRefresh = true;
      unbindDraft(state);
      state.message = mutation ? 'The save outcome is unknown. Refresh before another action; this action will not be replayed.'
        : 'Tasks could not be refreshed. Your draft is retained. Try Refresh tasks again.';
    } finally {
      if (current()) {
        state.pending = null;
        replaceTaskGroup(state, focusKey);
      } else if (state.pending === controller) {
        // A successful explicit refresh may have returned a new identity.
        state.pending = null;
        if (generation === requestId && !mount.hidden && state.node.isConnected) replaceTaskGroup(state, focusKey);
      }
    }
  }

  function selectTask(state, task) {
    var draft = state.draft;
    if (draft && (draft.bound || draft.mode === 'add') && (draft.textDirty || draft.dateDirty)) {
      taskMessage(state, 'Save or Cancel the current draft before choosing another task.');
      return;
    }
    if (draft && !draft.bound && draft.mode === 'edit') {
      draft.target = task.ref;
      draft.bound = true;
      if (!draft.textDirty) draft.text = task.text;
      if (!draft.dateDirty) draft.date = task.completion_date || '';
    } else {
      state.draft = { mode: 'edit', target: task.ref, bound: true, text: task.text,
        date: task.completion_date || '', textDirty: false, dateDirty: false };
    }
    state.message = 'Selected task: ' + task.text;
    replaceTaskGroup(state, 'text');
  }

  function renderTaskEditor(state) {
    var draft = state.draft;
    var group = state.group;
    var editor = element('fieldset', 'overview-tasks__editor');
    editor.disabled = Boolean(state.pending);
    editor.appendChild(element('legend', '', draft.mode === 'add' ? 'Add a task' : 'Selected task actions'));
    var task = group.tasks.find(function (row) { return row.ref === draft.target; });
    var blocked = state.needsRefresh ? 'Refresh tasks before another action.'
      : !group.editable ? group.reason || 'This group is read-only.' : !draft.bound ? 'Select a current task or add position first.' : '';
    function perform(operation, fields, focus) {
      taskRequest(state, Object.assign({ expected_digest: group.digest, operation: operation }, fields), focus || operation);
    }
    if (!draft.bound && draft.mode === 'edit') {
      var retarget = taskField(editor, 'Choose task for retained draft', element('select'));
      retarget.dataset.taskFocus = 'retarget';
      retarget.appendChild(new Option('Select a task…', ''));
      group.tasks.forEach(function (row, index) { retarget.appendChild(new Option((index + 1) + '. Level ' + (row.depth + 1) + ': ' + row.text, row.ref)); });
      retarget.addEventListener('change', function () {
        var selected = group.tasks.find(function (row) { return row.ref === retarget.value; });
        if (selected) selectTask(state, selected);
      });
    }
    if (draft.mode === 'add') {
      var placement = taskField(editor, 'Add position', element('select'));
      placement.dataset.taskFocus = 'placement';
      placement.appendChild(new Option('Select a position…', ''));
      var positions = [{ ref: group.root_ref, position: 'root', label: 'At the end, at root level' }];
      group.tasks.forEach(function (row, index) {
        ['before', 'after', 'child'].forEach(function (position) {
          positions.push({ ref: row.ref, position: position, label: (position === 'child' ? 'As child of' : position === 'before' ? 'Before' : 'After')
            + ' task ' + (index + 1) + ': ' + row.text });
        });
      });
      positions.forEach(function (position, index) {
        var option = new Option(position.label, String(index));
        option.selected = draft.bound && draft.destination === position.ref && draft.position === position.position;
        placement.appendChild(option);
      });
      placement.addEventListener('change', function () {
        var position = placement.value === '' ? null : positions[Number(placement.value)];
        draft.destination = position && position.ref;
        draft.position = position && position.position;
        draft.bound = Boolean(position);
        replaceTaskGroup(state, 'placement');
      });
    }
    var text = taskField(editor, 'Task text (complete label, including any Markdown)', element('input'));
    text.type = 'text'; text.value = draft.text; text.dataset.taskFocus = 'text';
    text.addEventListener('input', function () { draft.text = text.value; draft.textDirty = true; });
    editor.appendChild(taskButton(draft.mode === 'add' ? 'Save new task' : 'Save text', draft.mode === 'add' ? 'save-add' : 'edit', function () {
      perform(draft.mode === 'add' ? 'add' : 'edit', draft.mode === 'add'
        ? { destination: draft.destination, position: draft.position, value: draft.text }
        : { target: draft.target, value: draft.text }, draft.mode === 'add' ? 'save-add' : 'text');
    }, blocked));
    if (draft.mode === 'edit') {
      var date = taskField(editor, 'Completion date (does not change completion state)', element('input'));
      date.type = 'date'; date.value = draft.date; date.dataset.taskFocus = 'date';
      date.addEventListener('input', function () { draft.date = date.value; draft.dateDirty = true; });
      var limits = task ? task.limitations : {};
      var actions = element('div', 'overview-tasks__actions');
      [ ['Save completion date', 'set-date'], ['Clear completion date', 'clear-date'],
        [task && task.done ? 'Reopen task' : 'Complete task', task && task.done ? 'reopen' : 'complete'],
        ['Indent', 'indent'], ['Outdent', 'outdent'], ['Promote to root', 'promote'], ['Delete task', 'delete'],
      ].forEach(function (definition) {
        var op = definition[1];
        var reason = blocked || limits[op];
        var siblings = task ? group.tasks.filter(function (row) { return row.parent_ref === task.parent_ref; }) : [];
        if (op === 'indent' && siblings[0] === task) reason = reason || 'The first sibling has no preceding task to indent under.';
        var button = taskButton(definition[0], op, function () {
          perform(op, Object.assign({ target: draft.target }, op === 'set-date' ? { value: draft.date } : {}), op === 'set-date' || op === 'clear-date' ? 'date' : 'text');
        }, reason);
        actions.appendChild(button);
        if (reason && !blocked) actions.appendChild(element('small', 'overview-source__error', definition[0] + ': ' + reason));
      });
      var siblings = task ? group.tasks.filter(function (row) { return row.parent_ref === task.parent_ref; }) : [];
      var index = siblings.indexOf(task);
      [['Move earlier', -1, 'before'], ['Move later', 1, 'after']].forEach(function (definition) {
        var destination = siblings[index + definition[1]];
        var reason = blocked || limits.reorder || (!destination ? 'No sibling in this direction.' : '');
        actions.appendChild(taskButton(definition[0], definition[2] === 'before' ? 'move-earlier' : 'move-later', function () {
          perform('reorder', { target: draft.target, destination: destination.ref, position: definition[2] }, 'text');
        }, reason));
        if (reason && !blocked) actions.appendChild(element('small', 'overview-source__error', definition[0] + ': ' + reason));
      });
      editor.appendChild(actions);
    }
    if (blocked) editor.appendChild(element('p', 'overview-source__error', blocked));
    editor.appendChild(taskButton('Cancel draft', 'cancel', function () {
      state.draft = null;
      state.message = 'Draft cancelled.';
      replaceTaskGroup(state, 'add');
    }));
    return editor;
  }

  function renderTaskGroup(state) {
    var group = state.group;
    var node = element('details', 'overview-tasks__group');
    node.dataset.taskNexus = group.nexus;
    node.dataset.state = group.state;
    node.open = state.expanded !== false;
    node.addEventListener('toggle', function () { if (state.node === node) state.expanded = node.open; });
    var summary = element('summary');
    summary.append(element('strong', '', group.title || group.nexus), element('span', '', taskCount(group)));
    summary.dataset.taskFocus = 'summary';
    node.appendChild(summary);
    if (group.reason) node.appendChild(element('p', 'overview-source__error', group.reason));
    var message = element('p', 'overview-tasks__message', state.message || '');
    message.setAttribute('role', 'status'); message.setAttribute('aria-live', 'polite');
    node.appendChild(message);
    var toolbar = element('div', 'overview-tasks__actions');
    toolbar.appendChild(taskButton('Refresh tasks', 'refresh', function () { taskRequest(state, null, 'refresh'); }, state.pending ? 'A request is pending.' : ''));
    toolbar.appendChild(taskButton('Add task', 'add', function () {
      if (state.draft && (state.draft.textDirty || state.draft.dateDirty)) {
        taskMessage(state, 'Save or Cancel the current draft before adding a task.'); return;
      }
      state.draft = { mode: 'add', text: '', date: '', textDirty: false, dateDirty: false,
        bound: true, destination: group.root_ref, position: 'root' };
      replaceTaskGroup(state, 'text');
    }, state.pending || state.needsRefresh || !group.editable ? group.reason || 'Refresh current writable Tasks before adding.' : ''));
    addProjectAction(toolbar, group, false);
    node.appendChild(toolbar);
    var body = element('div', 'overview-tasks__body');
    var list = element('ol', 'overview-tasks__list');
    list.setAttribute('aria-label', 'Tasks for ' + (group.title || group.nexus) + ', in source order');
    group.tasks.forEach(function (task, index) {
      var row = element('li', 'overview-tasks__task');
      row.dataset.taskRef = task.ref;
      row.dataset.depth = String(task.depth);
      row.style.setProperty('--task-depth', Math.min(task.depth, 4));
      var label = 'Task ' + (index + 1) + ' · Level ' + (task.depth + 1) + ' · ' + (task.done ? 'Completed' : 'Incomplete');
      if (task.parent_ref) label += ' · Child of task ' + (group.tasks.findIndex(function (parent) { return parent.ref === task.parent_ref; }) + 1);
      var button = taskButton(task.text, 'select', function () { selectTask(state, task); }, state.pending ? 'A request is pending.' : '');
      button.dataset.taskFocus = 'select:' + task.ref;
      button.setAttribute('aria-label', label + ': ' + task.text);
      button.setAttribute('aria-pressed', String(Boolean(state.draft && state.draft.target === task.ref)));
      row.append(element('small', '', label), button);
      list.appendChild(row);
    });
    if (!group.tasks.length) list.appendChild(element('li', '', group.state === 'empty' ? 'No tasks yet.' : 'No readable tasks in this snapshot.'));
    body.appendChild(list);
    if (state.draft) body.appendChild(renderTaskEditor(state));
    else body.appendChild(element('p', 'overview-tasks__hint', 'Select a task to edit its text, completion, date or position.'));
    node.appendChild(body);
    if (typeof group.source_text === 'string' && group.source_text) {
      var original = element('details', 'overview-tasks__source');
      original.append(element('summary', '', 'View original Tasks Markdown'), element('pre', 'overview-desktop__literal', group.source_text));
      node.appendChild(original);
    }
    state.node = node;
    return node;
  }

  function renderTasks(source) {
    tasksSource = source;
    var card = element('section', 'overview-source overview-tasks');
    tasksCard = card;
    card.dataset.sourceId = 'matrix-tasks'; card.dataset.state = sourceState(source.state);
    var heading = element('div', 'overview-source__heading');
    heading.append(element('h2', '', 'Tasks'), element('span', 'overview-source__state', sourceState(source.state)));
    card.append(heading, element('p', 'overview-source__meta', tasksCount(source)
      + (source.freshness && source.freshness.observed_at ? ' · Checked ' + source.freshness.observed_at : '')),
    element('p', 'overview-tasks__hint', 'From each project’s Matrix, in project priority order. Refresh to see external edits.'));
    var warning = element('p', 'overview-source__error overview-tasks__error', source.error && source.error.message || '');
    warning.hidden = !warning.textContent;
    card.appendChild(warning);
    var items = Array.isArray(source.items) ? source.items : [];
    items.forEach(function (group) {
      var nexus = group && group.scope && group.scope.project_nexus;
      if (typeof nexus !== 'string' || !/^[a-z0-9][a-z0-9_-]*$/.test(nexus)
          || ['commons', 'general'].includes(nexus) || group.item_id !== 'project:' + nexus || !validTaskGroup(group, nexus)) {
        card.appendChild(element('p', 'overview-source__error', 'A Tasks group is unavailable because its source record is invalid.'));
        return;
      }
      var state = taskGroups.get(nexus) || { draft: null, expanded: true, pending: null };
      state.group = group; state.needsRefresh = false;
      unbindDraft(state);
      state.message = state.draft ? 'Your draft is retained. Select its task or add position again before saving.' : '';
      taskGroups.set(nexus, state);
      card.appendChild(renderTaskGroup(state));
    });
    if (!items.length) card.appendChild(element('p', 'overview-source__empty', source.state === 'empty' ? 'No active project Tasks.' : 'Tasks are unavailable from this source.'));
    return card;
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
    if (source.source_id === 'matrix-tasks') return renderTasks(source);
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
    invalidateTasks();
    disconnectScene();
    host.replaceChildren();
    status.textContent = 'Loading five Overview sources…';
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
      status.textContent = 'Five sources checked.';
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
    invalidateTasks();
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
  window.addEventListener('pagehide', function () { requestId += 1; invalidateTasks(); taskGroups.clear(); });
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
        if (node.matches('button, input, select, textarea, summary, a[href], [tabindex]')
            && !node.matches(':disabled') && node.tabIndex >= 0) controls.push(node);
        if (node.shadowRoot) collect(node.shadowRoot);
        else if (node.tagName === 'DETAILS' && !node.open) {
          var summary = node.querySelector('summary');
          if (summary && summary.tabIndex >= 0) controls.push(summary);
        }
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
