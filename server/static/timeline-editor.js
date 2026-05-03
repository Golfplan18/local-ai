/**
 * timeline-editor.js — Audio/Video Phase 5
 *
 * Per-conversation timeline editor that lives in the middle band of the
 * visual pane when `body.pane-mode-video` is active. Loads / mutates /
 * persists state via /api/timeline/<conv_id>.
 *
 * Phase 5 scope:
 *   - 2 default tracks (video + audio), additional pip + music toggleable.
 *   - "+ Track" button to add a track from a small kind-picker.
 *   - Ruler with timecode + total duration + zoom controls.
 *   - Playhead (vertical line). Click/drag the ruler to scrub.
 *   - Drag a media-library entry onto a track lane to place a clip.
 *   - Drag clip body to move; drag clip edges to trim.
 *   - Keyboard: S splits the selected clip at the playhead; Delete removes.
 *   - Right-click on a clip: transition picker (in / out / cut / dissolve
 *     / fade-from-black / fade-to-black) — UI only; render lands in Phase 7.
 *
 * Deferred to later phases (per Phase 5 boundary report):
 *   - Multi-track FFmpeg-driven preview monitor (Phase 7 has the render
 *     pipeline; preview shares logic).
 *   - Per-clip volume slider + fade-handle drag (Phase 6 overlays/title).
 *
 * Public namespace: window.OraTimelineEditor
 *   .init()                        → call once at page load
 *   .setConversationId(id)
 *   .reload()                      → re-fetch from server
 *   .getState()                    → snapshot for tests
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ─────────────────────────────────────────────────────────

  var _hostEl = null;
  var _editorEl = null;            // .timeline-editor root
  var _viewportEl = null;          // scrollable viewport
  var _tracksEl = null;            // tracks container
  var _rulerEl = null;             // top ruler
  var _playheadEl = null;          // vertical playhead line
  var _conversationId = null;
  var _state = null;               // canonical timeline state
  var _selectedClipId = null;      // primary selection (single clip)
  var _selectedTrackId = null;
  // V3 Backlog 2A Phase 5 close-out — secondary selection set for
  // bulk operations (Shift+click adds to / removes from). Map keys
  // are clipId (globally unique because _addClipFromLibrary mints
  // ts+rand ids); values are { trackId } so bulk ops know where each
  // clip lives. Primary _selectedClipId is NOT in this map.
  var _secondarySelection = new Map();
  var _saveDebounce = null;
  var _libraryEntriesCache = {};   // entry_id → entry (used to look up names + duration on drop)
  var _ctxMenuEl = null;
  var _inspectorEl = null;         // overlay inspector panel when open

  // ── Helpers ──────────────────────────────────────────────────────────────

  function _formatTimecode(ms, withFrames) {
    if (!isFinite(ms) || ms < 0) ms = 0;
    var totalSec = Math.floor(ms / 1000);
    var h = Math.floor(totalSec / 3600);
    var m = Math.floor((totalSec % 3600) / 60);
    var s = totalSec % 60;
    var hh = String(h).padStart(2, '0');
    var mm = String(m).padStart(2, '0');
    var ss = String(s).padStart(2, '0');
    if (withFrames) {
      var frames = Math.floor((ms % 1000) / (1000 / 30));
      return hh + ':' + mm + ':' + ss + ':' + String(frames).padStart(2, '0');
    }
    return hh + ':' + mm + ':' + ss;
  }

  function _msToPx(ms) {
    return Math.max(0, ms) * (_state ? _state.zoom_pixels_per_ms : 0.05);
  }
  function _pxToMs(px) {
    return Math.max(0, px) / (_state ? _state.zoom_pixels_per_ms : 0.05);
  }

  // V3 Backlog 2A Phase 5 close-out — snap to nearby clip edges on the
  // target track. Returns positionMs unchanged if nothing within
  // ``thresholdPx`` (default ~10 px). ``excludeClipId`` lets a clip-move
  // skip its own old position so a tiny adjustment doesn't snap back.
  var SNAP_THRESHOLD_PX = 10;
  function _snapToClipEdge(trackId, positionMs, excludeClipId) {
    var t = _findTrack(trackId);
    if (!t || !t.clips || !t.clips.length) return positionMs;
    var pxPerMs = _state && _state.zoom_pixels_per_ms;
    if (!pxPerMs || pxPerMs <= 0) return positionMs;
    var thresholdMs = SNAP_THRESHOLD_PX / pxPerMs;
    var best = null;
    var bestDelta = Infinity;
    t.clips.forEach(function (c) {
      if (excludeClipId && c.id === excludeClipId) return;
      var clipLen = c.out_point_ms - c.in_point_ms;
      var clipEnd = c.track_position_ms + clipLen;
      [c.track_position_ms, clipEnd].forEach(function (edge) {
        var d = Math.abs(positionMs - edge);
        if (d <= thresholdMs && d < bestDelta) {
          bestDelta = d;
          best = edge;
        }
      });
    });
    return best == null ? positionMs : best;
  }

  function _findClip(trackId, clipId) {
    if (!_state) return null;
    var t = _state.tracks.find(function (x) { return x.id === trackId; });
    if (!t) return null;
    return t.clips.find(function (c) { return c.id === clipId; }) || null;
  }

  function _findTrack(trackId) {
    if (!_state) return null;
    return _state.tracks.find(function (x) { return x.id === trackId; }) || null;
  }

  // ── Persistence ──────────────────────────────────────────────────────────

  function _loadState() {
    if (!_conversationId) return Promise.resolve(null);
    return fetch('/api/timeline/' + encodeURIComponent(_conversationId))
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j && j.timeline) _state = j.timeline;
        return _state;
      })
      .catch(function () { _state = null; });
  }

  // V3 Backlog 2A Phase 5 close-out — undo/redo history. Every successful
  // mutation calls _scheduleSave(), so we hook the history push here:
  // each save pushes a deep clone of the post-mutation state. Undo
  // moves the cursor back and restores the prior snapshot; redo moves
  // it forward. Capped at 50 entries so memory stays bounded.
  var _history = [];
  var _historyCursor = -1;
  var HISTORY_CAP = 50;

  function _pushHistory() {
    if (!_state) return;
    if (_historyCursor < _history.length - 1) {
      _history.length = _historyCursor + 1;
    }
    _history.push(JSON.parse(JSON.stringify(_state)));
    _historyCursor = _history.length - 1;
    if (_history.length > HISTORY_CAP) {
      _history.shift();
      _historyCursor--;
    }
  }

  function _undo() {
    if (_historyCursor <= 0) return;
    _historyCursor--;
    _state = JSON.parse(JSON.stringify(_history[_historyCursor]));
    _selectedClipId = null;
    _selectedTrackId = null;
    _secondarySelection.clear();
    if (_saveDebounce) { try { clearTimeout(_saveDebounce); } catch (e) {} }
    _saveDebounce = setTimeout(_saveStateNow, 250);
    _render();
  }

  function _redo() {
    if (_historyCursor >= _history.length - 1) return;
    _historyCursor++;
    _state = JSON.parse(JSON.stringify(_history[_historyCursor]));
    _selectedClipId = null;
    _selectedTrackId = null;
    _secondarySelection.clear();
    if (_saveDebounce) { try { clearTimeout(_saveDebounce); } catch (e) {} }
    _saveDebounce = setTimeout(_saveStateNow, 250);
    _render();
  }

  function _scheduleSave() {
    _pushHistory();
    if (_saveDebounce) {
      try { clearTimeout(_saveDebounce); } catch (e) { /* ignore */ }
    }
    _saveDebounce = setTimeout(_saveStateNow, 250);
  }

  function _saveStateNow() {
    _saveDebounce = null;
    if (!_conversationId || !_state) return;
    fetch('/api/timeline/' + encodeURIComponent(_conversationId), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_state),
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j && j.timeline) {
          _state = j.timeline;
          _render();
          // Tell the preview monitor (and any other listeners) that the
          // server-confirmed timeline changed — they invalidate caches
          // accordingly.
          document.dispatchEvent(new CustomEvent('ora:timeline-mutated', {
            detail: { conversation_id: _conversationId },
          }));
        }
      })
      .catch(function () { /* leave local state in place */ });
  }

  // Dispatch a playhead-changed event so subscribers (preview monitor)
  // can react. `source` distinguishes user-driven changes ('scrub',
  // 'split', 'preview') so each receiver can avoid feedback loops.
  function _emitPlayheadChanged(source) {
    if (!_state) return;
    document.dispatchEvent(new CustomEvent('ora:timeline-playhead-changed', {
      detail: {
        conversation_id: _conversationId,
        playhead_ms: _state.playhead_ms || 0,
        source: source || 'unknown',
      },
    }));
  }

  // ── DOM build ────────────────────────────────────────────────────────────

  function _build() {
    if (_editorEl) return _editorEl;
    var el = document.createElement('div');
    el.className = 'timeline-editor';
    el.innerHTML = ''
      + '<div class="timeline-editor__ruler-row">'
      +   '<div class="timeline-editor__timecode-cluster">'
      +     '<span class="timeline-editor__timecode" data-role="timecode" aria-live="polite">00:00:00:00</span>'
      +     '<span class="timeline-editor__sep">/</span>'
      +     '<span class="timeline-editor__total-duration" data-role="total-duration">00:00:00</span>'
      +   '</div>'
      +   '<div class="timeline-editor__zoom">'
      +     '<button type="button" class="timeline-editor__icon-btn" data-role="zoom-out" aria-label="Zoom out" title="Zoom out">−</button>'
      +     '<button type="button" class="timeline-editor__icon-btn" data-role="zoom-in"  aria-label="Zoom in"  title="Zoom in">+</button>'
      +   '</div>'
      +   '<div class="timeline-editor__track-control">'
      +     '<button type="button" class="timeline-editor__icon-btn timeline-editor__watermark-btn" '
      +       'data-role="watermark" aria-label="Watermark" title="Watermark settings">◎</button>'
      +     '<button type="button" class="timeline-editor__add-track" data-role="add-track" aria-label="Add track" title="Add track">+ Track</button>'
      +   '</div>'
      + '</div>'
      + '<div class="timeline-editor__viewport" data-role="viewport">'
      +   '<div class="timeline-editor__ruler" data-role="ruler"></div>'
      +   '<div class="timeline-editor__tracks" data-role="tracks"></div>'
      +   '<div class="timeline-editor__playhead" data-role="playhead" aria-hidden="true"></div>'
      + '</div>'
      + '<div class="timeline-editor__hint" data-role="hint">Drop a clip from the media library onto a track to begin. Press <kbd>S</kbd> to split at the playhead, <kbd>Delete</kbd> to remove the selected clip.</div>';
    _editorEl = el;
    _viewportEl = el.querySelector('[data-role="viewport"]');
    _tracksEl = el.querySelector('[data-role="tracks"]');
    _rulerEl = el.querySelector('[data-role="ruler"]');
    _playheadEl = el.querySelector('[data-role="playhead"]');
    _wireChrome();
    return el;
  }

  function _wireChrome() {
    var btnZoomIn  = _editorEl.querySelector('[data-role="zoom-in"]');
    var btnZoomOut = _editorEl.querySelector('[data-role="zoom-out"]');
    var btnAdd     = _editorEl.querySelector('[data-role="add-track"]');
    btnZoomIn.addEventListener('click', function () { _zoom(1.5); });
    btnZoomOut.addEventListener('click', function () { _zoom(1 / 1.5); });
    btnAdd.addEventListener('click', _openTrackPicker);
    _wireWatermarkButton();

    // Scroll wheel on viewport zooms (Cmd/Ctrl held) or scrolls horizontally.
    _viewportEl.addEventListener('wheel', function (e) {
      if (e.metaKey || e.ctrlKey) {
        e.preventDefault();
        _zoom(e.deltaY < 0 ? 1.15 : (1 / 1.15));
      }
    });

    // Ruler scrubbing: click or drag on ruler positions the playhead.
    var scrubbing = false;
    var onScrubMove = function (e) {
      if (!scrubbing) return;
      var rect = _rulerEl.getBoundingClientRect();
      var x = e.clientX - rect.left + _viewportEl.scrollLeft;
      _state.playhead_ms = Math.max(0, Math.round(_pxToMs(x)));
      _renderPlayhead();
      _renderTimecode();
      _emitPlayheadChanged('scrub');
    };
    var onScrubUp = function () {
      if (!scrubbing) return;
      scrubbing = false;
      _scheduleSave();
      document.removeEventListener('mousemove', onScrubMove);
      document.removeEventListener('mouseup', onScrubUp);
    };
    _rulerEl.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      scrubbing = true;
      onScrubMove(e);
      document.addEventListener('mousemove', onScrubMove);
      document.addEventListener('mouseup', onScrubUp);
    });

    // Document keydown: Split (S) and Delete.
    document.addEventListener('keydown', _onKeydown);

    // Outside click closes the context menu.
    document.addEventListener('click', function (e) {
      if (_ctxMenuEl && !e.target.closest('.timeline-editor__ctx-menu')) {
        _closeContextMenu();
      }
    }, true);
  }

  function _zoom(factor) {
    if (!_state) return;
    var z = _state.zoom_pixels_per_ms * factor;
    z = Math.max(0.005, Math.min(2.0, z));
    _state.zoom_pixels_per_ms = z;
    _scheduleSave();
    _render();
  }

  function _onKeydown(e) {
    if (!document.body.classList.contains('pane-mode-video')) return;
    if (!_editorEl || !_editorEl.classList.contains('timeline-editor--visible')) return;
    // Don't intercept while user types in an input field.
    var tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

    var key = (e.key || '').toLowerCase();
    var meta = e.metaKey || e.ctrlKey;

    // V3 Backlog 2A Phase 5 close-out — undo / redo on Cmd+Z and Cmd+Shift+Z
    // (Ctrl+Z / Ctrl+Shift+Z on Windows/Linux). History is pushed on every
    // mutation via _scheduleSave; undo/redo walks the cursor.
    if (meta && key === 'z') {
      e.preventDefault();
      if (e.shiftKey) _redo(); else _undo();
      return;
    }

    // V3 Backlog 2A Phase 5 close-out — duplicate (Cmd+D) + copy/paste
    // (Cmd+C / Cmd+V). Operates on the currently-selected clip.
    if (meta && key === 'd' && _selectedClipId) {
      e.preventDefault();
      _duplicateSelected();
      return;
    }
    if (meta && key === 'c' && _selectedClipId) {
      e.preventDefault();
      _copySelected();
      return;
    }
    if (meta && key === 'v') {
      e.preventDefault();
      _pasteAtPlayhead();
      return;
    }

    if (key === 's') {
      e.preventDefault();
      _splitSelectedAtPlayhead();
    } else if (key === 'delete' || key === 'backspace') {
      if (_selectedClipId) {
        e.preventDefault();
        _deleteSelected();
      }
    }
  }

  // V3 Backlog 2A Phase 5 close-out — clipboard for clip copy/paste/dup.
  // The clipboard holds a deep-cloned clip + its source-track id. Paste
  // inserts a fresh-id copy on the same track at the playhead. Duplicate
  // is shorthand: paste-immediately to the right of the original on the
  // same track.
  var _clipboardClip = null;
  var _clipboardTrackId = null;

  function _copySelected() {
    if (!_selectedClipId || !_selectedTrackId) return;
    var clip = _findClip(_selectedTrackId, _selectedClipId);
    if (!clip) return;
    _clipboardClip   = JSON.parse(JSON.stringify(clip));
    _clipboardTrackId = _selectedTrackId;
  }

  function _pasteAtPlayhead() {
    if (!_clipboardClip) return;
    var t = _findTrack(_clipboardTrackId);
    if (!t) return; // source track gone
    var newClip = JSON.parse(JSON.stringify(_clipboardClip));
    newClip.id = 'clip-' + (Date.now().toString(36)) + '-' + Math.floor(Math.random() * 1e6).toString(36);
    newClip.track_position_ms = Math.max(0, _state.playhead_ms);
    t.clips.push(newClip);
    _scheduleSave();
    _render();
    _select(_clipboardTrackId, newClip.id);
  }

  function _duplicateSelected() {
    var targets = _allSelectedClips();
    if (!targets.length) return;
    // V3 Backlog 2A Phase 5 close-out — multi-clip duplicate. Each
    // selected clip is cloned with a fresh id and placed immediately
    // to the right of the original on the same track. Selection
    // shifts to the cloned clips so a follow-up duplicate keeps stamping.
    var newPrimary = null;
    var newSecondary = new Map();
    targets.forEach(function (sel, idx) {
      var t = _findTrack(sel.trackId);
      var clip = _findClip(sel.trackId, sel.clipId);
      if (!t || !clip) return;
      var newClip = JSON.parse(JSON.stringify(clip));
      newClip.id = 'clip-' + (Date.now().toString(36)) + '-' + idx + '-' + Math.floor(Math.random() * 1e6).toString(36);
      var clipLen = clip.out_point_ms - clip.in_point_ms;
      newClip.track_position_ms = clip.track_position_ms + clipLen;
      t.clips.push(newClip);
      if (newPrimary == null) {
        newPrimary = { trackId: sel.trackId, clipId: newClip.id };
      } else {
        newSecondary.set(newClip.id, { trackId: sel.trackId });
      }
    });
    _scheduleSave();
    _render();
    if (newPrimary) {
      _selectedTrackId = newPrimary.trackId;
      _selectedClipId  = newPrimary.clipId;
      _secondarySelection = newSecondary;
      _select(newPrimary.trackId, newPrimary.clipId, { additive: false });
      // Re-apply secondaries (the additive=false call cleared them).
      newSecondary.forEach(function (v, k) {
        _secondarySelection.set(k, v);
      });
      _select(newPrimary.trackId, newPrimary.clipId, { additive: true });
      // Cleanup: the toggle above flipped newPrimary out of secondary —
      // restore the rendering loop so all new clips highlight.
      Array.from(_editorEl.querySelectorAll('.timeline-editor__clip')).forEach(function (el) {
        var cid = el.dataset.clipId;
        el.classList.toggle('is-selected',
          cid === _selectedClipId || _secondarySelection.has(cid));
      });
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  function _render() {
    if (!_state || !_editorEl) return;

    // Total duration display.
    var totalEl = _editorEl.querySelector('[data-role="total-duration"]');
    if (totalEl) totalEl.textContent = _formatTimecode(_state.duration_ms, false);
    _renderTimecode();

    // Ruler width: at least viewport width, else longest content + 1s.
    var contentWidthMs = Math.max(_state.duration_ms + 5000, 60000); // ≥ 60s of canvas
    var contentWidthPx = _msToPx(contentWidthMs);
    _rulerEl.style.width = contentWidthPx + 'px';
    _tracksEl.style.minWidth = contentWidthPx + 'px';

    _renderRuler(contentWidthPx);
    _renderTracks();
    _renderPlayhead();
    _renderWatermarkButton();
  }

  function _renderTimecode() {
    if (!_state || !_editorEl) return;
    var tcEl = _editorEl.querySelector('[data-role="timecode"]');
    if (tcEl) tcEl.textContent = _formatTimecode(_state.playhead_ms || 0, true);
  }

  function _renderRuler(contentWidthPx) {
    _rulerEl.innerHTML = '';
    // Pick a tick interval such that ticks are ≥ 60 px apart.
    var minPx = 60;
    var pxPerMs = _state.zoom_pixels_per_ms;
    var candidates = [100, 250, 500, 1000, 2000, 5000, 10000, 30000, 60000, 120000];
    var stepMs = candidates.find(function (c) { return c * pxPerMs >= minPx; }) || 60000;
    for (var t = 0; t < contentWidthPx / pxPerMs; t += stepMs) {
      var tick = document.createElement('div');
      tick.className = 'timeline-editor__tick';
      tick.style.left = _msToPx(t) + 'px';
      tick.textContent = _formatTimecode(t, false);
      _rulerEl.appendChild(tick);
    }
  }

  function _renderTracks() {
    _tracksEl.innerHTML = '';
    _state.tracks.forEach(function (track) {
      var trackEl = document.createElement('div');
      trackEl.className = 'timeline-editor__track';
      trackEl.dataset.trackId = track.id;
      trackEl.dataset.kind = track.kind;

      var header = document.createElement('div');
      header.className = 'timeline-editor__track-header';
      var addOverlayBtn = (track.kind === 'overlay')
        ? '<button type="button" class="timeline-editor__track-add-overlay" '
        +   'aria-label="Add overlay" title="Add overlay (lower-third or title card)">+</button>'
        : '';
      // V3 Backlog 2A Phase 5 close-out — mute toggle on audio-bearing
      // tracks. Visible only for kinds that carry sound (video / audio /
      // pip / music). Overlay tracks are silent so the button is hidden.
      var hasAudio = (track.kind === 'video' || track.kind === 'audio'
                      || track.kind === 'pip' || track.kind === 'music');
      var muteBtn = hasAudio
        ? '<button type="button" class="timeline-editor__track-mute" '
        +   'aria-label="Mute track" title="Mute / unmute"'
        +   ' aria-pressed="' + (track.muted ? 'true' : 'false') + '">'
        +   (track.muted ? '🔇' : '🔊')
        +  '</button>'
        : '';
      header.innerHTML = ''
        + '<span class="timeline-editor__track-kind" data-kind="' + track.kind + '">'
        +   _trackKindGlyph(track.kind)
        + '</span>'
        + '<span class="timeline-editor__track-label">' + (track.label || track.kind) + '</span>'
        + muteBtn
        + addOverlayBtn
        + '<button type="button" class="timeline-editor__track-remove" '
        +   'aria-label="Remove track" title="Remove track">×</button>';
      header.querySelector('.timeline-editor__track-remove').addEventListener('click', function () {
        _removeTrack(track.id);
      });
      var muteEl = header.querySelector('.timeline-editor__track-mute');
      if (muteEl) {
        muteEl.addEventListener('click', function (e) {
          e.stopPropagation();
          track.muted = !track.muted;
          _scheduleSave();
          _render();
        });
      }
      var addOvBtn = header.querySelector('.timeline-editor__track-add-overlay');
      if (addOvBtn) {
        addOvBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          _openAddOverlayPicker(track.id, addOvBtn);
        });
      }
      trackEl.appendChild(header);
      if (track.muted) trackEl.classList.add('is-muted');

      var lane = document.createElement('div');
      lane.className = 'timeline-editor__track-lane';
      lane.dataset.trackId = track.id;
      // Drop target for media-library drags AND for moving clips.
      lane.addEventListener('dragover', function (e) {
        if (e.dataTransfer && (
              e.dataTransfer.types.includes('application/x-ora-media-entry') ||
              e.dataTransfer.types.includes('application/x-ora-clip-id'))) {
          e.preventDefault();
          e.dataTransfer.dropEffect = 'copy';
        }
      });
      lane.addEventListener('drop', function (e) {
        var rect = lane.getBoundingClientRect();
        var x = e.clientX - rect.left + _viewportEl.scrollLeft;
        var dropMs = Math.max(0, Math.round(_pxToMs(x)));
        var entryId = e.dataTransfer.getData('application/x-ora-media-entry');
        var clipMove = e.dataTransfer.getData('application/x-ora-clip-id');
        if (entryId) {
          e.preventDefault();
          // V3 Backlog 2A Phase 5 close-out — snap to nearest clip edge
          // on this track within ~10px so new clips align cleanly with
          // existing material.
          dropMs = _snapToClipEdge(track.id, dropMs, null);
          _addClipFromLibrarySafely(track.id, entryId, dropMs);
        } else if (clipMove) {
          // Move existing clip to this track at dropMs.
          e.preventDefault();
          var parts = clipMove.split('|');
          dropMs = _snapToClipEdge(track.id, dropMs, parts[1] /* exclude self */);
          _moveClipToTrack(parts[0], parts[1], track.id, dropMs);
        }
      });

      // Render clips
      track.clips.forEach(function (clip) {
        var clipEl = _buildClipEl(track, clip);
        lane.appendChild(clipEl);
      });

      trackEl.appendChild(lane);
      _tracksEl.appendChild(trackEl);
    });
  }

  function _trackKindGlyph(kind) {
    if (kind === 'video')   return 'V';
    if (kind === 'audio')   return 'A';
    if (kind === 'pip')     return 'P';
    if (kind === 'music')   return 'M';
    if (kind === 'overlay') return 'T';
    return '·';
  }

  function _overlayTypeGlyph(overlayType) {
    if (overlayType === 'title-card')  return '⊟';
    if (overlayType === 'lower-third') return '⌃';
    if (overlayType === 'watermark')   return '◎';
    return 'T';
  }

  function _buildClipEl(track, clip) {
    var clipEl = document.createElement('div');
    clipEl.className = 'timeline-editor__clip';
    clipEl.dataset.kind = track.kind;
    clipEl.dataset.clipId = clip.id;
    clipEl.dataset.trackId = track.id;
    if (clip.overlay_type) clipEl.dataset.overlayType = clip.overlay_type;
    clipEl.draggable = true;
    var leftPx = _msToPx(clip.track_position_ms);
    var widthPx = Math.max(8, _msToPx(clip.out_point_ms - clip.in_point_ms));
    clipEl.style.left = leftPx + 'px';
    clipEl.style.width = widthPx + 'px';
    if (clip.id === _selectedClipId) clipEl.classList.add('is-selected');

    var label = _clipDisplayLabel(clip);
    var bodyHtml;
    if (clip.overlay_type) {
      bodyHtml = ''
        + '<div class="timeline-editor__clip-body">'
        +   '<span class="timeline-editor__clip-overlay-glyph">' + _overlayTypeGlyph(clip.overlay_type) + '</span>'
        +   '<span class="timeline-editor__clip-label">' + label + '</span>'
        +   '<span class="timeline-editor__clip-tin"  data-trans-in="' + clip.transition_in + '" title="In: ' + clip.transition_in + '"></span>'
        +   '<span class="timeline-editor__clip-tout" data-trans-out="' + clip.transition_out + '" title="Out: ' + clip.transition_out + '"></span>'
        + '</div>';
    } else {
      bodyHtml = ''
        + '<div class="timeline-editor__clip-body">'
        +   '<span class="timeline-editor__clip-label">' + label + '</span>'
        +   '<span class="timeline-editor__clip-tin"  data-trans-in="' + clip.transition_in + '" title="In: ' + clip.transition_in + '"></span>'
        +   '<span class="timeline-editor__clip-tout" data-trans-out="' + clip.transition_out + '" title="Out: ' + clip.transition_out + '"></span>'
        + '</div>';
    }

    // V3 Backlog 2A Phase 5 close-out — fade-handle drags. Render two
    // small grippable handles inside the clip body at the current fade
    // boundary positions; drag inward to extend the fade, outward to
    // shorten. Handles only render for non-overlay clips (overlay
    // fades use the inspector's numeric fields). When fade_in_ms /
    // fade_out_ms is 0 the handle sits at the clip edge — visually
    // discoverable but inert until dragged inward.
    var fadeHandlesHtml = '';
    if (!clip.overlay_type) {
      var pxPerMs = _state.zoom_pixels_per_ms;
      var fInPx  = Math.max(0, Math.min(widthPx - 4, Math.round((clip.fade_in_ms  || 0) * pxPerMs)));
      var fOutPx = Math.max(0, Math.min(widthPx - 4, Math.round((clip.fade_out_ms || 0) * pxPerMs)));
      fadeHandlesHtml = ''
        + '<div class="timeline-editor__clip-fade-handle" '
        +     'data-fade="in"  style="left:' + fInPx + 'px;"></div>'
        + '<div class="timeline-editor__clip-fade-handle" '
        +     'data-fade="out" style="right:' + fOutPx + 'px;"></div>';
    }

    clipEl.innerHTML = ''
      + '<div class="timeline-editor__clip-edge" data-edge="left"></div>'
      + bodyHtml
      + fadeHandlesHtml
      + '<div class="timeline-editor__clip-edge" data-edge="right"></div>';

    clipEl.addEventListener('mousedown', function (e) {
      if (e.target.classList.contains('timeline-editor__clip-edge')) {
        _beginTrim(clip, track.id, e.target.dataset.edge, e);
        return;
      }
      // V3 Backlog 2A Phase 5 close-out — fade-handle drag. Each handle
      // sets fade_in_ms (left) or fade_out_ms (right) by translating
      // pointer movement to a ms value at the current zoom.
      if (e.target.classList.contains('timeline-editor__clip-fade-handle')) {
        _beginFadeDrag(clip, track.id, e.target.dataset.fade, e);
        return;
      }
      // V3 Backlog 2A Phase 5 close-out — Shift+click extends selection
      // to multiple clips. Plain click clears any extension.
      _select(track.id, clip.id, { additive: e.shiftKey });
    });
    // Phase 6: double-click on an overlay clip opens the inspector.
    if (clip.overlay_type) {
      clipEl.addEventListener('dblclick', function (e) {
        e.preventDefault();
        _openOverlayInspector(track.id, clip.id);
      });
    }
    clipEl.addEventListener('dragstart', function (e) {
      if (!e.dataTransfer) return;
      e.dataTransfer.effectAllowed = 'copy';
      e.dataTransfer.setData('application/x-ora-clip-id', track.id + '|' + clip.id);
    });
    clipEl.addEventListener('contextmenu', function (e) {
      e.preventDefault();
      _openContextMenu(track.id, clip.id, e.clientX, e.clientY);
    });
    return clipEl;
  }

  function _clipDisplayLabel(clip) {
    if (clip.overlay_type) {
      var content = clip.overlay_content || {};
      var text = (content.text || '').trim();
      if (!text) {
        if (clip.overlay_type === 'title-card')  text = 'Title';
        else if (clip.overlay_type === 'lower-third') text = 'Lower-third';
        else text = clip.overlay_type;
      }
      return text.length > 36 ? text.substring(0, 34) + '…' : text;
    }
    var entry = _libraryEntriesCache[clip.media_entry_id];
    var name = (entry && entry.display_name) || clip.media_entry_id || 'clip';
    return name.length > 40 ? name.substring(0, 38) + '…' : name;
  }

  function _renderPlayhead() {
    if (!_playheadEl || !_state) return;
    _playheadEl.style.left = _msToPx(_state.playhead_ms || 0) + 'px';
  }

  // ── Mutations ────────────────────────────────────────────────────────────

  function _select(trackId, clipId, opts) {
    opts = opts || {};
    if (opts.additive) {
      // V3 Backlog 2A Phase 5 close-out — Shift+click toggle. If the
      // shift-clicked clip is already primary, demote nothing (no-op).
      // If it's already in the secondary set, remove it. Otherwise add.
      if (clipId === _selectedClipId) return;
      if (_secondarySelection.has(clipId)) {
        _secondarySelection.delete(clipId);
      } else {
        _secondarySelection.set(clipId, { trackId: trackId });
      }
    } else {
      _selectedTrackId = trackId;
      _selectedClipId = clipId;
      _secondarySelection.clear();
    }
    var primary = _selectedClipId;
    var secondary = _secondarySelection;
    Array.from(_editorEl.querySelectorAll('.timeline-editor__clip')).forEach(function (el) {
      var cid = el.dataset.clipId;
      el.classList.toggle('is-selected', cid === primary || secondary.has(cid));
    });
    // Phase 6 follow-up (drag-to-position) — broadcast selected overlay so
    // preview-monitor can render a draggable handle on the preview stage.
    // Only fires for primary selection of a positionable overlay (lower-
    // third). Title cards fill the frame; watermarks use corner anchors.
    _broadcastOverlaySelection();
  }

  function _broadcastOverlaySelection() {
    if (typeof document === 'undefined') return;
    var detail = null;
    if (_selectedTrackId && _selectedClipId) {
      var clip = _findClip(_selectedTrackId, _selectedClipId);
      if (clip && clip.overlay_type === 'lower-third') {
        var content = clip.overlay_content || {};
        var pos = content.position || {};
        detail = {
          trackId:      _selectedTrackId,
          clipId:       _selectedClipId,
          overlay_type: clip.overlay_type,
          position: {
            x_pct:     typeof pos.x_pct === 'number'     ? pos.x_pct     : 0.5,
            y_pct:     typeof pos.y_pct === 'number'     ? pos.y_pct     : 0.85,
            width_pct: typeof pos.width_pct === 'number' ? pos.width_pct : 0.5,
          }
        };
      }
    }
    try {
      document.dispatchEvent(new CustomEvent('ora:overlay-selected',
        { detail: detail }));
    } catch (e) { /* no DOM in tests — fine */ }
  }

  // V3 Backlog 2A Phase 5 close-out — bulk-op convenience. Returns an
  // array of {trackId, clipId} for every selected clip (primary + all
  // shift-extended secondaries). Order: primary first, then secondaries
  // in insertion order so consistent across calls.
  function _allSelectedClips() {
    var out = [];
    if (_selectedClipId && _selectedTrackId) {
      out.push({ trackId: _selectedTrackId, clipId: _selectedClipId });
    }
    _secondarySelection.forEach(function (v, k) {
      out.push({ trackId: v.trackId, clipId: k });
    });
    return out;
  }

  function _addClipFromLibrary(trackId, entryId, positionMs) {
    var entry = _libraryEntriesCache[entryId];
    var dur = (entry && entry.duration_ms) || 5000;
    var clip = {
      id: 'clip-' + (Date.now().toString(36)) + '-' + Math.floor(Math.random() * 1e6).toString(36),
      media_entry_id: entryId,
      track_position_ms: positionMs,
      in_point_ms: 0,
      out_point_ms: dur,
      transition_in: 'cut',
      transition_out: 'cut',
      transition_duration_ms: 500,
      volume: 1.0,
      fade_in_ms: 0,
      fade_out_ms: 0,
    };
    var t = _findTrack(trackId);
    if (!t) return;
    t.clips.push(clip);
    _scheduleSave();
    _render();
  }

  function _moveClipToTrack(srcTrackId, clipId, dstTrackId, positionMs) {
    var src = _findTrack(srcTrackId);
    var dst = _findTrack(dstTrackId);
    if (!src || !dst) return;
    var idx = src.clips.findIndex(function (c) { return c.id === clipId; });
    if (idx < 0) return;
    var clip = src.clips.splice(idx, 1)[0];
    clip.track_position_ms = Math.max(0, positionMs);
    dst.clips.push(clip);
    _scheduleSave();
    _render();
  }

  // V3 Backlog 2A Phase 5 close-out — fade-handle drag. Drag the left
  // handle inward to extend fade-in; drag the right handle inward to
  // extend fade-out. Drag back outward to shorten. Capped to the clip's
  // current track-length so a fade can never overflow its clip.
  function _beginFadeDrag(clip, trackId, edge, downEvent) {
    downEvent.preventDefault();
    downEvent.stopPropagation();
    var startX  = downEvent.clientX;
    var origIn  = clip.fade_in_ms  || 0;
    var origOut = clip.fade_out_ms || 0;
    var pxPerMs = _state.zoom_pixels_per_ms;
    var clipLen = clip.out_point_ms - clip.in_point_ms;

    function onMove(e) {
      var dx = e.clientX - startX;
      var dms = Math.round(dx / pxPerMs);
      if (edge === 'in') {
        clip.fade_in_ms  = Math.max(0, Math.min(clipLen, origIn + dms));
      } else {
        // Right-handle: dragging LEFT (negative dx) extends fade-out
        // since the handle uses CSS `right:` positioning.
        clip.fade_out_ms = Math.max(0, Math.min(clipLen, origOut - dms));
      }
      _render();
    }
    function onUp() {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      _scheduleSave();
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  function _beginTrim(clip, trackId, edge, downEvent) {
    downEvent.preventDefault();
    downEvent.stopPropagation();
    var startX = downEvent.clientX;
    var origIn = clip.in_point_ms;
    var origOut = clip.out_point_ms;
    var origPos = clip.track_position_ms;
    var pxPerMs = _state.zoom_pixels_per_ms;

    function onMove(e) {
      var dx = e.clientX - startX;
      var dms = Math.round(dx / pxPerMs);
      if (edge === 'left') {
        var newIn = Math.max(0, Math.min(origOut - 100, origIn + dms));
        var deltaTrim = newIn - origIn;
        clip.in_point_ms = newIn;
        clip.track_position_ms = Math.max(0, origPos + deltaTrim);
      } else {
        clip.out_point_ms = Math.max(origIn + 100, origOut + dms);
      }
      _render();
    }
    function onUp() {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      _scheduleSave();
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  function _splitSelectedAtPlayhead() {
    if (!_selectedClipId || !_selectedTrackId) return;
    var t = _findTrack(_selectedTrackId);
    var clip = _findClip(_selectedTrackId, _selectedClipId);
    if (!t || !clip) return;
    var ph = _state.playhead_ms;
    var clipStart = clip.track_position_ms;
    var clipLength = clip.out_point_ms - clip.in_point_ms;
    var clipEnd = clipStart + clipLength;
    if (ph <= clipStart || ph >= clipEnd) return;  // playhead outside this clip

    var splitOffset = ph - clipStart;
    var newClip = JSON.parse(JSON.stringify(clip));
    newClip.id = 'clip-' + (Date.now().toString(36)) + '-' + Math.floor(Math.random() * 1e6).toString(36);
    // First half: end at split point.
    clip.out_point_ms = clip.in_point_ms + splitOffset;
    clip.transition_out = 'cut';
    // Second half: start at split point, retains original out.
    newClip.in_point_ms = clip.out_point_ms;
    newClip.track_position_ms = ph;
    newClip.transition_in = 'cut';
    t.clips.push(newClip);
    _scheduleSave();
    _render();
  }

  function _deleteSelected() {
    var targets = _allSelectedClips();
    if (!targets.length) return;
    // V3 Backlog 2A Phase 5 close-out — ripple delete + multi-select. For
    // each selected clip we compute its track-length (so we can ripple
    // its track) and remove it. Ripple math runs per-track, scoped to
    // clips that survive the delete pass — order-of-operations doesn't
    // matter because we batch the removal first.
    var deletedByTrack = {};      // trackId → [{ deletedEnd, deletedLen }]
    targets.forEach(function (sel) {
      var clip = _findClip(sel.trackId, sel.clipId);
      if (!clip) return;
      var len = (clip.out_point_ms - clip.in_point_ms) || 0;
      var end = clip.track_position_ms + len;
      (deletedByTrack[sel.trackId] = deletedByTrack[sel.trackId] || []).push({
        deletedEnd: end,
        deletedLen: len,
      });
    });
    var deletedClipIds = {};
    targets.forEach(function (sel) { deletedClipIds[sel.clipId] = true; });

    Object.keys(deletedByTrack).forEach(function (trackId) {
      var t = _findTrack(trackId);
      if (!t) return;
      // Sort deletions by track-end ascending so each survivor's ripple
      // shift is the cumulative length of deletions strictly before it.
      var dels = deletedByTrack[trackId].slice().sort(function (a, b) {
        return a.deletedEnd - b.deletedEnd;
      });
      t.clips.forEach(function (c) {
        if (deletedClipIds[c.id]) return;
        var cumShift = 0;
        for (var i = 0; i < dels.length; i++) {
          if (c.track_position_ms >= dels[i].deletedEnd) cumShift += dels[i].deletedLen;
          else break;
        }
        if (cumShift) c.track_position_ms = Math.max(0, c.track_position_ms - cumShift);
      });
      t.clips = t.clips.filter(function (c) { return !deletedClipIds[c.id]; });
    });

    _selectedClipId = null;
    _selectedTrackId = null;
    _secondarySelection.clear();
    _scheduleSave();
    _render();
  }

  // ── Track add / remove ──────────────────────────────────────────────────

  function _openTrackPicker() {
    if (_ctxMenuEl) _closeContextMenu();
    var menu = document.createElement('div');
    menu.className = 'timeline-editor__ctx-menu';
    menu.innerHTML = ''
      + '<div class="timeline-editor__ctx-menu-title">Add track</div>'
      + '<button type="button" data-kind="video">Video track</button>'
      + '<button type="button" data-kind="audio">Audio track</button>'
      + '<button type="button" data-kind="pip">Picture-in-picture</button>'
      + '<button type="button" data-kind="music">Music / ambient</button>'
      + '<button type="button" data-kind="overlay">Overlays (text + title cards)</button>';
    document.body.appendChild(menu);
    _ctxMenuEl = menu;
    var btn = _editorEl.querySelector('[data-role="add-track"]');
    var btnRect = btn.getBoundingClientRect();
    menu.style.left = (btnRect.left) + 'px';
    menu.style.top  = (btnRect.bottom + 4) + 'px';
    Array.from(menu.querySelectorAll('button[data-kind]')).forEach(function (b) {
      b.addEventListener('click', function () {
        _addTrack(b.dataset.kind);
        _closeContextMenu();
      });
    });
  }

  function _addTrack(kind) {
    var labelMap = { video: 'Video', audio: 'Audio', pip: 'PiP', music: 'Music', overlay: 'Overlays' };
    _state.tracks.push({
      id: 'track-' + (Date.now().toString(36)) + '-' + Math.floor(Math.random() * 1e6).toString(36),
      kind: kind,
      label: labelMap[kind] || kind,
      muted: false,
      clips: [],
    });
    _scheduleSave();
    _render();
  }

  // Phase 6: add an overlay clip to a specific overlay-kind track at the
  // current playhead. The clip carries default content for its type;
  // the user opens the inspector to refine.
  function _addOverlayClip(trackId, overlayType) {
    var t = _findTrack(trackId);
    if (!t || t.kind !== 'overlay') return;
    var defaults = {
      'lower-third': { duration_ms: 4000, text: 'Lower-third caption' },
      'title-card':  { duration_ms: 3000, text: 'Title' },
      'watermark':   { duration_ms: _state.duration_ms || 60000, text: '◎' },
    };
    var d = defaults[overlayType] || defaults['lower-third'];
    var ph = _state.playhead_ms || 0;
    var clip = {
      id: 'clip-' + (Date.now().toString(36)) + '-' + Math.floor(Math.random() * 1e6).toString(36),
      overlay_type: overlayType,
      track_position_ms: ph,
      in_point_ms: 0,
      out_point_ms: d.duration_ms,
      transition_in: 'cut',
      transition_out: 'cut',
      transition_duration_ms: 500,
      volume: 1.0,
      fade_in_ms: 0,
      fade_out_ms: 0,
      overlay_content: { text: d.text },
    };
    t.clips.push(clip);
    _selectedClipId = clip.id;
    _selectedTrackId = trackId;
    _scheduleSave();
    _render();
    _openOverlayInspector(trackId, clip.id);
  }

  function _openAddOverlayPicker(trackId, anchorEl) {
    if (_ctxMenuEl) _closeContextMenu();
    var menu = document.createElement('div');
    menu.className = 'timeline-editor__ctx-menu';
    menu.innerHTML = ''
      + '<div class="timeline-editor__ctx-menu-title">Add overlay at playhead</div>'
      + '<button type="button" data-overlay="lower-third">Lower-third / subtitle</button>'
      + '<button type="button" data-overlay="title-card">Title card</button>'
      + '<button type="button" data-overlay="watermark">Time-ranged watermark</button>';
    document.body.appendChild(menu);
    _ctxMenuEl = menu;
    var rect = anchorEl.getBoundingClientRect();
    menu.style.left = rect.left + 'px';
    menu.style.top  = (rect.bottom + 4) + 'px';
    Array.from(menu.querySelectorAll('button[data-overlay]')).forEach(function (b) {
      b.addEventListener('click', function () {
        _addOverlayClip(trackId, b.dataset.overlay);
        _closeContextMenu();
      });
    });
  }

  function _removeTrack(trackId) {
    _state.tracks = _state.tracks.filter(function (t) { return t.id !== trackId; });
    if (_selectedTrackId === trackId) {
      _selectedTrackId = null;
      _selectedClipId = null;
    }
    _scheduleSave();
    _render();
  }

  // ── Right-click context menu (transitions) ──────────────────────────────

  function _openContextMenu(trackId, clipId, x, y) {
    _closeContextMenu();
    _select(trackId, clipId);
    var clip = _findClip(trackId, clipId);
    if (!clip) return;
    var menu = document.createElement('div');
    menu.className = 'timeline-editor__ctx-menu';
    // V3 Backlog 2A Phase 5 close-out — per-clip volume slider on the
    // context menu for non-overlay clips. Volume is stored on the clip
    // (default 1.0 from _addClipFromLibrary); overlay clips don't carry
    // sound so they use the existing fade-only inspector instead.
    var volumePct = Math.round(((clip.volume == null ? 1.0 : clip.volume) * 100));
    var volumeSection = clip.overlay_type
      ? ''
      : '<div class="timeline-editor__ctx-menu-section">'
      +   '<span class="timeline-editor__ctx-menu-label">Volume</span>'
      +   '<input type="range" class="timeline-editor__ctx-menu-volume" '
      +     'min="0" max="200" step="1" value="' + volumePct + '" '
      +     'aria-label="Clip volume" />'
      +   '<span class="timeline-editor__ctx-menu-volume-readout">' + volumePct + '%</span>'
      + '</div>';
    menu.innerHTML = ''
      + '<div class="timeline-editor__ctx-menu-title">Clip</div>'
      + volumeSection
      + '<div class="timeline-editor__ctx-menu-section">'
      +   '<span class="timeline-editor__ctx-menu-label">In</span>'
      +   '<button data-tin="cut">Cut</button>'
      +   '<button data-tin="dissolve">Dissolve</button>'
      +   '<button data-tin="fade-from-black">Fade from black</button>'
      + '</div>'
      + '<div class="timeline-editor__ctx-menu-section">'
      +   '<span class="timeline-editor__ctx-menu-label">Out</span>'
      +   '<button data-tout="cut">Cut</button>'
      +   '<button data-tout="dissolve">Dissolve</button>'
      +   '<button data-tout="fade-to-black">Fade to black</button>'
      + '</div>'
      + '<div class="timeline-editor__ctx-menu-section">'
      +   '<button data-action="duplicate">Duplicate</button>'
      +   '<button data-action="copy">Copy</button>'
      + '</div>'
      + '<div class="timeline-editor__ctx-menu-section">'
      +   '<button class="timeline-editor__ctx-menu-danger" data-action="delete">Delete clip</button>'
      + '</div>';
    document.body.appendChild(menu);
    _ctxMenuEl = menu;
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';

    Array.from(menu.querySelectorAll('button[data-tin]')).forEach(function (b) {
      b.addEventListener('click', function () {
        clip.transition_in = b.dataset.tin;
        _scheduleSave();
        _render();
        _closeContextMenu();
      });
    });
    Array.from(menu.querySelectorAll('button[data-tout]')).forEach(function (b) {
      b.addEventListener('click', function () {
        clip.transition_out = b.dataset.tout;
        _scheduleSave();
        _render();
        _closeContextMenu();
      });
    });
    Array.from(menu.querySelectorAll('button[data-action]')).forEach(function (b) {
      b.addEventListener('click', function () {
        var act = b.dataset.action;
        if (act === 'delete')         _deleteSelected();
        else if (act === 'duplicate') _duplicateSelected();
        else if (act === 'copy')      _copySelected();
        _closeContextMenu();
      });
    });
    // V3 Backlog 2A Phase 5 close-out — wire the volume slider to the
    // selected clip; rendering is live (no save until release).
    var volumeInput = menu.querySelector('.timeline-editor__ctx-menu-volume');
    var volumeReadout = menu.querySelector('.timeline-editor__ctx-menu-volume-readout');
    if (volumeInput) {
      volumeInput.addEventListener('input', function () {
        var pct = parseFloat(volumeInput.value);
        if (!isFinite(pct)) pct = 100;
        clip.volume = Math.max(0, Math.min(2, pct / 100));
        if (volumeReadout) volumeReadout.textContent = Math.round(pct) + '%';
      });
      volumeInput.addEventListener('change', function () {
        _scheduleSave();
      });
    }
  }

  function _closeContextMenu() {
    if (!_ctxMenuEl) return;
    try { _ctxMenuEl.remove(); } catch (e) { /* ignore */ }
    _ctxMenuEl = null;
  }

  // ── Phase 6: overlay inspector + watermark UI ────────────────────────────

  function _openOverlayInspector(trackId, clipId) {
    _closeOverlayInspector();
    var clip = _findClip(trackId, clipId);
    if (!clip || !clip.overlay_type) return;
    var content = clip.overlay_content || {};

    var panel = document.createElement('div');
    panel.className = 'timeline-editor__inspector';
    panel.dataset.trackId = trackId;
    panel.dataset.clipId = clipId;

    var typeLabel = ({
      'lower-third': 'Lower-third / subtitle',
      'title-card':  'Title card',
      'watermark':   'Watermark (time-ranged)',
    }[clip.overlay_type]) || clip.overlay_type;

    panel.innerHTML = ''
      + '<div class="timeline-editor__inspector-head">'
      +   '<span class="timeline-editor__inspector-type">' + typeLabel + '</span>'
      +   '<button type="button" class="timeline-editor__inspector-close" aria-label="Close">×</button>'
      + '</div>'
      + '<div class="timeline-editor__inspector-body">'
      +   _inspectorTextSection(clip, content)
      +   _inspectorTypographySection(content)
      +   _inspectorBackgroundSection(clip, content)
      +   _inspectorPositionSection(clip, content)
      +   _inspectorFadeSection(content)
      + '</div>';

    document.body.appendChild(panel);
    _inspectorEl = panel;
    _positionInspector(panel);
    _wireInspector(panel, clip);
  }

  function _closeOverlayInspector() {
    if (!_inspectorEl) return;
    try { _inspectorEl.remove(); } catch (e) { /* ignore */ }
    _inspectorEl = null;
  }

  function _positionInspector(panel) {
    var host = _findVisualHost();
    if (!host) return;
    var hostBox = host.getBoundingClientRect();
    panel.style.position = 'fixed';
    // Anchor to the right side of the visual pane.
    panel.style.left = (hostBox.right - 320 - 16) + 'px';
    panel.style.top  = (hostBox.top + 60) + 'px';
    panel.style.maxHeight = (hostBox.height - 80) + 'px';
  }

  function _inspectorTextSection(clip, content) {
    var canShowGradient = (clip.overlay_type === 'title-card');
    return ''
      + '<section class="timeline-editor__inspector-section">'
      +   '<label class="timeline-editor__inspector-label">Text</label>'
      +   '<textarea class="timeline-editor__inspector-textarea" data-field="text" '
      +     'rows="3" placeholder="Overlay text">' + _esc(content.text || '') + '</textarea>'
      + '</section>';
  }

  function _inspectorTypographySection(content) {
    return ''
      + '<section class="timeline-editor__inspector-section">'
      +   '<label class="timeline-editor__inspector-label">Typography</label>'
      +   '<div class="timeline-editor__inspector-row">'
      +     '<select class="timeline-editor__inspector-select" data-field="font" aria-label="Font family">'
      +       _fontOption('system-ui',                content.font)
      +       _fontOption('-apple-system',            content.font)
      +       _fontOption('Helvetica Neue',           content.font)
      +       _fontOption('Inter',                    content.font)
      +       _fontOption('Georgia',                  content.font)
      +       _fontOption('Menlo',                    content.font)
      +     '</select>'
      +     '<label class="timeline-editor__inspector-inline">Size'
      +       '<input class="timeline-editor__inspector-num" type="number" min="8" max="240" '
      +         'data-field="font_size" value="' + (content.font_size || 36) + '">'
      +     '</label>'
      +   '</div>'
      +   '<div class="timeline-editor__inspector-row">'
      +     '<label class="timeline-editor__inspector-inline">Color'
      +       '<input class="timeline-editor__inspector-color" type="color" '
      +         'data-field="color" value="' + (content.color || '#FFFFFF') + '">'
      +     '</label>'
      +   '</div>'
      // V3 Backlog 2A Phase 6 close-out — shadow + outline rows. Both
      // default to off (offset / width 0). Renderer skips the FFmpeg
      // params when offset / width is 0 so text-only output is unchanged.
      +   '<div class="timeline-editor__inspector-row">'
      +     '<label class="timeline-editor__inspector-inline">Shadow color'
      +       '<input class="timeline-editor__inspector-color" type="color" '
      +         'data-field="text_shadow_color" value="' + (content.text_shadow_color || '#000000') + '">'
      +     '</label>'
      +     '<label class="timeline-editor__inspector-inline">Shadow offset'
      +       '<input class="timeline-editor__inspector-num" type="number" min="0" max="20" step="1" '
      +         'data-field="text_shadow_offset" value="' + (content.text_shadow_offset || 0) + '">'
      +     '</label>'
      +   '</div>'
      +   '<div class="timeline-editor__inspector-row">'
      +     '<label class="timeline-editor__inspector-inline">Outline color'
      +       '<input class="timeline-editor__inspector-color" type="color" '
      +         'data-field="text_outline_color" value="' + (content.text_outline_color || '#000000') + '">'
      +     '</label>'
      +     '<label class="timeline-editor__inspector-inline">Outline width'
      +       '<input class="timeline-editor__inspector-num" type="number" min="0" max="20" step="1" '
      +         'data-field="text_outline_width" value="' + (content.text_outline_width || 0) + '">'
      +     '</label>'
      +   '</div>'
      + '</section>';
  }

  function _inspectorBackgroundSection(clip, content) {
    var grad = content.gradient || {kind:'none', from_color:'#000000', to_color:'#000000', angle_deg:0};
    var gradKind = grad.kind || 'none';
    return ''
      + '<section class="timeline-editor__inspector-section">'
      +   '<label class="timeline-editor__inspector-label">Background</label>'
      +   '<div class="timeline-editor__inspector-row">'
      +     '<label class="timeline-editor__inspector-inline">Solid'
      +       '<input class="timeline-editor__inspector-color" type="color" '
      +         'data-field="background_color" value="' + (content.background_color || '#000000') + '">'
      +     '</label>'
      +     '<label class="timeline-editor__inspector-inline">Opacity'
      +       '<input class="timeline-editor__inspector-range" type="range" min="0" max="1" step="0.05" '
      +         'data-field="background_opacity" value="' + (content.background_opacity != null ? content.background_opacity : 0) + '">'
      +     '</label>'
      +   '</div>'
      +   '<div class="timeline-editor__inspector-row">'
      +     '<span class="timeline-editor__inspector-grad-label">Gradient</span>'
      +     _gradKindBtn('none',   gradKind)
      +     _gradKindBtn('linear', gradKind)
      +     _gradKindBtn('radial', gradKind)
      +   '</div>'
      +   '<div class="timeline-editor__inspector-row" data-field-group="gradient" '
      +     'style="display:' + (gradKind === 'none' ? 'none' : 'flex') + ';">'
      +     '<label class="timeline-editor__inspector-inline">From'
      +       '<input class="timeline-editor__inspector-color" type="color" '
      +         'data-field="gradient.from_color" value="' + (grad.from_color || '#000000') + '">'
      +     '</label>'
      +     '<label class="timeline-editor__inspector-inline">To'
      +       '<input class="timeline-editor__inspector-color" type="color" '
      +         'data-field="gradient.to_color" value="' + (grad.to_color || '#000000') + '">'
      +     '</label>'
      +     '<label class="timeline-editor__inspector-inline">Angle'
      +       '<input class="timeline-editor__inspector-num" type="number" min="0" max="360" '
      +         'data-field="gradient.angle_deg" value="' + (grad.angle_deg || 0) + '">'
      +     '</label>'
      +   '</div>'
      + '</section>';
  }

  function _inspectorPositionSection(clip, content) {
    if (clip.overlay_type === 'title-card') {
      // Title cards fill the frame; no positioning needed.
      return '';
    }
    var pos = content.position || {x_pct:0.5, y_pct:0.5, width_pct:1.0};
    return ''
      + '<section class="timeline-editor__inspector-section">'
      +   '<label class="timeline-editor__inspector-label">Position (% of frame)</label>'
      +   '<div class="timeline-editor__inspector-row">'
      +     '<label class="timeline-editor__inspector-inline">X'
      +       '<input class="timeline-editor__inspector-num" type="number" min="0" max="100" step="1" '
      +         'data-field="position.x_pct" value="' + Math.round((pos.x_pct || 0) * 100) + '">'
      +     '</label>'
      +     '<label class="timeline-editor__inspector-inline">Y'
      +       '<input class="timeline-editor__inspector-num" type="number" min="0" max="100" step="1" '
      +         'data-field="position.y_pct" value="' + Math.round((pos.y_pct || 0) * 100) + '">'
      +     '</label>'
      +     '<label class="timeline-editor__inspector-inline">Width'
      +       '<input class="timeline-editor__inspector-num" type="number" min="5" max="100" step="1" '
      +         'data-field="position.width_pct" value="' + Math.round((pos.width_pct || 1) * 100) + '">'
      +     '</label>'
      +   '</div>'
      + '</section>';
  }

  function _inspectorFadeSection(content) {
    return ''
      + '<section class="timeline-editor__inspector-section">'
      +   '<label class="timeline-editor__inspector-label">Fade</label>'
      +   '<div class="timeline-editor__inspector-row">'
      +     '<label class="timeline-editor__inspector-inline">In (ms)'
      +       '<input class="timeline-editor__inspector-num" type="number" min="0" max="5000" step="50" '
      +         'data-field="fade_in_ms" value="' + (content.fade_in_ms || 0) + '">'
      +     '</label>'
      +     '<label class="timeline-editor__inspector-inline">Out (ms)'
      +       '<input class="timeline-editor__inspector-num" type="number" min="0" max="5000" step="50" '
      +         'data-field="fade_out_ms" value="' + (content.fade_out_ms || 0) + '">'
      +     '</label>'
      +   '</div>'
      + '</section>';
  }

  function _fontOption(family, current) {
    var sel = (current === family) ? ' selected' : '';
    return '<option value="' + family + '"' + sel + '>' + family + '</option>';
  }

  function _gradKindBtn(kind, current) {
    var active = (kind === current) ? ' data-active="true"' : '';
    var label = ({none:'None', linear:'Linear', radial:'Radial'})[kind] || kind;
    return '<button type="button" class="timeline-editor__inspector-grad-btn" '
      + 'data-grad-kind="' + kind + '"' + active + '>' + label + '</button>';
  }

  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _basename(path) {
    if (!path) return '';
    var s = String(path);
    var i = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'));
    return i >= 0 ? s.slice(i + 1) : s;
  }

  function _uploadWatermarkImage(file, menuEl) {
    if (!file || !_conversationId) return;
    var statusEl = menuEl && menuEl.querySelector('[data-wm-status]');
    if (statusEl) statusEl.textContent = 'Uploading…';
    var fd = new FormData();
    fd.append('file', file, file.name);
    fetch('/api/watermark/' + encodeURIComponent(_conversationId) + '/upload', {
      method: 'POST',
      body: fd,
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, data: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error((res.data && res.data.error) || 'upload failed');
        }
        _state.watermark = _state.watermark || {};
        _state.watermark.image_path = res.data.image_path;
        // Auto-enable the watermark on first upload — typical user
        // intent. They can still toggle off from the same picker.
        if (_state.watermark.enabled === undefined) _state.watermark.enabled = true;
        _scheduleSave();
        _closeContextMenu();
        _openWatermarkPicker();
      })
      .catch(function (err) {
        if (statusEl) {
          statusEl.textContent = 'Upload failed: ' + (err && err.message || err);
        }
      });
  }

  function _wireInspector(panel, clip) {
    panel.querySelector('.timeline-editor__inspector-close').addEventListener('click', _closeOverlayInspector);

    // Track-id and clip-id captured by id, not by reference: after every
    // save the server returns a normalized state and `_state` is replaced.
    // Stored references go stale; resolving by id keeps mutations applying
    // to the live object.
    var trackId = panel.dataset.trackId;
    var clipId  = panel.dataset.clipId;

    panel.addEventListener('input', function (e) {
      var field = e.target.dataset.field;
      if (!field) return;
      var raw = e.target.value;
      _applyInspectorField(trackId, clipId, field, raw);
    });
    panel.addEventListener('change', function (e) {
      var field = e.target.dataset.field;
      if (!field) return;
      _scheduleSave();
    });

    // Gradient kind buttons
    Array.from(panel.querySelectorAll('.timeline-editor__inspector-grad-btn')).forEach(function (b) {
      b.addEventListener('click', function () {
        var kind = b.dataset.gradKind;
        var live = _findClip(trackId, clipId);
        if (!live) return;
        live.overlay_content = live.overlay_content || {};
        live.overlay_content.gradient = live.overlay_content.gradient || {};
        live.overlay_content.gradient.kind = kind;
        Array.from(panel.querySelectorAll('.timeline-editor__inspector-grad-btn')).forEach(function (other) {
          if (other === b) other.dataset.active = 'true';
          else delete other.dataset.active;
        });
        var gradRow = panel.querySelector('[data-field-group="gradient"]');
        if (gradRow) gradRow.style.display = (kind === 'none') ? 'none' : 'flex';
        _scheduleSave();
        _render();
      });
    });
  }

  function _applyInspectorField(trackId, clipId, field, raw) {
    var clip = _findClip(trackId, clipId);
    if (!clip) return;
    clip.overlay_content = clip.overlay_content || {};
    var content = clip.overlay_content;
    if (field.indexOf('position.') === 0) {
      var k = field.substring('position.'.length);
      content.position = content.position || {};
      var n = parseFloat(raw);
      if (!isFinite(n)) n = 0;
      content.position[k] = n / 100;  // form shows %, store fraction
    } else if (field.indexOf('gradient.') === 0) {
      var gk = field.substring('gradient.'.length);
      content.gradient = content.gradient || {};
      if (gk === 'angle_deg') {
        content.gradient[gk] = parseInt(raw, 10) || 0;
      } else {
        content.gradient[gk] = raw;
      }
    } else if (field === 'font_size' || field === 'fade_in_ms'
                || field === 'fade_out_ms'
                || field === 'text_shadow_offset'
                || field === 'text_outline_width') {
      content[field] = parseInt(raw, 10) || 0;
    } else if (field === 'background_opacity') {
      content[field] = parseFloat(raw) || 0;
    } else {
      content[field] = raw;
    }
    _scheduleSave();
    // Re-render the timeline so the clip's label reflects the new text.
    if (field === 'text') _render();
  }

  // ── Phase 6: watermark UI in the ruler row ──────────────────────────────

  function _wireWatermarkButton() {
    if (!_editorEl) return;
    var btn = _editorEl.querySelector('[data-role="watermark"]');
    if (!btn) return;
    btn.addEventListener('click', _openWatermarkPicker);
  }

  function _renderWatermarkButton() {
    if (!_editorEl || !_state) return;
    var btn = _editorEl.querySelector('[data-role="watermark"]');
    if (!btn) return;
    var w = _state.watermark || {enabled:false};
    btn.dataset.enabled = w.enabled ? 'true' : 'false';
    btn.title = 'Watermark — ' + (w.enabled ? 'on (' + w.corner + ')' : 'off');
  }

  function _openWatermarkPicker() {
    if (_ctxMenuEl) _closeContextMenu();
    var w = _state.watermark || {enabled:false, corner:'bottom-right', opacity:0.55};
    var menu = document.createElement('div');
    menu.className = 'timeline-editor__ctx-menu timeline-editor__ctx-menu--wm';
    var imageRow = w.image_path
      ? ('<div class="timeline-editor__ctx-menu-row">'
         +   '<span class="timeline-editor__ctx-menu-label">Image</span>'
         +   '<span class="timeline-editor__wm-image-name">'
         +     _esc(_basename(w.image_path)) + '</span>'
         +   '<button type="button" data-wm-action="clear-image" '
         +           'class="timeline-editor__inspector-btn">Use ◎ glyph</button>'
         + '</div>')
      : ('<div class="timeline-editor__ctx-menu-row">'
         +   '<span class="timeline-editor__ctx-menu-label">Image</span>'
         +   '<span class="timeline-editor__wm-image-empty">— ◎ glyph —</span>'
         + '</div>');
    menu.innerHTML = ''
      + '<div class="timeline-editor__ctx-menu-title">Watermark</div>'
      + '<label class="timeline-editor__ctx-menu-row">'
      +   '<input type="checkbox" data-wm="enabled"' + (w.enabled ? ' checked' : '') + '>'
      +   '<span>Enabled</span>'
      + '</label>'
      + imageRow
      + '<div class="timeline-editor__ctx-menu-row">'
      +   '<input type="file" data-wm-action="upload-image" '
      +          'accept="image/png,image/jpeg,image/webp" '
      +          'class="timeline-editor__wm-image-input">'
      + '</div>'
      + '<div class="timeline-editor__ctx-menu-row">'
      +   '<span class="timeline-editor__ctx-menu-label">Corner</span>'
      +   _wmCornerBtn('top-left',     w.corner)
      +   _wmCornerBtn('top-right',    w.corner)
      +   _wmCornerBtn('bottom-left',  w.corner)
      +   _wmCornerBtn('bottom-right', w.corner)
      + '</div>'
      + '<label class="timeline-editor__ctx-menu-row">'
      +   '<span class="timeline-editor__ctx-menu-label">Opacity</span>'
      +   '<input type="range" data-wm="opacity" min="0" max="1" step="0.05" value="' + (w.opacity != null ? w.opacity : 0.55) + '">'
      +   '<span data-wm-readout>' + Math.round((w.opacity != null ? w.opacity : 0.55) * 100) + '%</span>'
      + '</label>'
      + '<div class="timeline-editor__ctx-menu-row" data-wm-status></div>';
    document.body.appendChild(menu);
    _ctxMenuEl = menu;

    var clearBtn = menu.querySelector('[data-wm-action="clear-image"]');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        _state.watermark = _state.watermark || {};
        _state.watermark.image_path = null;
        _scheduleSave();
        _closeContextMenu();
        _openWatermarkPicker();
      });
    }
    var uploadInput = menu.querySelector('[data-wm-action="upload-image"]');
    if (uploadInput) {
      uploadInput.addEventListener('change', function (e) {
        var file = (e.target.files && e.target.files[0]) || null;
        if (!file) return;
        _uploadWatermarkImage(file, menu);
      });
    }
    var btn = _editorEl.querySelector('[data-role="watermark"]');
    var rect = btn.getBoundingClientRect();
    menu.style.left = (rect.left) + 'px';
    menu.style.top  = (rect.bottom + 4) + 'px';

    menu.querySelector('input[data-wm="enabled"]').addEventListener('change', function (e) {
      _state.watermark = _state.watermark || {};
      _state.watermark.enabled = !!e.target.checked;
      _scheduleSave();
      _renderWatermarkButton();
    });
    Array.from(menu.querySelectorAll('button[data-wm-corner]')).forEach(function (b) {
      b.addEventListener('click', function () {
        _state.watermark = _state.watermark || {};
        _state.watermark.corner = b.dataset.wmCorner;
        Array.from(menu.querySelectorAll('button[data-wm-corner]')).forEach(function (other) {
          if (other === b) other.dataset.active = 'true';
          else delete other.dataset.active;
        });
        _scheduleSave();
        _renderWatermarkButton();
      });
    });
    var opacityInput = menu.querySelector('input[data-wm="opacity"]');
    var readout = menu.querySelector('[data-wm-readout]');
    opacityInput.addEventListener('input', function (e) {
      var val = parseFloat(e.target.value) || 0;
      _state.watermark = _state.watermark || {};
      _state.watermark.opacity = val;
      readout.textContent = Math.round(val * 100) + '%';
    });
    opacityInput.addEventListener('change', function () { _scheduleSave(); });
  }

  function _wmCornerBtn(corner, current) {
    var active = (corner === current) ? ' data-active="true"' : '';
    var glyph = ({
      'top-left':     '⌜',
      'top-right':    '⌝',
      'bottom-left':  '⌞',
      'bottom-right': '⌟',
    })[corner] || corner;
    return '<button type="button" class="timeline-editor__inspector-grad-btn" '
      + 'data-wm-corner="' + corner + '"' + active + ' aria-label="' + corner + '">'
      + glyph + '</button>';
  }

  // ── Show / hide ──────────────────────────────────────────────────────────

  function _findVisualHost() {
    return document.querySelector('.visual-panel')
        || document.querySelector('.pane.right-pane');
  }

  function _show() {
    var host = _findVisualHost();
    if (!host) return;
    _hostEl = host;
    if (!_editorEl) _build();
    if (!_editorEl.parentNode) host.appendChild(_editorEl);
    _editorEl.classList.add('timeline-editor--visible');
    _refreshLibraryCache().then(_loadState).then(function () { _render(); });
  }

  function _hide() {
    if (_editorEl) _editorEl.classList.remove('timeline-editor--visible');
    _closeContextMenu();
  }

  // Pull a fresh snapshot of the media library so clip names + durations
  // resolve correctly without N round-trips.
  function _refreshLibraryCache() {
    if (!_conversationId) return Promise.resolve();
    return fetch('/api/media-library/' + encodeURIComponent(_conversationId))
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var byId = {};
        (j.entries || []).forEach(function (e) { byId[e.id] = e; });
        _libraryEntriesCache = byId;
      })
      .catch(function () { _libraryEntriesCache = {}; });
  }

  // Ensure the library cache is current before placing a clip from a
  // freshly-captured / freshly-imported entry. The cache is otherwise
  // refreshed on mount + conversation change; new entries that arrived
  // since then would be missing, leaving _addClipFromLibrary to fall
  // back to a 5000 ms default duration.
  function _addClipFromLibrarySafely(trackId, entryId, positionMs) {
    if (_libraryEntriesCache[entryId]) {
      _addClipFromLibrary(trackId, entryId, positionMs);
      return;
    }
    _refreshLibraryCache().then(function () {
      _addClipFromLibrary(trackId, entryId, positionMs);
    });
  }

  // ── External plumbing ────────────────────────────────────────────────────

  function setConversationId(id) {
    _conversationId = id || null;
    _selectedClipId = null;
    _selectedTrackId = null;
    if (document.body.classList.contains('pane-mode-video')) {
      _refreshLibraryCache().then(_loadState).then(function () { _render(); });
    }
  }

  function reload() {
    return _refreshLibraryCache().then(_loadState).then(function () {
      // V3 Backlog 2A Phase 5 close-out — seed undo history with the
      // freshly-loaded state so the very first mutation has something
      // to step back to.
      _history = [];
      _historyCursor = -1;
      if (_state) {
        _history.push(JSON.parse(JSON.stringify(_state)));
        _historyCursor = 0;
      }
      _render();
    });
  }

  function init() {
    document.addEventListener('ora:pane-mode-toggle', function (e) {
      var cur = e.detail && e.detail.current;
      if (cur === 'video') _show(); else _hide();
    });
    document.addEventListener('ora:conversation-selected', function (e) {
      var d = e.detail || {};
      var cid = d.conversation_id || d.id || null;
      if (cid) setConversationId(cid);
    });
    // The preview monitor drives the playhead during proxy playback. We
    // mirror its position on the timeline so the user sees the cursor
    // travel through the clip arrangement. Save is debounced so the
    // many-per-second timeupdate events collapse to one save when
    // playback stops.
    document.addEventListener('ora:preview-playhead-update', function (e) {
      if (!_state) return;
      var ms = (e.detail && Number(e.detail.playhead_ms)) || 0;
      _state.playhead_ms = Math.max(0, ms);
      _renderPlayhead();
      _renderTimecode();
      _scheduleSave();
    });
    _build();
  }

  // ── A/V Phase 8 — applyCutSuggestion ───────────────────────────────────
  // Public mutation entry point used by the suggestions panel.
  // Removes a source-time range [start_ms, end_ms] for a given
  // media_entry_id from the timeline. V1 scope: only operates on
  // a single clip whose source range fully contains the cut. Cuts
  // that span multiple clips return ok:false with a reason; the user
  // resolves those manually.
  function applyCutSuggestion(opts) {
    if (!_state || !Array.isArray(_state.tracks)) {
      return { ok: false, reason: 'no timeline state' };
    }
    var entryId = opts && opts.media_entry_id;
    var startSrc = Number(opts && opts.start_ms);
    var endSrc = Number(opts && opts.end_ms);
    if (!entryId) return { ok: false, reason: 'media_entry_id required' };
    if (!isFinite(startSrc) || !isFinite(endSrc) || endSrc <= startSrc) {
      return { ok: false, reason: 'invalid source range' };
    }

    // Find a clip with this entry that fully contains the range.
    var targetTrack = null;
    var targetClip = null;
    for (var ti = 0; ti < _state.tracks.length; ti++) {
      var trk = _state.tracks[ti];
      if (!trk || !Array.isArray(trk.clips)) continue;
      for (var ci = 0; ci < trk.clips.length; ci++) {
        var c = trk.clips[ci];
        if (!c || c.media_entry_id !== entryId) continue;
        var cIn = Number(c.in_point_ms) || 0;
        var cOut = Number(c.out_point_ms) || 0;
        if (startSrc >= cIn && endSrc <= cOut && cOut > cIn) {
          targetTrack = trk;
          targetClip = c;
          break;
        }
      }
      if (targetClip) break;
    }
    if (!targetClip) {
      return {
        ok: false,
        reason: 'no clip on the timeline contains this source range',
      };
    }

    var clipIn = Number(targetClip.in_point_ms) || 0;
    var clipOut = Number(targetClip.out_point_ms) || 0;
    var clipPos = Number(targetClip.track_position_ms) || 0;
    var startTrackMs = clipPos + (startSrc - clipIn);
    var endTrackMs = clipPos + (endSrc - clipIn);
    var cutLength = endTrackMs - startTrackMs;
    if (cutLength <= 0) return { ok: false, reason: 'zero-length cut' };

    var originalOut = clipOut;
    var originalTransitionOut = targetClip.transition_out;

    // Mutate target into the LEFT half: out_point_ms = startSrc.
    targetClip.out_point_ms = startSrc;
    targetClip.transition_out = 'cut';

    // Create the RIGHT half occupying [startTrackMs, startTrackMs + (originalOut - endSrc)].
    var rightId = 'clip-' + Date.now().toString(36)
                + '-' + Math.floor(Math.random() * 1e6).toString(36);
    var rightClip = JSON.parse(JSON.stringify(targetClip));
    rightClip.id = rightId;
    rightClip.in_point_ms = endSrc;
    rightClip.out_point_ms = originalOut;
    rightClip.track_position_ms = startTrackMs;
    rightClip.transition_in = 'cut';
    rightClip.transition_out = originalTransitionOut || 'cut';

    // Skip 0-length halves (cuts that touch a clip boundary).
    if (targetClip.out_point_ms <= targetClip.in_point_ms) {
      // Left half collapsed — drop it.
      targetTrack.clips = targetTrack.clips.filter(function (cc) {
        return cc.id !== targetClip.id;
      });
    }
    if (rightClip.out_point_ms > rightClip.in_point_ms) {
      targetTrack.clips.push(rightClip);
    }

    // Ripple-shift any unrelated clip on the same track that started after
    // the cut region.
    targetTrack.clips.forEach(function (cc) {
      if (cc.id === targetClip.id || cc.id === rightClip.id) return;
      var pos = Number(cc.track_position_ms) || 0;
      if (pos >= endTrackMs) {
        cc.track_position_ms = Math.max(0, pos - cutLength);
      }
    });

    _scheduleSave();
    _render();
    return { ok: true, deleted_ms: cutLength };
  }

  // ── A/V Phase 8 — apply chapter / title_card / transition suggestions ─

  function _findOrCreateOverlayTrack() {
    if (!_state || !Array.isArray(_state.tracks)) return null;
    var existing = _state.tracks.find(function (t) {
      return t && t.kind === 'overlay';
    });
    if (existing) return existing;
    var newTrack = {
      id: 'track-' + Date.now().toString(36) + '-' + Math.floor(Math.random() * 1e6).toString(36),
      kind: 'overlay',
      label: 'Overlay',
      muted: false,
      clips: [],
    };
    _state.tracks.push(newTrack);
    return newTrack;
  }

  function _newClipId() {
    return 'clip-' + Date.now().toString(36)
         + '-' + Math.floor(Math.random() * 1e6).toString(36);
  }

  function applyChapterSuggestion(opts) {
    if (!_state) return { ok: false, reason: 'no timeline state' };
    var atMs = Number(opts && opts.at_ms);
    var label = String((opts && opts.label) || '').trim();
    if (!isFinite(atMs) || atMs < 0) return { ok: false, reason: 'invalid at_ms' };
    if (!label) return { ok: false, reason: 'label required' };
    var track = _findOrCreateOverlayTrack();
    if (!track) return { ok: false, reason: 'no track' };
    track.clips.push({
      id: _newClipId(),
      media_entry_id: '',
      track_position_ms: atMs,
      in_point_ms: 0,
      out_point_ms: 2500,                // 2.5s display
      transition_in: 'cut',
      transition_out: 'cut',
      transition_duration_ms: 500,
      volume: 1.0,
      fade_in_ms: 0,
      fade_out_ms: 0,
      overlay_type: 'lower-third',
      overlay_content: {
        text: label,
        font_size: 32,
        color: '#FFFFFF',
        background_color: '#000000',
        background_opacity: 0.55,
        position: { x_pct: 0.05, y_pct: 0.85, width_pct: 0.5 },
        fade_in_ms: 200,
        fade_out_ms: 200,
      },
    });
    _scheduleSave();
    _render();
    return { ok: true };
  }

  function applyTitleCardSuggestion(opts) {
    if (!_state) return { ok: false, reason: 'no timeline state' };
    var atMs = Number(opts && opts.at_ms);
    var durMs = Number(opts && opts.duration_ms) || 3000;
    var title = String((opts && opts.title) || '').trim();
    var subtitle = String((opts && opts.subtitle) || '').trim();
    if (!isFinite(atMs) || atMs < 0) return { ok: false, reason: 'invalid at_ms' };
    if (!title) return { ok: false, reason: 'title required' };
    var track = _findOrCreateOverlayTrack();
    if (!track) return { ok: false, reason: 'no track' };
    track.clips.push({
      id: _newClipId(),
      media_entry_id: '',
      track_position_ms: atMs,
      in_point_ms: 0,
      out_point_ms: Math.max(500, durMs),
      transition_in: 'cut',
      transition_out: 'cut',
      transition_duration_ms: 500,
      volume: 1.0,
      fade_in_ms: 0,
      fade_out_ms: 0,
      overlay_type: 'title-card',
      overlay_content: {
        text: subtitle ? (title + '\n' + subtitle) : title,
        font_size: 96,
        color: '#FFFFFF',
        background_color: '#0E1117',
        background_opacity: 1.0,
        gradient: {
          kind: 'linear',
          from_color: '#0E1117',
          to_color: '#1A2030',
          angle_deg: 135,
        },
        fade_in_ms: 400,
        fade_out_ms: 400,
      },
    });
    _scheduleSave();
    _render();
    return { ok: true };
  }

  function applyTransitionSuggestion(opts) {
    // Sets the outgoing transition on whichever clip ends nearest
    // ``at_ms``. The Phase 8 framework emits kind ∈ {fade, dissolve, cut};
    // we map ``fade`` → ``fade-to-black`` since that's the validator's
    // canonical name.
    if (!_state || !Array.isArray(_state.tracks)) {
      return { ok: false, reason: 'no timeline state' };
    }
    var atMs = Number(opts && opts.at_ms);
    var rawKind = (opts && opts.kind) || 'cut';
    var durMs = Number(opts && opts.duration_ms) || 500;
    if (!isFinite(atMs) || atMs < 0) return { ok: false, reason: 'invalid at_ms' };
    var kind = rawKind === 'fade' ? 'fade-to-black'
             : rawKind === 'dissolve' ? 'dissolve'
             : 'cut';

    // Find the clip whose end is closest to at_ms (within 1s tolerance —
    // the framework often suggests transitions at sentence boundaries
    // that fall a few hundred ms after the actual cut).
    var bestClip = null;
    var bestDistance = Infinity;
    for (var ti = 0; ti < _state.tracks.length; ti++) {
      var trk = _state.tracks[ti];
      if (!trk || trk.kind === 'overlay' || !Array.isArray(trk.clips)) continue;
      for (var ci = 0; ci < trk.clips.length; ci++) {
        var c = trk.clips[ci];
        if (!c || c.overlay_type) continue; // skip overlay clips
        var pos = Number(c.track_position_ms) || 0;
        var len = (Number(c.out_point_ms) || 0) - (Number(c.in_point_ms) || 0);
        var endMs = pos + Math.max(0, len);
        var dist = Math.abs(endMs - atMs);
        if (dist < bestDistance) {
          bestDistance = dist;
          bestClip = c;
        }
      }
    }
    if (!bestClip || bestDistance > 1000) {
      return { ok: false,
               reason: 'no clip ends near this timestamp (closest was '
                     + Math.round(bestDistance) + 'ms away)' };
    }
    bestClip.transition_out = kind;
    bestClip.transition_duration_ms = Math.max(100, durMs);
    _scheduleSave();
    _render();
    return { ok: true, applied_kind: kind };
  }

  // ── Drag-to-position public API (Phase 6 follow-up, 2026-05-01) ──────────
  //
  // Lets preview-monitor.js update an overlay's normalized position from a
  // drag interaction on the preview stage. Numbers are clamped into the
  // visible range so a runaway drag can't push the overlay off-frame, and
  // the inspector inputs are refreshed in place when open. The change is
  // sent through the same _scheduleSave path the inspector uses, so the
  // server-side timeline state stays consistent.

  function setOverlayPosition(trackId, clipId, x_pct, y_pct, opts) {
    opts = opts || {};
    var clip = _findClip(trackId, clipId);
    if (!clip) return { ok: false, reason: 'clip not found' };
    if (clip.overlay_type !== 'lower-third') {
      return { ok: false, reason: 'overlay_type does not support positioning' };
    }
    if (typeof x_pct !== 'number' || !isFinite(x_pct)) {
      return { ok: false, reason: 'x_pct must be a finite number' };
    }
    if (typeof y_pct !== 'number' || !isFinite(y_pct)) {
      return { ok: false, reason: 'y_pct must be a finite number' };
    }
    // Clamp to [0, 1] — the renderer's safe range. Real overlays can sit
    // exactly at 0 or 1; values outside that produce garbage.
    var x = Math.max(0, Math.min(1, x_pct));
    var y = Math.max(0, Math.min(1, y_pct));

    clip.overlay_content = clip.overlay_content || {};
    clip.overlay_content.position = clip.overlay_content.position || {};
    clip.overlay_content.position.x_pct = x;
    clip.overlay_content.position.y_pct = y;

    // Refresh inspector inputs in place if they're open for this clip,
    // so the form-field values match the dragged position immediately.
    if (_inspectorEl
        && _inspectorEl.dataset.trackId === trackId
        && _inspectorEl.dataset.clipId  === clipId) {
      var xField = _inspectorEl.querySelector('[data-field="position.x_pct"]');
      var yField = _inspectorEl.querySelector('[data-field="position.y_pct"]');
      if (xField) xField.value = String(Math.round(x * 100));
      if (yField) yField.value = String(Math.round(y * 100));
    }

    if (!opts.skipSave) _scheduleSave();
    return { ok: true, x_pct: x, y_pct: y };
  }

  root.OraTimelineEditor = {
    init: init,
    setConversationId: setConversationId,
    reload: reload,
    getState: function () { return _state ? JSON.parse(JSON.stringify(_state)) : null; },
    applyCutSuggestion: applyCutSuggestion,
    applyChapterSuggestion: applyChapterSuggestion,
    applyTitleCardSuggestion: applyTitleCardSuggestion,
    applyTransitionSuggestion: applyTransitionSuggestion,
    // Phase 6 follow-up (drag-to-position) — preview-monitor.js calls this
    // during overlay drags. Returns {ok, x_pct, y_pct} on success or
    // {ok:false, reason} on validation failure.
    setOverlayPosition: setOverlayPosition,
    // Test seam — the Apply methods need a populated state to operate
    // against. In production _state is hydrated by _loadState() over
    // the network; tests use this to inject a known state directly.
    _setStateForTests: function (s) { _state = s; },
  };
})(typeof window !== 'undefined' ? window : this);
