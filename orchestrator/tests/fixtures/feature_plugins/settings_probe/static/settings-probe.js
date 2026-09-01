(function registerSettingsProbe(root) {
  'use strict';
  if (!root.OraSettingsSections || typeof root.OraSettingsSections.register !== 'function') {
    return;
  }
  root.OraSettingsSections.register({
    id: 'settings-probe',
    label: 'Settings probe',
    render: function render(body) {
      var note = document.createElement('p');
      note.textContent = 'Settings probe feature loaded.';
      body.appendChild(note);
    },
  });
}(typeof window !== 'undefined' ? window : globalThis));
