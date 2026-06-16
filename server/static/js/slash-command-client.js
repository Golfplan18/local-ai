/* Browser-side slash commands for Ora.
 *
 * Server-side commands are intentionally left alone; this bridge handles only
 * UI actions that must run in the browser before the prompt is submitted.
 */
(() => {
  'use strict';

  const LOCAL_COMMANDS = new Set([
    '/new',
    '/sidebar',
    '/frameworks',
    '/modes',
    '/mode',
    '/analyses',
    '/analysis',
    '/review',
    '/settings',
    '/visual',
    '/canvas',
    '/video',
    '/image',
    '/generate-image',
  ]);

  const parse = (text) => {
    const raw = (text || '').trim();
    if (!raw || raw[0] !== '/') return null;
    const parts = raw.split(/\s+/);
    return {
      command: (parts[0] || '').toLowerCase(),
      args: parts.slice(1),
      rest: raw.slice((parts[0] || '').length).trim(),
      raw,
    };
  };

  const _tabAlias = (value) => {
    const v = (value || '').toLowerCase();
    const aliases = {
      api: 'apis',
      apis: 'apis',
      external: 'apis',
      'external-api': 'apis',
      'external-apis': 'apis',
      model: 'models',
      models: 'models',
      shortcuts: 'shortcuts',
      shortcut: 'shortcuts',
      project: 'projects',
      projects: 'projects',
      keys: 'apis',
      visual: 'visual',
      interface: 'interface',
      capture: 'capture',
      export: 'export',
      transcription: 'transcription',
      speech: 'speech',
    };
    return aliases[v] || v || 'models';
  };

  const _setSidebar = (mode) => {
    const sidebar = window.OraSidebar;
    if (!sidebar || typeof sidebar.setExpanded !== 'function') return false;
    const m = (mode || 'toggle').toLowerCase();
    if (m === 'open') sidebar.setExpanded(true);
    else if (m === 'close') sidebar.setExpanded(false);
    else sidebar.setExpanded(!sidebar.isExpanded || !sidebar.isExpanded());
    return true;
  };

  const _openFrameworks = () => {
    if (window.OraFrameworkPicker && typeof window.OraFrameworkPicker.open === 'function') {
      window.OraFrameworkPicker.open();
      return true;
    }
    document.dispatchEvent(new CustomEvent('ora:input-toolbar:framework'));
    return true;
  };

  const _normaliseToken = (value) => (value || '')
    .toLowerCase()
    .replace(/\.md$/, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  const _frameworkAlias = (value) => {
    const v = _normaliseToken(value);
    const aliases = {
      cff: 'corpus-formalization',
      pff: 'process-formalization',
      off: 'output-formalization',
    };
    return aliases[v] || v;
  };

  const _stageFramework = (target) => {
    const wanted = _frameworkAlias(target);
    if (!wanted) return _openFrameworks();
    fetch('/api/frameworks/picker')
      .then((res) => res.ok ? res.json() : { frameworks: [] })
      .then((payload) => {
        const rows = Array.isArray(payload && payload.frameworks)
          ? payload.frameworks : [];
        const match = rows.find((fw) => {
          const id = _normaliseToken(fw.id);
          const name = _normaliseToken(fw.display_name);
          return id === wanted || name === wanted;
        });
        if (!match) {
          window.alert(`No framework named "${target}".`);
          _openFrameworks();
          return;
        }
        if (window.OraInputState && typeof window.OraInputState.setFramework === 'function') {
          window.OraInputState.setFramework(match);
        }
        if (window.OraFrameworkPicker && typeof window.OraFrameworkPicker.close === 'function') {
          window.OraFrameworkPicker.close();
        }
      })
      .catch(() => {
        window.alert('Could not load frameworks.');
      });
    return true;
  };

  const _openModes = () => {
    if (window.OraAnalysisPicker && typeof window.OraAnalysisPicker.open === 'function') {
      window.OraAnalysisPicker.open();
      return true;
    }
    document.dispatchEvent(new CustomEvent('ora:input-toolbar:analysis'));
    return true;
  };

  const _stageMode = (target) => {
    const wanted = _normaliseToken(target);
    if (!wanted) return _openModes();
    fetch('/api/analyses/picker')
      .then((res) => res.ok ? res.json() : { modes: [] })
      .then((payload) => {
        const rows = Array.isArray(payload && payload.modes) ? payload.modes : [];
        const match = rows.find((mode) => {
          const id = _normaliseToken(mode.id);
          const name = _normaliseToken(mode.display_name);
          const educational = _normaliseToken(mode.educational_name);
          return id === wanted || name === wanted || educational === wanted;
        });
        if (!match) {
          window.alert(`No analysis mode named "${target}".`);
          _openModes();
          return;
        }
        if (window.OraInputState && typeof window.OraInputState.setAnalysisMode === 'function') {
          window.OraInputState.setAnalysisMode(match);
        }
        if (window.OraAnalysisPicker && typeof window.OraAnalysisPicker.close === 'function') {
          window.OraAnalysisPicker.close();
        }
      })
      .catch(() => {
        window.alert('Could not load analysis modes.');
      });
    return true;
  };

  const _openSettings = (tab) => {
    if (!window.OraSettingsPanel || typeof window.OraSettingsPanel.open !== 'function') {
      return false;
    }
    window.OraSettingsPanel.open({ tab: _tabAlias(tab) });
    return true;
  };

  const _openReviewQueue = () => {
    if (window.OraReviewQueuePanel && typeof window.OraReviewQueuePanel.open === 'function') {
      window.OraReviewQueuePanel.open({ tab: 'paused' });
      return true;
    }
    const btn = document.getElementById('sidebarReviewQueueOpen');
    if (btn) {
      btn.click();
      return true;
    }
    return false;
  };

  const _setVideo = (mode) => {
    if (!window.OraPaneMode || typeof window.OraPaneMode.set !== 'function') return false;
    const m = (mode || 'toggle').toLowerCase();
    const cur = (typeof window.OraPaneMode.current === 'function')
      ? window.OraPaneMode.current()
      : null;
    if (m === 'on' || m === 'open') window.OraPaneMode.set('video');
    else if (m === 'off' || m === 'close') window.OraPaneMode.set(null);
    else window.OraPaneMode.set(cur === 'video' ? null : 'video');
    return true;
  };

  const _showVisualCanvas = () => {
    if (window.OraPaneMode && typeof window.OraPaneMode.set === 'function') {
      window.OraPaneMode.set(null);
    }
    const pane = document.querySelector('.right-pane');
    if (pane && typeof pane.focus === 'function') {
      if (!pane.hasAttribute('tabindex')) pane.setAttribute('tabindex', '-1');
      pane.focus();
    }
    return true;
  };

  const _runImageCommand = (detail) => {
    const prompt = (detail.rest || '').trim();
    if (!prompt) {
      const btn = document.getElementById('inputToolbarImageGenerate');
      if (btn) {
        btn.click();
        return true;
      }
      document.dispatchEvent(new CustomEvent('ora:input-toolbar:image-generate'));
      return true;
    }
    document.body.dispatchEvent(new CustomEvent('capability-dispatch', {
      detail: {
        slot: 'image_generates',
        inputs: { prompt },
        execution_pattern: 'sync',
        source: 'slash-command',
      },
      bubbles: true,
    }));
    return true;
  };

  const handleClientCommand = (text) => {
    const parsed = parse(text);
    if (!parsed || !LOCAL_COMMANDS.has(parsed.command)) return false;

    if (parsed.command === '/new') {
      document.dispatchEvent(new CustomEvent('ora:new-thread-requested', {
        detail: { source: 'slash-command' },
      }));
      return true;
    }
    if (parsed.command === '/sidebar') return _setSidebar(parsed.args[0]);
    if (parsed.command === '/frameworks') return _stageFramework(parsed.rest);
    if (parsed.command === '/modes' || parsed.command === '/mode'
        || parsed.command === '/analyses' || parsed.command === '/analysis') {
      return _stageMode(parsed.rest);
    }
    if (parsed.command === '/review') return _openReviewQueue();
    if (parsed.command === '/settings') return _openSettings(parsed.args[0]);
    if (parsed.command === '/visual' || parsed.command === '/canvas') return _showVisualCanvas();
    if (parsed.command === '/video') return _setVideo(parsed.args[0]);
    if (parsed.command === '/image' || parsed.command === '/generate-image') {
      return _runImageCommand(parsed);
    }
    return false;
  };

  window.OraSlashCommands = {
    parse,
    handleClientCommand,
  };
})();
