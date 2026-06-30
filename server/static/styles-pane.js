/* Output Styles settings pane.
 *
 *   OraStylesPane.init(hostEl)  — mount into a container element
 *   OraStylesPane.destroy()     — clean up
 *
 * Lists the built-in Output Style profiles (GET /api/styles/registry) and sets
 * the account-wide default style (styles.default_id via GET/POST /api/settings).
 * Any single turn can override the default by typing `/style <id>` (or
 * `/style off`) in the chat. Mirrors the mount/destroy shape of models-pane.js.
 */
(function (root) {
  'use strict';

  var _host = null;

  function _json(r) { return r.json(); }

  function _esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function _saveDefault(id) {
    return fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates: { styles: { default_id: id } } }),
    }).then(_json);
  }

  function _row(id, name, desc, checked) {
    return '<label class="ora-style-row">'
      + '<input type="radio" name="ora-style-default" value="' + _esc(id) + '"'
      + (checked ? ' checked' : '') + '>'
      + '<span class="ora-style-name">' + _esc(name) + '</span>'
      + '<span class="ora-style-desc">' + _esc(desc) + '</span>'
      + '</label>';
  }

  function _render(host, styles, currentDefault) {
    var rows = [_row('', 'None', 'no Output Style — the engine default voice', !currentDefault)];
    styles.forEach(function (s) {
      rows.push(_row(s.id, s.display_name || s.id, s.description || '', s.id === currentDefault));
    });
    host.innerHTML =
      '<div class="ora-styles-pane">'
      + '<p class="ora-styles-intro">Choose the default Output Style applied to your results. '
      + 'Override any single turn by typing <code>/style &lt;id&gt;</code> '
      + '(or <code>/style off</code>) in the chat.</p>'
      + '<div class="ora-styles-list">' + rows.join('') + '</div>'
      + '<p class="ora-styles-status" data-role="status" aria-live="polite"></p>'
      + '</div>';
    var status = host.querySelector('[data-role="status"]');
    var inputs = host.querySelectorAll('input[name="ora-style-default"]');
    Array.prototype.forEach.call(inputs, function (el) {
      el.addEventListener('change', function () {
        status.textContent = 'Saving…';
        _saveDefault(el.value).then(function () {
          status.textContent = el.value
            ? ('Default style: ' + el.value)
            : 'No default style';
        }).catch(function () {
          status.textContent = 'Could not save — try again.';
        });
      });
    });
  }

  function init(host) {
    if (!host) return;
    _host = host;
    host.textContent = 'Loading Output Styles…';
    Promise.all([
      fetch('/api/styles/registry').then(_json).catch(function () { return { styles: [] }; }),
      fetch('/api/settings').then(_json).catch(function () { return { settings: {} }; }),
    ]).then(function (res) {
      if (_host !== host) return;  // a later init/destroy superseded us
      var styles = (res[0] && res[0].styles) || [];
      var settings = (res[1] && res[1].settings) || {};
      var cur = (settings.styles && settings.styles.default_id) || '';
      if (!styles.length) {
        host.innerHTML = '<p class="ora-styles-empty">No Output Style profiles found '
          + '(the style registry is unavailable).</p>';
        return;
      }
      _render(host, styles, cur);
    });
  }

  function destroy() {
    if (_host) { _host.innerHTML = ''; _host = null; }
  }

  root.OraStylesPane = { init: init, destroy: destroy };
})(typeof window !== 'undefined' ? window : this);
