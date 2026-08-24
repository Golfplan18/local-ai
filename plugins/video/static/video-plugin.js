/* Video plugin composition root: registers all four browser seams. */
(function (root) {
  'use strict';

  function warn(message, error) {
    if (root.console && typeof root.console.warn === 'function') {
      root.console.warn('[video-plugin] ' + message, error || '');
    }
  }

  function activeConversationId() {
    try {
      if (root.OraConversation
          && typeof root.OraConversation.getActiveConversationId === 'function') {
        return root.OraConversation.getActiveConversationId();
      }
      if (root.OraSidebar && typeof root.OraSidebar.getActiveConversation === 'function') {
        var conversation = root.OraSidebar.getActiveConversation();
        return conversation && (conversation.conversation_id || conversation.id);
      }
    } catch (error) { warn('active Dialogue lookup failed', error); }
    return null;
  }

  function visualPanel() {
    try {
      if (root.OraPanels && root.OraPanels.visual
          && typeof root.OraPanels.visual._getActive === 'function') {
        return root.OraPanels.visual._getActive();
      }
    } catch (error) { warn('visual panel lookup failed', error); }
    return null;
  }

  function initModule(name, opts) {
    var module = root[name];
    if (!module || typeof module.init !== 'function') {
      warn(name + ' is unavailable');
      return;
    }
    try { module.init(opts || {}); }
    catch (error) { warn(name + ' init failed', error); }
  }

  function initialiseFeature() {
    var conversationId = activeConversationId();
    initModule('OraCaptureControls', { conversationId: conversationId });
    initModule('OraMediaLibrary', { conversationId: conversationId });
    initModule('OraTimelineEditor', { conversationId: conversationId });
    initModule('OraPreviewMonitor', { conversationId: conversationId });
    initModule('OraTranscriptPanel', { conversationId: conversationId });
    initModule('OraRenderControls', { conversationId: conversationId });
    initModule('OraCapabilityVideoGenerates', {
      hostEl: document.body,
      visualPanel: visualPanel(),
    });
    if (root.OraV3CanvasToLibrary) root.OraV3CanvasToLibrary.init(visualPanel());
    document.addEventListener('ora:canvas-mounted', function () {
      if (root.OraCapabilityVideoGenerates
          && typeof root.OraCapabilityVideoGenerates.setVisualPanel === 'function') {
        root.OraCapabilityVideoGenerates.setVisualPanel(visualPanel());
      }
      if (root.OraV3CanvasToLibrary) root.OraV3CanvasToLibrary.init(visualPanel());
    });
  }

  function registerSeams() {
    if (!root.OraPanes || !root.OraMounts || !root.OraSettingsSections
        || !root.OraBrowseOverlays) {
      warn('one or more Ora browser seams are unavailable; video UI was skipped');
      return false;
    }

    root.OraPanes.register({
      pane: 'exhibits',
      mode: 'video',
      label: 'Video editor',
      onTake: function () { root.OraMounts.setActive('video-editor', true); },
      onRelease: function () { root.OraMounts.setActive('video-editor', false); },
    });

    root.OraMounts.register({
      position: 'exhibits',
      id: 'video-editor',
      label: 'Video editor',
      icon: 'video',
      active: false,
      onSelect: function () {
        if (root.OraPanes.owner('exhibits') === 'video') root.OraPanes.release('video');
        else root.OraPanes.take('video');
      },
    });

    root.OraBrowseOverlays.register({
      id: 'video-media-browser',
      label: 'Dialogue media',
      render: function (body) {
        if (!root.OraMediaLibrary || typeof root.OraMediaLibrary.renderBrowser !== 'function') {
          body.textContent = 'The media library is unavailable.';
          return;
        }
        return root.OraMediaLibrary.renderBrowser(body);
      },
    });
    root.OraMounts.register({
      position: 'exhibits',
      id: 'video-media-browser-button',
      label: 'Browse Dialogue media',
      icon: 'list-video',
      onSelect: function () {
        if (root.OraBrowseOverlays.isOpen('video-media-browser')) {
          root.OraBrowseOverlays.close('video-media-browser');
        } else {
          root.OraBrowseOverlays.open('video-media-browser');
        }
      },
    });
    root.OraMounts.register({
      position: 'exhibits',
      id: 'video-send-canvas-image',
      label: 'Send canvas image to media library',
      icon: 'film',
      onSelect: function () {
        var helper = root.OraV3CanvasToLibrary;
        if (!helper || typeof helper.sendBest !== 'function') return;
        helper.sendBest(visualPanel());
      },
    });

    root.OraSettingsSections.register({
      id: 'video',
      label: 'Video',
      render: function (body) {
        return root.OraVideoSettings.render(body);
      },
    });
    return true;
  }

  function registerCommands() {
    if (!root.OraSlashCommands || typeof root.OraSlashCommands.register !== 'function') {
      warn('Ora slash-command registry is unavailable; /video was skipped');
      return;
    }
    root.OraSlashCommands.register({
      command: '/video',
      settingsTab: 'video',
      settingsAliases: ['video', 'capture', 'export', 'av', 'media', 'avmedia'],
      handler: function (parsed) {
        var panes = root.OraPanes;
        if (!panes) return false;
        var mode = String(parsed && parsed.args && parsed.args[0] || 'toggle').toLowerCase();
        var active = panes.owner('exhibits') === 'video';
        if (mode === 'on' || mode === 'open') return active || panes.take('video');
        if (mode === 'off' || mode === 'close') return !active || panes.release('video');
        return active ? panes.release('video') : panes.take('video');
      },
    });
  }

  function installPaneExits() {
    var lastConversationId = null;
    document.addEventListener('ora:new-thread-requested', function () {
      if (root.OraPanes) root.OraPanes.release('video');
    });
    document.addEventListener('ora:conversation-selected', function (event) {
      var detail = event && event.detail || {};
      var conversationId = detail.conversation_id || detail.id || null;
      if (conversationId && lastConversationId && conversationId !== lastConversationId
          && root.OraPanes) {
        root.OraPanes.release('video');
      }
      lastConversationId = conversationId;
    });
  }

  initialiseFeature();
  if (registerSeams()) registerCommands();
  installPaneExits();
})(typeof window !== 'undefined' ? window : globalThis);
