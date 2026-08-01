/* G1.16 Model Profile quick selector.
 *
 * One menu serves both required surfaces:
 *   - the project-owned default directly beneath Active Project; and
 *   - a one-run override in the Inquiry toolbar.
 *
 * Internal compatibility endpoints keep their historical
 * `/api/configurations` names. No user-facing copy calls these objects
 * configurations, and no health/migration state is inferred in the browser.
 */
(function () {
  'use strict';

  var sidebarButton;
  var sidebarName;
  var runButton;
  var menu;
  var profiles = [];
  var effective = null;
  var oneRunOverride = '';
  var openMode = '';

  function activeProject() {
    try {
      if (window.OraSidebar && typeof window.OraSidebar.getActiveProject === 'function') {
        return window.OraSidebar.getActiveProject() || 'commons';
      }
    } catch (_) {}
    return 'commons';
  }

  function isCommons(value) {
    return !value || ['commons', 'general'].indexOf(String(value).toLowerCase()) !== -1;
  }

  function json(response) {
    return response.json().then(function (data) {
      if (!response.ok || (data && data.error)) {
        throw new Error((data && data.error) || ('HTTP ' + response.status));
      }
      return data;
    });
  }

  function effectiveName() {
    return effective && effective.selected && effective.selected.name
      ? effective.selected.name : 'Unavailable';
  }

  function effectiveSource() {
    return effective && effective.selected && effective.selected.source
      ? effective.selected.source : '';
  }

  function paintButtons() {
    if (sidebarName) {
      sidebarName.textContent = effectiveName();
      sidebarName.title = effectiveSource()
        ? 'Inherited from ' + effectiveSource().replace('_', ' ') : '';
    }
    if (runButton) {
      var name = oneRunOverride || effectiveName();
      runButton.textContent = name;
      runButton.classList.toggle('is-active', !!oneRunOverride);
      runButton.setAttribute('aria-label', oneRunOverride
        ? 'One-run Model Profile: ' + name
        : 'Model Profile inherited: ' + name);
      runButton.title = oneRunOverride
        ? name + ' for the next run only'
        : name + ' (inherited; choose a one-run override)';
    }
  }

  function load() {
    var project = activeProject();
    return fetch('/api/model-profiles?project_id=' + encodeURIComponent(project))
      .then(json)
      .then(function (data) {
        profiles = data.profiles || [];
        effective = data.effective || null;
        paintButtons();
        return data;
      })
      .catch(function (error) {
        effective = null;
        profiles = [];
        paintButtons();
        if (sidebarName) sidebarName.title = error.message || String(error);
      });
  }

  function close() {
    if (!menu) return;
    menu.hidden = true;
    menu.innerHTML = '';
    openMode = '';
    if (sidebarButton) sidebarButton.setAttribute('aria-expanded', 'false');
    if (runButton) runButton.setAttribute('aria-expanded', 'false');
  }

  function positionMenu(anchor) {
    var rect = anchor.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - 300)) + 'px';
    menu.style.top = Math.min(rect.bottom + 6, window.innerHeight - 340) + 'px';
  }

  function healthFor(profile) {
    return (profile && profile.health) || { status: 'unavailable', reason: 'Health unavailable' };
  }

  function option(profile, onSelect) {
    var health = healthFor(profile);
    var row = document.createElement('div');
    row.className = 'model-profile-menu__row';
    var choose = document.createElement('button');
    choose.type = 'button';
    choose.className = 'model-profile-menu__choice';
    choose.disabled = health.status === 'unavailable';
    choose.innerHTML = '<span>' + escapeHtml(profile.name) + '</span>'
      + '<small>' + escapeHtml(health.status) + '</small>';
    choose.title = health.reason || '';
    choose.addEventListener('click', function () { onSelect(profile.name); });
    row.appendChild(choose);
    if (health.status === 'deprecated') {
      var migrate = document.createElement('button');
      migrate.type = 'button';
      migrate.className = 'model-profile-menu__migrate';
      migrate.textContent = 'Review migration';
      migrate.addEventListener('click', function (event) {
        event.stopPropagation();
        reviewMigration(profile.name);
      });
      row.appendChild(migrate);
    }
    return row;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function post(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(json);
  }

  function selectRun(name) {
    oneRunOverride = name || '';
    close();
    paintButtons();
  }

  function selectProject(name) {
    var project = activeProject();
    var request;
    if (isCommons(project)) {
      if (!name) return;
      request = post('/api/model-profiles/global', { name: name });
    } else {
      request = post('/api/model-profiles/project/' + encodeURIComponent(project), {
        name: name || '',
      });
    }
    close();
    request.then(load).catch(function (error) {
      window.alert('Model Profile was not changed: ' + (error.message || error));
      load();
    });
  }

  function reviewMigration(name) {
    var project = activeProject();
    var projectTarget = (!isCommons(project)
      && effective && effective.selected
      && effective.selected.source === 'project'
      && effective.selected.name === name) ? project : '';
    post('/api/model-profiles/migration/preview', {
      name: name,
      project_nexus: projectTarget || undefined,
    }).then(function (data) {
      var proposal = data.proposal;
      var lines = Object.keys(proposal.replacements || {}).map(function (oldId) {
        return oldId + '  →  ' + proposal.replacements[oldId];
      });
      var accepted = window.confirm(
        'Review Model Profile migration for "' + name + '".\n\n'
        + lines.join('\n')
        + '\n\nNothing changes unless you confirm this exact proposal.'
      );
      if (!accepted) return null;
      return post('/api/model-profiles/migration/confirm', {
        name: name,
        project_nexus: projectTarget || undefined,
        proposal_id: proposal.proposal_id,
        confirmed: true,
      });
    }).then(function (result) {
      if (result) return load();
      return null;
    }).catch(function (error) {
      window.alert('Migration was not applied: ' + (error.message || error));
    });
  }

  function renderMenu(mode, anchor) {
    openMode = mode;
    menu.innerHTML = '';
    var heading = document.createElement('div');
    heading.className = 'model-profile-menu__heading';
    heading.textContent = mode === 'run' ? 'Next run'
      : (isCommons(activeProject()) ? 'Global default' : 'Project default');
    menu.appendChild(heading);

    if (mode === 'run' || !isCommons(activeProject())) {
      var inherit = document.createElement('button');
      inherit.type = 'button';
      inherit.className = 'model-profile-menu__inherit';
      inherit.textContent = mode === 'run'
        ? 'Inherit · ' + effectiveName()
        : 'Use global default';
      inherit.addEventListener('click', function () {
        if (mode === 'run') selectRun(''); else selectProject('');
      });
      menu.appendChild(inherit);
    }

    profiles.forEach(function (profile) {
      menu.appendChild(option(profile, mode === 'run' ? selectRun : selectProject));
    });
    menu.hidden = false;
    positionMenu(anchor);
    anchor.setAttribute('aria-expanded', 'true');
  }

  function toggle(mode, anchor) {
    if (!menu.hidden && openMode === mode) { close(); return; }
    load().then(function () { renderMenu(mode, anchor); });
  }

  function init() {
    sidebarButton = document.getElementById('sidebarModelConfigBtn');
    sidebarName = document.getElementById('sidebarModelConfigName');
    runButton = document.getElementById('inputToolbarModelProfile');
    menu = document.createElement('div');
    menu.className = 'model-profile-menu';
    menu.hidden = true;
    menu.setAttribute('role', 'menu');
    document.body.appendChild(menu);

    if (sidebarButton) {
      sidebarButton.setAttribute('aria-haspopup', 'menu');
      sidebarButton.addEventListener('click', function (event) {
        event.stopPropagation();
        toggle('project', sidebarButton);
      });
    }
    document.addEventListener('ora:input-toolbar:model-profile', function () {
      if (runButton) toggle('run', runButton);
    });
    document.addEventListener('ora:active-project-changed', function () {
      oneRunOverride = '';
      close();
      load();
    });
    document.addEventListener('click', function (event) {
      if (!menu.hidden && !menu.contains(event.target)
          && event.target !== sidebarButton && event.target !== runButton) close();
    });
    load();
  }

  window.OraModelProfiles = {
    getOneRunOverride: function () { return oneRunOverride || ''; },
    clearOneRunOverride: function () { oneRunOverride = ''; paintButtons(); },
    acknowledgeSubmission: function (response) {
      // A network failure or rejected HTTP request did not consume this
      // one-run authority.  Clear only after the server acknowledges the
      // submission contract with a successful response.
      if (!response || response.ok !== true) return false;
      oneRunOverride = '';
      paintButtons();
      return true;
    },
    refresh: load,
    _state: function () { return { profiles: profiles, effective: effective }; },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
