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
    '/analyses',
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

  const _openModes = () => {
    if (window.OraAnalysisPicker && typeof window.OraAnalysisPicker.open === 'function') {
      window.OraAnalysisPicker.open();
      return true;
    }
    document.dispatchEvent(new CustomEvent('ora:input-toolbar:analysis'));
    return true;
  };

  const _openSettings = (tab) => {
    if (!window.OraSettingsPanel || typeof window.OraSettingsPanel.open !== 'function') {
      return false;
    }
    window.OraSettingsPanel.open({ tab: _tabAlias(tab) });
    return true;
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
    if (parsed.command === '/frameworks') return _openFrameworks();
    if (parsed.command === '/modes' || parsed.command === '/analyses') return _openModes();
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
