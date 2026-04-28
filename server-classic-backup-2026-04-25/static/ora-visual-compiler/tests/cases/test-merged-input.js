/**
 * tests/cases/test-merged-input.js — WP-3.3 client-side regression suite.
 *
 * Exports { label, run(ctx, record) } per the run.js case-file convention.
 *
 * Exercises chat-panel.js's send path: when a visual panel subscribed to
 * the chat has user drawings (captured by canvas-serializer's
 * captureFromPanel), the send path must POST multipart/form-data to
 * `/chat/multipart`. Empty visual-panel case must fall back to the legacy
 * JSON POST to `/chat` so text-only sessions stay unchanged.
 *
 * Coverage:
 *   1.  With spatial drawings → fetch called with '/chat/multipart'.
 *   2.  Request body is a FormData instance (not a JSON string).
 *   3.  FormData carries `message` field with the input text.
 *   4.  FormData carries `conversation_id` matching this.panelId.
 *   5.  FormData carries `spatial_representation` as a JSON string.
 *   6.  spatial_representation JSON parses successfully.
 *   7.  Parsed spatial_rep validates against schema (via OraCanvasSerializer).
 *   8.  Parsed spatial_rep has the expected entity count (3 rects + 1 arrow
 *       → 3 entities + 1 relationship).
 *   9.  Parsed spatial_rep's relationship is of type 'causal'.
 *  10.  Empty visual panel (no user drawings) → fetch called with '/chat'.
 *  11.  Empty case uses Content-Type application/json (not FormData).
 *  12.  Empty case body is a JSON string carrying the message.
 *  13.  _findSubscribedVisualPanel prefers panels matching bridge_subscribe_to.
 *  14.  When no visual panel mounted, send falls back to JSON POST.
 */

'use strict';

module.exports = {
  label: 'WP-3.3 — chat-panel merged-input send path (multipart vs JSON)',
  run: async function run(ctx, record) {
    const { win } = ctx;

    // Guard: harness dependencies.
    if (typeof win.ChatPanel !== 'function') {
      record('merged-input: harness — ChatPanel class exposed on window',
        false, 'typeof=' + typeof win.ChatPanel);
      return;
    }
    if (typeof win.OraCanvasSerializer === 'undefined') {
      record('merged-input: harness — OraCanvasSerializer exposed',
        false, 'canvas-serializer not loaded');
      return;
    }

    // ── Helpers ────────────────────────────────────────────────────────────

    /**
     * Build a minimal duck-typed VisualPanel-like object the chat panel's
     * send path can interrogate. The serializer reads attrs directly via
     * _getAttrs, and we expose userInputLayer as the panel's public field
     * (per the canvas-serializer contract).
     */
    function mkMockVisualPanel(panelId, shapes, opts) {
      opts = opts || {};
      var layer = {
        _canvasDims: { width: 500, height: 400 },
        children: shapes,
        getChildren: function () { return shapes; },
      };
      return {
        panelId: panelId,
        config: {
          id: panelId,
          type: 'visual',
          bridge_subscribe_to: opts.bridge_subscribe_to || 'main',
        },
        userInputLayer: layer,
      };
    }

    function mkRect(id, label, x, y, w, h) {
      return {
        attrs: {
          name: 'user-shape',
          userShapeType: 'rect',
          userShapeId: id,
          userLabel: label,
          x: x, y: y, width: w, height: h,
        },
        getClientRect: function () { return { x: x, y: y, width: w, height: h }; },
      };
    }

    function mkArrow(id, src, dst) {
      return {
        attrs: {
          name: 'user-shape',
          userShapeType: 'arrow',
          userShapeId: id,
          userLabel: '',
          connEndpointStart: src,
          connEndpointEnd:   dst,
          x: 0, y: 0,
        },
        getClientRect: function () { return { x: 0, y: 0, width: 0, height: 0 }; },
      };
    }

    /**
     * Build a minimal DOM element for the chat panel to init into.
     */
    function mkChatHost() {
      var host = win.document.createElement('div');
      host.style.cssText = 'width:600px;height:400px;';
      win.document.body.appendChild(host);
      return host;
    }

    /**
     * Install a mock fetch that captures the most recent call's
     * (url, options) and returns a fake SSE-style Response. Returns the
     * capture object with `.last`.
     */
    function installMockFetch() {
      var capture = { last: null };
      win.fetch = function (url, options) {
        capture.last = { url: url, options: options || {} };
        // Fake SSE body: emit a single response event and terminate. We
        // don't strictly need these bytes for the test, but ChatPanel will
        // try to read them.
        var chunks = [
          'data: {"type":"start"}\n',
          'data: {"type":"response","text":"ok"}\n',
          'data: {"type":"done"}\n',
        ];
        var encoder = new win.TextEncoder
          ? new win.TextEncoder()
          : { encode: function (s) { return Buffer.from(s, 'utf-8'); } };
        var idx = 0;
        var reader = {
          read: function () {
            if (idx >= chunks.length) return Promise.resolve({ done: true, value: undefined });
            var v = encoder.encode(chunks[idx++]);
            return Promise.resolve({ done: false, value: v });
          },
        };
        return Promise.resolve({
          status: 200,
          ok: true,
          body: { getReader: function () { return reader; } },
        });
      };
      return capture;
    }

    // Ensure TextDecoder is available in jsdom (Node's globalThis has it; mirror
    // onto the jsdom window so ChatPanel's new TextDecoder() call resolves).
    if (typeof win.TextDecoder === 'undefined') {
      win.TextDecoder = (typeof TextDecoder !== 'undefined') ? TextDecoder : global.TextDecoder;
    }
    if (typeof win.TextEncoder === 'undefined') {
      win.TextEncoder = (typeof TextEncoder !== 'undefined') ? TextEncoder : global.TextEncoder;
    }

    async function sendAndCapture(chat, textValue) {
      chat._input.value = textValue;
      var p = chat.sendMessage();
      await p;
    }

    // ── Test case 1–9: Multipart path with drawings ───────────────────────

    try {
      var host = mkChatHost();
      var chat = new win.ChatPanel(host, {
        id: 'main',
        is_main_feed: true,
        model_slot: 'breadth',
      });
      chat.init();

      // Mount a visual panel on window._panels with drawings.
      var shapes = [
        mkRect('u-rect-0', 'A', 50,  50,  40, 40),
        mkRect('u-rect-1', 'B', 250, 50,  40, 40),
        mkRect('u-rect-2', 'C', 450, 50,  40, 40),
        mkArrow('u-arr-0', 'u-rect-0', 'u-rect-1'),
      ];
      var visualPanel = mkMockVisualPanel('visual', shapes, { bridge_subscribe_to: 'main' });
      win._panels = { 'main': chat, 'visual': visualPanel };

      var cap = installMockFetch();
      await sendAndCapture(chat, 'Analyze this diagram');

      // 1. Multipart endpoint used.
      record('merged-input #1: drawings present → POST /chat/multipart',
        cap.last && cap.last.url === '/chat/multipart',
        'url=' + (cap.last && cap.last.url));

      var fd = cap.last && cap.last.options && cap.last.options.body;
      var isFormData = !!(fd && typeof fd.get === 'function' && typeof fd.append === 'function');
      // 2. body is FormData.
      record('merged-input #2: body is FormData',
        isFormData, 'typeof=' + (fd && fd.constructor && fd.constructor.name));

      // 3. message field.
      if (isFormData) {
        record('merged-input #3: FormData carries message=Analyze this diagram',
          fd.get('message') === 'Analyze this diagram',
          'got=' + JSON.stringify(fd.get('message')));
      } else {
        record('merged-input #3: FormData carries message field',
          false, 'body not FormData');
      }

      // 4. conversation_id matches panelId.
      if (isFormData) {
        record('merged-input #4: FormData conversation_id matches panel id',
          fd.get('conversation_id') === 'main',
          'got=' + JSON.stringify(fd.get('conversation_id')));
      } else {
        record('merged-input #4', false, 'body not FormData');
      }

      // 5. spatial_representation field exists.
      var srJson = isFormData ? fd.get('spatial_representation') : null;
      record('merged-input #5: spatial_representation field present',
        typeof srJson === 'string' && srJson.length > 0,
        'typeof=' + typeof srJson + ' len=' + (srJson && srJson.length));

      // 6. parses to JSON.
      var parsed = null;
      var parseOk = false;
      if (typeof srJson === 'string') {
        try { parsed = JSON.parse(srJson); parseOk = true; } catch (e) { parseOk = false; }
      }
      record('merged-input #6: spatial_representation JSON parses',
        parseOk && parsed && typeof parsed === 'object',
        'parseOk=' + parseOk);

      // 7. Validates against schema.
      if (parsed) {
        var v = win.OraCanvasSerializer.validate(parsed);
        record('merged-input #7: spatial_representation validates',
          v.valid === true,
          'valid=' + v.valid + ' errors=' +
            (v.errors || []).map(function (e) { return e.code; }).join(','));
      } else {
        record('merged-input #7', false, 'no parsed spatial_representation');
      }

      // 8. Correct entity/relationship counts.
      if (parsed) {
        record('merged-input #8: 3 rects + 1 arrow → 3 entities + 1 relationship',
          parsed.entities && parsed.entities.length === 3
            && parsed.relationships && parsed.relationships.length === 1,
          'ents=' + (parsed.entities && parsed.entities.length)
            + ' rels=' + (parsed.relationships && parsed.relationships.length));
      } else {
        record('merged-input #8', false, 'no parsed spatial_representation');
      }

      // 9. arrow → 'causal'.
      if (parsed && parsed.relationships && parsed.relationships[0]) {
        record('merged-input #9: arrow relationship.type === "causal"',
          parsed.relationships[0].type === 'causal',
          'type=' + parsed.relationships[0].type);
      } else {
        record('merged-input #9', false, 'missing relationship');
      }

      host.remove();
      delete win._panels;
    } catch (e) {
      record('merged-input multipart suite', false,
        'threw: ' + (e.stack || e.message || e));
    }

    // ── Test case 10–12: Empty visual panel → JSON path ────────────────────

    try {
      var host2 = mkChatHost();
      var chat2 = new win.ChatPanel(host2, {
        id: 'main',
        is_main_feed: true,
        model_slot: 'breadth',
      });
      chat2.init();

      // Visual panel exists but has no user shapes → captureFromPanel returns null.
      var emptyVisual = mkMockVisualPanel('visual', [], { bridge_subscribe_to: 'main' });
      win._panels = { 'main': chat2, 'visual': emptyVisual };

      var cap2 = installMockFetch();
      await sendAndCapture(chat2, 'Plain text message');

      // 10. Backward-compat JSON endpoint.
      record('merged-input #10: empty visual → POST /chat (JSON fallback)',
        cap2.last && cap2.last.url === '/chat',
        'url=' + (cap2.last && cap2.last.url));

      // 11. Content-Type header is application/json.
      var headers = cap2.last && cap2.last.options && cap2.last.options.headers;
      var ctHeader = headers && (headers['Content-Type'] || headers['content-type']);
      record('merged-input #11: Content-Type=application/json on JSON path',
        ctHeader === 'application/json',
        'ct=' + ctHeader);

      // 12. Body is a JSON string that parses to { message, history, panel_id, is_main_feed }.
      var body12 = cap2.last && cap2.last.options && cap2.last.options.body;
      var parsedBody = null;
      try { parsedBody = JSON.parse(body12); } catch (e) { parsedBody = null; }
      record('merged-input #12: JSON body carries message field',
        parsedBody && parsedBody.message === 'Plain text message',
        'msg=' + (parsedBody && parsedBody.message));

      host2.remove();
      delete win._panels;
    } catch (e) {
      record('merged-input JSON fallback suite', false,
        'threw: ' + (e.stack || e.message || e));
    }

    // ── Test case 13: _findSubscribedVisualPanel discovery ─────────────────

    try {
      var host3 = mkChatHost();
      var chat3 = new win.ChatPanel(host3, {
        id: 'main',
        is_main_feed: true,
        model_slot: 'breadth',
      });
      chat3.init();

      var vp3 = mkMockVisualPanel('visual', [
        mkRect('r0', 'A', 10, 10, 20, 20),
      ], { bridge_subscribe_to: 'main' });
      win._panels = { 'main': chat3, 'visual': vp3 };

      var found = chat3._findSubscribedVisualPanel();
      record('merged-input #13: _findSubscribedVisualPanel locates subscribed panel',
        found === vp3, 'match=' + (found === vp3));

      host3.remove();
      delete win._panels;
    } catch (e) {
      record('merged-input #13', false, 'threw: ' + (e.stack || e.message || e));
    }

    // ── Test case 14: No visual panel mounted → JSON fallback ──────────────

    try {
      // Clear any OraPanels.visual from earlier test globals to force null.
      var savedVisual = (win.OraPanels && win.OraPanels.visual) || null;
      if (win.OraPanels) { win.OraPanels.visual = null; }

      var host4 = mkChatHost();
      var chat4 = new win.ChatPanel(host4, {
        id: 'main',
        is_main_feed: true,
        model_slot: 'breadth',
      });
      chat4.init();
      win._panels = { 'main': chat4 };

      var cap4 = installMockFetch();
      await sendAndCapture(chat4, 'No visual here');

      record('merged-input #14: no visual panel → JSON POST /chat',
        cap4.last && cap4.last.url === '/chat',
        'url=' + (cap4.last && cap4.last.url));

      host4.remove();
      delete win._panels;
      if (win.OraPanels) { win.OraPanels.visual = savedVisual; }
    } catch (e) {
      record('merged-input #14', false, 'threw: ' + (e.stack || e.message || e));
    }
  },
};
