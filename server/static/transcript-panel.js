/**
 * transcript-panel.js — Audio/Video Phase 8
 *
 * Floating overlay docked to the right edge of the visual pane in
 * `body.pane-mode-video`. Shows whisper segments for whichever
 * media-library entry is currently under the timeline playhead. Click
 * a segment to seek; the active segment highlights as the playhead
 * moves.
 *
 * Event contract (all on `document`):
 *   in  : `ora:pane-mode-toggle`         — show/hide
 *         `ora:conversation-selected`    — switch conversation
 *         `ora:timeline-playhead-changed` — refresh active highlight
 *         `ora:timeline-mutated`         — clip set may have changed
 *   out : `ora:timeline-playhead-changed` — fired with source: 'transcript'
 *                                            when the user clicks a segment
 *
 * Reads `window.OraTimelineEditor.getState()` to find the clip at the
 * playhead and to convert track-time ↔ source-time. No new event needed
 * from timeline-editor; it already exposes the snapshot we need.
 *
 * Public namespace: window.OraTranscriptPanel
 *   .init()
 *   .setConversationId(id)
 *   .show() / .hide() / .toggle()
 *   .reload()
 *   .getState()                          — for tests
 */
(function (root) {
  'use strict';

  if (typeof document === 'undefined') return;

  // ── module state ─────────────────────────────────────────────────────────

  var _hostEl = null;
  var _rootEl = null;
  var _listEl = null;
  var _statusEl = null;
  var _conversationId = null;

  // Loaded transcript: which entry it's for, plus the segments themselves.
  var _loadedEntryId = null;
  var _segments = [];
  var _segmentEls = [];
  var _activeSegmentIdx = -1;
  var _loadingEntryId = null;
  var _loadAbort = null;

  // Suggestions section (Item #2 — Video Editing Suggestions framework).
  var _suggSummaryEl = null;
  var _suggListEl = null;
  var _suggRunBtn = null;
  var _suggestionsForEntry = null;   // entry_id the loaded suggestions apply to
  var _suggestions = [];
  var _suggestRunning = false;

  // The user just clicked a segment row → suppress auto-scroll for
  // 800ms so the seek doesn't fight the click ripple.
  var _suppressAutoScrollUntil = 0;

  // ── helpers ──────────────────────────────────────────────────────────────

  function _formatTimecode(ms) {
    if (!isFinite(ms) || ms < 0) ms = 0;
    var totalSec = Math.floor(ms / 1000);
    var h = Math.floor(totalSec / 3600);
    var m = Math.floor((totalSec % 3600) / 60);
    var s = totalSec % 60;
    if (h > 0) {
      return String(h) + ':' +
             String(m).padStart(2, '0') + ':' +
             String(s).padStart(2, '0');
    }
    return String(m).padStart(2, '0') + ':' +
           String(s).padStart(2, '0');
  }

  function _findActiveClip(state, playheadMs) {
    if (!state || !Array.isArray(state.tracks)) return null;
    for (var ti = 0; ti < state.tracks.length; ti++) {
      var track = state.tracks[ti];
      if (!track || !Array.isArray(track.clips)) continue;
      for (var ci = 0; ci < track.clips.length; ci++) {
        var clip = track.clips[ci];
        if (!clip || !clip.media_entry_id) continue; // overlay clips skip
        var inMs = Number(clip.in_point_ms) || 0;
        var outMs = Number(clip.out_point_ms) || 0;
        var pos = Number(clip.track_position_ms) || 0;
        var len = outMs - inMs;
        if (len <= 0) continue;
        if (playheadMs >= pos && playheadMs < pos + len) {
          return clip;
        }
      }
    }
    return null;
  }

  function _sourceTimeAt(clip, playheadMs) {
    var inMs = Number(clip.in_point_ms) || 0;
    var pos = Number(clip.track_position_ms) || 0;
    return inMs + (playheadMs - pos);
  }

  function _segmentIdxAt(segments, sourceMs) {
    if (!segments || !segments.length) return -1;
    // Linear scan is fine: typical talks have a few hundred segments.
    for (var i = 0; i < segments.length; i++) {
      var seg = segments[i];
      if (sourceMs >= seg.start_ms && sourceMs < seg.end_ms) return i;
    }
    // Fall back to last completed segment (handles the gap at the end).
    var last = -1;
    for (var j = 0; j < segments.length; j++) {
      if (segments[j].start_ms <= sourceMs) last = j;
    }
    return last;
  }

  function _trackTimeForSegment(state, entryId, segmentStartMs) {
    if (!state || !Array.isArray(state.tracks)) return null;
    for (var ti = 0; ti < state.tracks.length; ti++) {
      var track = state.tracks[ti];
      if (!track || !Array.isArray(track.clips)) continue;
      for (var ci = 0; ci < track.clips.length; ci++) {
        var clip = track.clips[ci];
        if (!clip || clip.media_entry_id !== entryId) continue;
        var inMs = Number(clip.in_point_ms) || 0;
        var outMs = Number(clip.out_point_ms) || 0;
        if (segmentStartMs >= inMs && segmentStartMs < outMs) {
          var pos = Number(clip.track_position_ms) || 0;
          return pos + (segmentStartMs - inMs);
        }
      }
    }
    return null; // segment is trimmed out of every clip on the timeline
  }

  // ── DOM build ────────────────────────────────────────────────────────────

  function _build() {
    if (_rootEl) return _rootEl;
    var el = document.createElement('div');
    el.className = 'transcript-panel';
    el.innerHTML = ''
      + '<div class="transcript-panel__header">'
      +   '<span class="transcript-panel__title">Transcript</span>'
      +   '<button type="button" class="transcript-panel__close" '
      +           'title="Close (transcript stays available — toggle from the timeline)" '
      +           'aria-label="Close transcript panel">×</button>'
      + '</div>'
      + '<div class="transcript-panel__status" data-role="status"></div>'
      + '<div class="transcript-panel__list" data-role="list" tabindex="0"></div>'
      + '<div class="transcript-panel__suggestions" data-role="suggestions">'
      +   '<div class="transcript-panel__sugg-header">'
      +     '<span class="transcript-panel__sugg-title">Edit suggestions</span>'
      +     '<button type="button" class="transcript-panel__sugg-run" '
      +             'data-role="sugg-run">Suggest edits</button>'
      +   '</div>'
      +   '<div class="transcript-panel__sugg-summary" data-role="sugg-summary"></div>'
      +   '<div class="transcript-panel__sugg-list" data-role="sugg-list"></div>'
      + '</div>';
    _rootEl = el;
    _listEl = el.querySelector('[data-role="list"]');
    _statusEl = el.querySelector('[data-role="status"]');
    _suggSummaryEl = el.querySelector('[data-role="sugg-summary"]');
    _suggListEl = el.querySelector('[data-role="sugg-list"]');
    _suggRunBtn = el.querySelector('[data-role="sugg-run"]');
    el.querySelector('.transcript-panel__close')
      .addEventListener('click', hide);
    if (_suggRunBtn) {
      _suggRunBtn.addEventListener('click', _onSuggestEdits);
    }
    return el;
  }

  function _setStatus(msg) {
    if (!_statusEl) return;
    if (msg) {
      _statusEl.textContent = msg;
      _statusEl.classList.add('transcript-panel__status--visible');
    } else {
      _statusEl.textContent = '';
      _statusEl.classList.remove('transcript-panel__status--visible');
    }
  }

  function _renderSegments() {
    if (!_listEl) return;
    _listEl.innerHTML = '';
    _segmentEls = [];
    if (!_segments.length) return;
    var frag = document.createDocumentFragment();
    for (var i = 0; i < _segments.length; i++) {
      var seg = _segments[i];
      var row = document.createElement('div');
      row.className = 'transcript-panel__segment';
      row.setAttribute('role', 'button');
      row.setAttribute('tabindex', '0');
      row.dataset.idx = String(i);
      row.dataset.startMs = String(seg.start_ms);
      var tc = document.createElement('span');
      tc.className = 'transcript-panel__timecode';
      tc.textContent = _formatTimecode(seg.start_ms);
      var tx = document.createElement('span');
      tx.className = 'transcript-panel__text';
      tx.textContent = seg.text;
      row.appendChild(tc);
      row.appendChild(tx);
      row.addEventListener('click', _onSegmentClick);
      row.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          _onSegmentClick.call(this, e);
        }
      });
      _segmentEls.push(row);
      frag.appendChild(row);
    }
    _listEl.appendChild(frag);
    _activeSegmentIdx = -1;
  }

  function _onSegmentClick(e) {
    var idx = Number(this.dataset.idx);
    if (!isFinite(idx) || idx < 0 || idx >= _segments.length) return;
    var seg = _segments[idx];
    if (!_loadedEntryId) return;
    var state = (root.OraTimelineEditor && root.OraTimelineEditor.getState)
      ? root.OraTimelineEditor.getState() : null;
    var trackTime = _trackTimeForSegment(state, _loadedEntryId, seg.start_ms);
    if (trackTime === null) {
      _setStatus('That moment isn’t on the timeline (it’s outside the trimmed clip range).');
      window.setTimeout(function () { _setStatus(''); }, 2200);
      return;
    }
    _suppressAutoScrollUntil = Date.now() + 800;
    document.dispatchEvent(new CustomEvent('ora:timeline-playhead-changed', {
      detail: {
        conversation_id: _conversationId,
        playhead_ms: trackTime,
        source: 'transcript',
      },
    }));
    // Optimistic highlight — playhead listeners will confirm.
    _setActiveSegmentIdx(idx, /*scroll=*/false);
  }

  function _setActiveSegmentIdx(idx, scroll) {
    if (idx === _activeSegmentIdx) return;
    if (_activeSegmentIdx >= 0 && _segmentEls[_activeSegmentIdx]) {
      _segmentEls[_activeSegmentIdx]
        .classList.remove('transcript-panel__segment--active');
    }
    _activeSegmentIdx = idx;
    if (idx < 0 || !_segmentEls[idx]) return;
    var el = _segmentEls[idx];
    el.classList.add('transcript-panel__segment--active');
    if (scroll && Date.now() >= _suppressAutoScrollUntil) {
      // Only auto-scroll when the row is outside the visible viewport;
      // scrollIntoView with block:'nearest' is the gentle behavior.
      var listRect = _listEl.getBoundingClientRect();
      var rowRect = el.getBoundingClientRect();
      if (rowRect.top < listRect.top || rowRect.bottom > listRect.bottom) {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }

  // ── transcript loading ───────────────────────────────────────────────────

  function _loadTranscript(entryId) {
    if (!_conversationId || !entryId) {
      _segments = [];
      _loadedEntryId = null;
      _renderSegments();
      _setStatus('No clip at the playhead.');
      return;
    }
    if (entryId === _loadedEntryId || entryId === _loadingEntryId) return;
    _loadingEntryId = entryId;
    if (_loadAbort) {
      try { _loadAbort.abort(); } catch (_ignored) { /* */ }
    }
    var ctrl = (typeof AbortController !== 'undefined')
      ? new AbortController() : null;
    _loadAbort = ctrl;
    _setStatus('Loading transcript…');
    var url = '/api/media-library/' + encodeURIComponent(_conversationId)
            + '/' + encodeURIComponent(entryId) + '/transcript';
    fetch(url, ctrl ? { signal: ctrl.signal } : undefined)
      .then(function (r) {
        if (r.status === 404) return { __notranscript: true };
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (entryId !== _loadingEntryId) return; // a newer load won the race
        _loadingEntryId = null;
        // Stale suggestions don't apply to a new clip's source range.
        if (_suggestionsForEntry && _suggestionsForEntry !== entryId) {
          _resetSuggestions();
        }
        if (data && data.__notranscript) {
          _segments = [];
          _loadedEntryId = entryId;
          _renderSegments();
          _setStatus('This clip hasn’t been transcribed yet.');
          return;
        }
        _segments = (data && data.segments) || [];
        _loadedEntryId = entryId;
        _renderSegments();
        if (!_segments.length) {
          _setStatus('Transcript is empty.');
        } else {
          _setStatus('');
        }
        _refreshActiveFromPlayhead();
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        if (entryId !== _loadingEntryId) return;
        _loadingEntryId = null;
        _setStatus('Couldn’t load transcript: ' + (err && err.message || err));
      });
  }

  function _refreshActiveFromPlayhead() {
    var state = (root.OraTimelineEditor && root.OraTimelineEditor.getState)
      ? root.OraTimelineEditor.getState() : null;
    if (!state) return;
    var playheadMs = Number(state.playhead_ms) || 0;
    var clip = _findActiveClip(state, playheadMs);
    if (!clip) {
      _setActiveSegmentIdx(-1, false);
      if (_loadedEntryId) {
        _segments = [];
        _loadedEntryId = null;
        _renderSegments();
        _setStatus('No clip at the playhead.');
      } else {
        _setStatus('No clip at the playhead.');
      }
      return;
    }
    if (clip.media_entry_id !== _loadedEntryId
        && clip.media_entry_id !== _loadingEntryId) {
      _loadTranscript(clip.media_entry_id);
      return;
    }
    if (clip.media_entry_id !== _loadedEntryId) return; // load in-flight
    var srcMs = _sourceTimeAt(clip, playheadMs);
    var idx = _segmentIdxAt(_segments, srcMs);
    _setActiveSegmentIdx(idx, /*scroll=*/true);
  }

  // ── suggestions section (Video Editing Suggestions framework) ───────────

  function _resetSuggestions() {
    _suggestionsForEntry = null;
    _suggestions = [];
    if (_suggSummaryEl) _suggSummaryEl.textContent = '';
    if (_suggListEl) _suggListEl.innerHTML = '';
    if (_suggRunBtn) _suggRunBtn.disabled = false;
  }

  function _onSuggestEdits() {
    if (_suggestRunning) return;
    if (!_loadedEntryId || !_segments.length) {
      _suggSummaryEl.textContent =
        'Load a clip with a transcript before requesting suggestions.';
      return;
    }
    if (!_conversationId) return;
    _suggestRunning = true;
    if (_suggRunBtn) {
      _suggRunBtn.disabled = true;
      _suggRunBtn.textContent = 'Thinking…';
    }
    _suggSummaryEl.textContent = '';
    _suggListEl.innerHTML = '';

    var url = '/api/media-library/' + encodeURIComponent(_conversationId)
            + '/' + encodeURIComponent(_loadedEntryId) + '/suggest-edits';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, data: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error((res.data && res.data.error) || 'request failed');
        }
        _suggestionsForEntry = res.data.entry_id || _loadedEntryId;
        _suggestions = res.data.suggestions || [];
        if (_suggSummaryEl) {
          _suggSummaryEl.textContent = res.data.summary || '';
        }
        _renderSuggestions();
      })
      .catch(function (err) {
        if (_suggSummaryEl) {
          _suggSummaryEl.textContent = 'Couldn’t generate suggestions: '
            + (err && err.message || err);
        }
      })
      .then(function () {
        _suggestRunning = false;
        if (_suggRunBtn) {
          _suggRunBtn.disabled = false;
          _suggRunBtn.textContent = 'Suggest edits';
        }
      });
  }

  function _renderSuggestions() {
    if (!_suggListEl) return;
    _suggListEl.innerHTML = '';
    if (!_suggestions.length) {
      var empty = document.createElement('div');
      empty.className = 'transcript-panel__sugg-empty';
      empty.textContent = 'No edits suggested for this clip.';
      _suggListEl.appendChild(empty);
      return;
    }
    var frag = document.createDocumentFragment();
    _suggestions.forEach(function (sug, idx) {
      frag.appendChild(_buildSuggestionRow(sug, idx));
    });
    _suggListEl.appendChild(frag);
  }

  function _buildSuggestionRow(sug, idx) {
    var row = document.createElement('div');
    row.className = 'transcript-panel__sugg-row transcript-panel__sugg-row--'
                  + sug.type;
    row.dataset.idx = String(idx);
    var label = document.createElement('div');
    label.className = 'transcript-panel__sugg-label';
    var typeBadge = document.createElement('span');
    typeBadge.className = 'transcript-panel__sugg-badge';
    typeBadge.textContent = _suggestionBadge(sug);
    var primary = document.createElement('span');
    primary.className = 'transcript-panel__sugg-primary';
    primary.textContent = _suggestionPrimaryText(sug);
    label.appendChild(typeBadge);
    label.appendChild(primary);
    var reason = document.createElement('div');
    reason.className = 'transcript-panel__sugg-reason';
    reason.textContent = sug.reason || '';
    var actions = document.createElement('div');
    actions.className = 'transcript-panel__sugg-actions';
    var applyBtn = document.createElement('button');
    applyBtn.type = 'button';
    applyBtn.className = 'transcript-panel__sugg-apply';
    applyBtn.textContent = 'Apply';
    applyBtn.addEventListener('click', function () {
      _applySuggestion(sug, row);
    });
    actions.appendChild(applyBtn);
    row.appendChild(label);
    row.appendChild(reason);
    row.appendChild(actions);
    return row;
  }

  function _suggestionBadge(sug) {
    if (sug.type === 'cut') return 'CUT';
    if (sug.type === 'chapter') return 'CHAP';
    if (sug.type === 'title_card') return 'TITLE';
    if (sug.type === 'transition') return 'TRANS';
    return (sug.type || '?').toUpperCase();
  }

  function _suggestionPrimaryText(sug) {
    if (sug.type === 'cut') {
      return _formatTimecode(sug.start_ms) + ' → ' + _formatTimecode(sug.end_ms);
    }
    if (sug.type === 'chapter') {
      return _formatTimecode(sug.at_ms) + '  ' + (sug.label || '');
    }
    if (sug.type === 'title_card') {
      return _formatTimecode(sug.at_ms) + '  "' + (sug.title || '') + '"';
    }
    if (sug.type === 'transition') {
      return _formatTimecode(sug.at_ms) + '  ' + (sug.kind || '')
           + ' (' + (sug.duration_ms || 0) + 'ms)';
    }
    return '';
  }

  function _applySuggestion(sug, rowEl) {
    var api = root.OraTimelineEditor;
    if (!api) {
      _flashRow(rowEl, 'Timeline editor not ready.', 'error');
      return;
    }
    var res = null;
    if (sug.type === 'cut') {
      var entryId = _suggestionsForEntry || _loadedEntryId;
      if (!entryId) {
        _flashRow(rowEl, 'No clip context — load the transcript first.', 'error');
        return;
      }
      if (typeof api.applyCutSuggestion !== 'function') {
        _flashRow(rowEl, 'Cut apply unavailable.', 'error');
        return;
      }
      res = api.applyCutSuggestion({
        media_entry_id: entryId,
        start_ms: sug.start_ms,
        end_ms: sug.end_ms,
      });
      if (res && res.ok) {
        _flashRow(rowEl,
                  'Applied (-' + Math.round((res.deleted_ms || 0) / 100) / 10 + 's).',
                  'success');
      } else {
        _flashRow(rowEl, (res && res.reason) || 'Apply failed.', 'error');
      }
    } else if (sug.type === 'chapter') {
      if (typeof api.applyChapterSuggestion !== 'function') {
        _flashRow(rowEl, 'Chapter apply unavailable.', 'error');
        return;
      }
      res = api.applyChapterSuggestion({
        at_ms: sug.at_ms,
        label: sug.label,
      });
      if (res && res.ok) {
        _flashRow(rowEl, 'Chapter marker added.', 'success');
      } else {
        _flashRow(rowEl, (res && res.reason) || 'Apply failed.', 'error');
      }
    } else if (sug.type === 'title_card') {
      if (typeof api.applyTitleCardSuggestion !== 'function') {
        _flashRow(rowEl, 'Title-card apply unavailable.', 'error');
        return;
      }
      res = api.applyTitleCardSuggestion({
        at_ms: sug.at_ms,
        duration_ms: sug.duration_ms,
        title: sug.title,
        subtitle: sug.subtitle,
      });
      if (res && res.ok) {
        _flashRow(rowEl, 'Title card added.', 'success');
      } else {
        _flashRow(rowEl, (res && res.reason) || 'Apply failed.', 'error');
      }
    } else if (sug.type === 'transition') {
      if (typeof api.applyTransitionSuggestion !== 'function') {
        _flashRow(rowEl, 'Transition apply unavailable.', 'error');
        return;
      }
      res = api.applyTransitionSuggestion({
        at_ms: sug.at_ms,
        duration_ms: sug.duration_ms,
        kind: sug.kind,
      });
      if (res && res.ok) {
        _flashRow(rowEl,
                  'Applied (' + (res.applied_kind || sug.kind) + ').',
                  'success');
      } else {
        _flashRow(rowEl, (res && res.reason) || 'Apply failed.', 'error');
      }
    } else {
      _flashRow(rowEl, 'Unknown suggestion type: ' + sug.type, 'error');
    }
  }

  function _flashRow(rowEl, msg, kind) {
    if (!rowEl) return;
    var existing = rowEl.querySelector('.transcript-panel__sugg-flash');
    if (existing) existing.remove();
    var flash = document.createElement('div');
    flash.className = 'transcript-panel__sugg-flash transcript-panel__sugg-flash--' + (kind || 'info');
    flash.textContent = msg;
    rowEl.appendChild(flash);
    if (kind === 'success') {
      rowEl.classList.add('transcript-panel__sugg-row--applied');
    }
    setTimeout(function () {
      if (flash.parentNode === rowEl) flash.remove();
    }, 4000);
  }

  // ── show / hide ──────────────────────────────────────────────────────────

  function _findVisualHost() {
    return document.querySelector('.visual-panel')
        || document.querySelector('.pane.right-pane');
  }

  function show() {
    var host = _findVisualHost();
    if (!host) return;
    _hostEl = host;
    if (!_rootEl) _build();
    if (!_rootEl.parentNode) host.appendChild(_rootEl);
    _rootEl.classList.add('transcript-panel--visible');
    _refreshActiveFromPlayhead();
  }

  function hide() {
    if (_rootEl) _rootEl.classList.remove('transcript-panel--visible');
  }

  function toggle() {
    if (_rootEl && _rootEl.classList.contains('transcript-panel--visible')) {
      hide();
    } else {
      show();
    }
  }

  // ── external plumbing ────────────────────────────────────────────────────

  function setConversationId(id) {
    _conversationId = id || null;
    _loadedEntryId = null;
    _loadingEntryId = null;
    _segments = [];
    if (_listEl) _renderSegments();
    _setStatus('');
    if (document.body.classList.contains('pane-mode-video')) {
      _refreshActiveFromPlayhead();
    }
  }

  function reload() {
    _loadedEntryId = null;
    _refreshActiveFromPlayhead();
  }

  function getState() {
    return {
      visible: !!(_rootEl && _rootEl.classList.contains('transcript-panel--visible')),
      conversation_id: _conversationId,
      loaded_entry_id: _loadedEntryId,
      segment_count: _segments.length,
      active_segment_idx: _activeSegmentIdx,
    };
  }

  function init() {
    document.addEventListener('ora:pane-mode-toggle', function (e) {
      var cur = e.detail && e.detail.current;
      if (cur === 'video') show(); else hide();
    });
    document.addEventListener('ora:conversation-selected', function (e) {
      var d = e.detail || {};
      var cid = d.conversation_id || d.id || null;
      if (cid) setConversationId(cid);
    });
    document.addEventListener('ora:timeline-playhead-changed', function () {
      if (!_rootEl || !_rootEl.classList.contains('transcript-panel--visible')) return;
      _refreshActiveFromPlayhead();
    });
    document.addEventListener('ora:timeline-mutated', function () {
      if (!_rootEl || !_rootEl.classList.contains('transcript-panel--visible')) return;
      _refreshActiveFromPlayhead();
    });
  }

  root.OraTranscriptPanel = {
    init: init,
    setConversationId: setConversationId,
    show: show,
    hide: hide,
    toggle: toggle,
    reload: reload,
    getState: getState,
    // exported for unit tests:
    _internals: {
      findActiveClip: _findActiveClip,
      sourceTimeAt: _sourceTimeAt,
      segmentIdxAt: _segmentIdxAt,
      trackTimeForSegment: _trackTimeForSegment,
    },
  };
})(typeof window !== 'undefined' ? window : this);
