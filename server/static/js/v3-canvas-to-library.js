/* v3-canvas-to-library.js — Canvas-image → media-library transfer (2026-05-01)
 *
 * Lets the user take an image off the visual canvas (a Konva.Image node)
 * and add it to the active conversation's media library, where it
 * becomes a draggable clip source for the timeline editor.
 *
 * Two invocation paths share one helper:
 *
 *   1. Right-click on a canvas image → small context menu with a
 *      "Send to media library" entry. Wired by visual-panel.js's
 *      stage-level contextmenu listener.
 *   2. Toolbar button (tool:send_to_library, on the universal toolbar)
 *      → finds the most relevant image on the canvas and sends it.
 *      Disabled when no candidate image is present.
 *
 * Source-byte rule (decision 2 from the design conversation): we send
 * the ORIGINAL image bytes — never a rasterized snapshot of the canvas.
 * Recovery sources, in order of preference:
 *
 *   a. node.getAttr('sourcePath')  — explicit on-disk file path. Future-
 *      proof slot for upload paths that record where they staged the
 *      file. None of today's paths set this, but the helper checks
 *      first so retrofits work without further changes here.
 *   b. node.image().src as a data URL — the original file's bytes
 *      base64-encoded with the original MIME type. We decode + POST
 *      as a Blob with the same MIME, no rasterization happens.
 *   c. node.image().src as an http(s) URL — fetched and POSTed
 *      verbatim. Used when an image was loaded from a server-served
 *      path (e.g. AI-generated assets).
 *
 * If none of the above work the helper returns {ok:false} with a
 * reason. The user can always export their canvas via the existing
 * export flow and re-import the resulting raster file.
 *
 * Public API: window.OraV3CanvasToLibrary
 *   findCandidateImage(panel)         — Konva.Image | null
 *   send(panel, node)                 — Promise<{ok, ...}>
 *   sendBest(panel)                   — Promise<{ok, ...}> via findCandidateImage
 *   openContextMenu(panel, x, y, node)— opens a small floating menu
 *   _dataUrlToBlob(url)               — pure helper, exposed for tests
 *   _filenameFor(node)                — pure helper, exposed for tests
 */
(function (root) {
  'use strict';

  var MENU_ID = 'ora-canvas-to-library-menu';

  // ── Source-blob extraction ─────────────────────────────────────────────

  function _dataUrlToBlob(url) {
    if (typeof url !== 'string') return null;
    var m = /^data:([^;,]+)(?:;[^,]*)?,(.*)$/.exec(url);
    if (!m) return null;
    var mime = m[1] || 'application/octet-stream';
    var payload = m[2];
    // base64-encoded data URL: "...base64,xxxxx"
    var isBase64 = /;base64$/i.test(url.split(',')[0] || '');
    var bytes;
    try {
      if (isBase64) {
        var bin = (typeof atob === 'function') ? atob(payload) : null;
        if (bin == null) return null;
        bytes = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i) & 0xff;
      } else {
        // Percent-encoded text data URL — rare for images.
        var decoded = decodeURIComponent(payload);
        bytes = new Uint8Array(decoded.length);
        for (var j = 0; j < decoded.length; j++) bytes[j] = decoded.charCodeAt(j) & 0xff;
      }
    } catch (e) {
      return null;
    }
    try {
      return new Blob([bytes], { type: mime });
    } catch (e) {
      return null;
    }
  }

  function _filenameFor(node) {
    var attrName = (node && typeof node.getAttr === 'function')
      ? node.getAttr('sourceName') : '';
    if (attrName) return String(attrName);
    var attrType = (node && typeof node.getAttr === 'function')
      ? node.getAttr('sourceType') : '';
    var ext = 'png';
    if (attrType && attrType.indexOf('/') >= 0) {
      var t = attrType.split('/')[1].toLowerCase();
      if (t === 'jpeg') ext = 'jpg';
      else if (t === 'png' || t === 'jpg' || t === 'gif' || t === 'webp') ext = t;
    }
    return 'canvas-image-' + Date.now() + '.' + ext;
  }

  function _extractSourceBlob(node) {
    if (!node || typeof node.getAttr !== 'function') {
      return Promise.resolve({ ok: false, reason: 'invalid node' });
    }
    // (a) Explicit source path on the node — fetch verbatim. Reserved for
    // future upload paths that record the on-disk staging location.
    var srcPath = node.getAttr('sourcePath');
    if (srcPath && typeof srcPath === 'string') {
      return fetch(srcPath)
        .then(function (r) {
          if (!r || !r.ok) {
            throw new Error('source-path fetch failed (HTTP ' +
                            (r && r.status) + ')');
          }
          return r.blob();
        })
        .then(function (blob) { return { ok: true, blob: blob, via: 'sourcePath' }; })
        .catch(function (e) { return { ok: false, reason: String(e && e.message || e) }; });
    }

    // (b) / (c) HTMLImageElement.src — data URL OR http(s) URL.
    var imgEl = (typeof node.image === 'function') ? node.image() : null;
    var src = imgEl && imgEl.src;
    if (!src) {
      return Promise.resolve({ ok: false, reason: 'no source available' });
    }

    if (src.indexOf('data:') === 0) {
      var blob = _dataUrlToBlob(src);
      if (!blob) {
        return Promise.resolve({ ok: false, reason: 'malformed data URL' });
      }
      return Promise.resolve({ ok: true, blob: blob, via: 'dataUrl' });
    }

    if (/^https?:/.test(src) || src.charAt(0) === '/') {
      return fetch(src)
        .then(function (r) {
          if (!r || !r.ok) {
            throw new Error('image fetch failed (HTTP ' +
                            (r && r.status) + ')');
          }
          return r.blob();
        })
        .then(function (blob) { return { ok: true, blob: blob, via: 'url' }; })
        .catch(function (e) { return { ok: false, reason: String(e && e.message || e) }; });
    }

    return Promise.resolve({ ok: false, reason: 'unrecognized image src' });
  }

  // ── Candidate-image search ─────────────────────────────────────────────

  function findCandidateImage(panel) {
    if (!panel) return null;

    // Prefer a SELECTED Konva.Image in the user-input layer.
    if (panel._selectedShapeIds && panel._selectedShapeIds.length > 0
        && typeof panel._findShapeById === 'function') {
      for (var i = 0; i < panel._selectedShapeIds.length; i++) {
        var n = panel._findShapeById(panel._selectedShapeIds[i]);
        if (n && typeof n.getClassName === 'function'
            && n.getClassName() === 'Image') {
          return n;
        }
      }
    }

    // Fall back to the most-recent Konva.Image anywhere in the user-input
    // layer (top of stack first), then the background image.
    if (panel.userInputLayer
        && typeof panel.userInputLayer.getChildren === 'function') {
      var kids = panel.userInputLayer.getChildren();
      for (var j = kids.length - 1; j >= 0; j--) {
        var k = kids[j];
        if (k && typeof k.getClassName === 'function'
            && k.getClassName() === 'Image') {
          return k;
        }
      }
    }

    if (panel._backgroundImageNode) return panel._backgroundImageNode;

    return null;
  }

  // ── Send to library ────────────────────────────────────────────────────

  function _resolveConversationId(panel) {
    // Best-effort: look up the active conversation. visual-panel doesn't
    // own this; OraConversation typically does. Falls back to OraCanvas.
    if (root.OraConversation
        && typeof root.OraConversation.getCurrentId === 'function') {
      var cid = root.OraConversation.getCurrentId();
      if (cid) return cid;
    }
    if (root.OraCanvas && root.OraCanvas.conversationId) {
      return root.OraCanvas.conversationId;
    }
    if (panel && panel.conversationId) return panel.conversationId;
    return null;
  }

  function send(panel, node) {
    if (!node) return Promise.resolve({ ok: false, reason: 'no image' });
    var conversationId = _resolveConversationId(panel);
    if (!conversationId) {
      return Promise.resolve({ ok: false, reason: 'no active conversation' });
    }
    return _extractSourceBlob(node).then(function (extract) {
      if (!extract.ok) return extract;
      var fd = new FormData();
      var name = _filenameFor(node);
      fd.append('file', extract.blob, name);
      var url = '/api/media-library/' + encodeURIComponent(conversationId) + '/add';
      return fetch(url, { method: 'POST', body: fd }).then(function (r) {
        if (!r || !r.ok) {
          return r.json().then(function (j) {
            return { ok: false, reason: (j && j.error) || ('HTTP ' + r.status) };
          }).catch(function () {
            return { ok: false, reason: 'HTTP ' + (r && r.status) };
          });
        }
        return r.json().then(function (j) {
          // Tell the media library to refresh so the new entry appears.
          if (root.OraMediaLibrary && typeof root.OraMediaLibrary.refresh === 'function') {
            try { root.OraMediaLibrary.refresh(); } catch (e) {}
          }
          return { ok: true, entry: j, via: extract.via };
        });
      }).catch(function (e) {
        return { ok: false, reason: String(e && e.message || e) };
      });
    });
  }

  function sendBest(panel) {
    var node = findCandidateImage(panel);
    if (!node) {
      return Promise.resolve({ ok: false, reason: 'no image on canvas' });
    }
    return send(panel, node);
  }

  // ── Context menu DOM ───────────────────────────────────────────────────

  var _menuEl = null;

  function _closeMenu() {
    if (!_menuEl) return;
    try { _menuEl.remove(); } catch (e) {}
    _menuEl = null;
    document.removeEventListener('mousedown', _outsideClick, true);
    document.removeEventListener('keydown', _menuKey);
  }

  function _outsideClick(e) {
    if (!_menuEl) return;
    if (_menuEl.contains(e.target)) return;
    _closeMenu();
  }

  function _menuKey(e) {
    if (e.key === 'Escape') _closeMenu();
  }

  function openContextMenu(panel, x, y, node) {
    _closeMenu();
    if (!panel || !node) return;

    var menu = document.createElement('div');
    menu.id = MENU_ID;
    menu.setAttribute('role', 'menu');
    menu.style.cssText = [
      'position:fixed', 'z-index:99998',
      'min-width:200px',
      'background:var(--ora-bg-1, #282a36)',
      'color:var(--ora-fg, #f8f8f2)',
      'border:1px solid var(--ora-border, #44475a)',
      'border-radius:6px', 'padding:4px',
      'box-shadow:0 6px 18px rgba(0,0,0,0.45)',
      'font-family:var(--ora-font-body, Inter, system-ui, sans-serif)',
      'font-size:13px', 'line-height:1.4'
    ].join(';');
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('role', 'menuitem');
    btn.style.cssText = [
      'display:block', 'width:100%', 'text-align:left',
      'background:transparent', 'color:inherit', 'border:0',
      'border-radius:4px', 'padding:7px 10px', 'cursor:pointer',
      'font:inherit'
    ].join(';');
    btn.textContent = 'Send to media library';
    btn.addEventListener('mouseenter', function () {
      btn.style.background = 'var(--ora-bg-2, #44475a)';
    });
    btn.addEventListener('mouseleave', function () {
      btn.style.background = 'transparent';
    });
    btn.addEventListener('click', function () {
      _closeMenu();
      send(panel, node).then(function (r) {
        if (root.OraToast && typeof root.OraToast.show === 'function') {
          root.OraToast.show(r.ok
            ? 'Sent to media library'
            : ('Send failed: ' + (r.reason || 'unknown')));
        } else if (!r.ok) {
          console.warn('[v3-canvas-to-library] send failed:', r.reason);
        }
      });
    });
    menu.appendChild(btn);

    document.body.appendChild(menu);
    _menuEl = menu;

    // Defer outside-click attachment so the contextmenu's own click
    // doesn't immediately close the menu we just opened.
    setTimeout(function () {
      if (!_menuEl) return;
      document.addEventListener('mousedown', _outsideClick, true);
      document.addEventListener('keydown', _menuKey);
    }, 0);
  }

  root.OraV3CanvasToLibrary = {
    findCandidateImage: findCandidateImage,
    send: send,
    sendBest: sendBest,
    openContextMenu: openContextMenu,
    _dataUrlToBlob: _dataUrlToBlob,
    _filenameFor: _filenameFor,
    _extractSourceBlob: _extractSourceBlob,  // exposed for tests
  };
})(typeof window !== 'undefined' ? window : this);
