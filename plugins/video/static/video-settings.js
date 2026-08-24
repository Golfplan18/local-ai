/* Video plugin Settings page. Owns capture and render settings end to end. */
(function (root) {
  'use strict';

  var PRESETS = [
    ['standard', 'Standard (1080p · 30 fps · MP4)'],
    ['high', 'High quality (source res · 60 fps · MP4)'],
    ['web', 'Web optimized (1080p · 30 fps · faststart MP4)'],
    ['mov', 'QuickTime (1080p · 30 fps · MOV / H.264)'],
    ['webm', 'WebM (1080p · 30 fps · VP9 / Opus)'],
    ['audio_only', 'Audio only (M4A · AAC 192k)'],
  ];

  function requestJson(url, options) {
    return fetch(url, options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
        return data;
      });
    });
  }

  function save(group, key, value, status) {
    var updates = {};
    updates[group] = {};
    updates[group][key] = value;
    status.textContent = 'Saving…';
    return requestJson('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates: updates }),
    }).then(function () {
      status.textContent = 'Saved';
    }).catch(function (error) {
      status.textContent = 'Could not save: ' + error.message;
    });
  }

  function saveRouting(preferred, fallback, status) {
    status.textContent = 'Saving…';
    return requestJson('/config/routing/slots', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slots: {
        video_generates: { preferred: preferred || null, fallback: fallback || [] },
      } }),
    }).then(function () {
      status.textContent = 'Saved';
    }).catch(function (error) {
      status.textContent = 'Could not save: ' + error.message;
    });
  }

  function field(body, labelText, input, note) {
    var row = document.createElement('label');
    row.className = 'video-settings__field';
    var label = document.createElement('span');
    label.className = 'video-settings__label';
    label.textContent = labelText;
    row.appendChild(label);
    row.appendChild(input);
    body.appendChild(row);
    if (note) {
      var help = document.createElement('p');
      help.className = 'video-settings__note';
      help.textContent = note;
      body.appendChild(help);
    }
  }

  function text(value) {
    var input = document.createElement('input');
    input.type = 'text';
    input.value = value || '';
    return input;
  }

  function number(value, min, max) {
    var input = document.createElement('input');
    input.type = 'number';
    input.min = String(min);
    input.max = String(max);
    input.value = String(value == null ? '' : value);
    return input;
  }

  function select(options, value) {
    var el = document.createElement('select');
    options.forEach(function (pair) {
      var option = document.createElement('option');
      option.value = String(pair[0]);
      option.textContent = pair[1];
      el.appendChild(option);
    });
    el.value = String(value == null ? '' : value);
    if (el.value !== String(value == null ? '' : value) && value) {
      var stale = document.createElement('option');
      stale.value = String(value);
      stale.textContent = String(value) + ' — not detected';
      el.appendChild(stale);
      el.value = String(value);
    }
    return el;
  }

  function section(body, title) {
    var element = document.createElement('section');
    element.className = 'video-settings__section';
    var heading = document.createElement('h4');
    heading.textContent = title;
    element.appendChild(heading);
    body.appendChild(element);
    return element;
  }

  function bind(input, group, key, status, coerce) {
    input.addEventListener('change', function () {
      save(group, key, coerce ? coerce(input.value) : input.value, status);
    });
  }

  function render(body) {
    body.textContent = 'Loading video settings…';
    return Promise.all([
      requestJson('/api/settings'),
      requestJson('/api/capture/devices').catch(function () {
        return { video: [], audio: [] };
      }),
      requestJson('/config/routing/slots'),
      requestJson('/api/capability/providers').catch(function () {
        return { slots: {} };
      }),
    ]).then(function (values) {
      var settings = values[0].settings || {};
      var devices = values[1] || {};
      var capture = settings.capture || {};
      var exports = settings.export || {};
      var routing = (values[2].slots || {}).video_generates || {};
      var providers = (values[3].slots || {}).video_generates || [];
      body.innerHTML = '';

      var status = document.createElement('div');
      status.className = 'video-settings__status';
      body.appendChild(status);

      var recording = section(body, 'Screen recording');
      var directory = text(capture.default_directory);
      field(recording, 'Save recordings to', directory,
        'Applies to the next recording. Off Record recordings stay inside their Dialogue.');
      bind(directory, 'capture', 'default_directory', status);

      var rate = select([24, 25, 30, 50, 60].map(function (value) {
        return [value, value + ' fps'];
      }), capture.frame_rate);
      field(recording, 'Frame rate', rate, '25–30 fps suits screen demos; use 50–60 for fast motion.');
      bind(rate, 'capture', 'frame_rate', status, function (value) { return Number(value); });

      var audioNames = (devices.audio || []).map(function (device) { return device.name; });
      var videoNames = (devices.video || []).map(function (device) { return device.name; })
        .filter(function (name) { return !/screen/i.test(name); });
      var microphone = audioNames.length
        ? select([['', '(system default)']].concat(
            audioNames.map(function (name) { return [name, name]; })
          ), capture.default_audio_device || '')
        : text(capture.default_audio_device || '');
      field(recording, 'Microphone / audio device', microphone,
        'To record system audio, choose an installed loopback device.');
      bind(microphone, 'capture', 'default_audio_device', status);

      var webcam = videoNames.length
        ? select([['', '(off — screen only)']].concat(
            videoNames.map(function (name) { return [name, name]; })
          ), capture.default_webcam_device || '')
        : text(capture.default_webcam_device || '');
      field(recording, 'Webcam picture-in-picture', webcam,
        'When selected, the webcam appears over the screen recording.');
      bind(webcam, 'capture', 'default_webcam_device', status);
      if (!audioNames.length && !videoNames.length) {
        var unavailable = document.createElement('p');
        unavailable.className = 'video-settings__note';
        unavailable.textContent = 'Device detection is unavailable; device names must match exactly.';
        recording.appendChild(unavailable);
      }

      var rendering = section(body, 'Media export');
      var exportDirectory = text(exports.default_directory);
      field(rendering, 'Default export directory', exportDirectory);
      bind(exportDirectory, 'export', 'default_directory', status);
      var preset = select(PRESETS, exports.default_render_preset || 'standard');
      field(rendering, 'Default render preset', preset);
      bind(preset, 'export', 'default_render_preset', status);
      var threshold = number(exports.background_render_threshold_seconds, 0, 7200);
      field(rendering, 'Background-render threshold (seconds)', threshold,
        'Set to 0 to always render in the background.');
      bind(threshold, 'export', 'background_render_threshold_seconds', status,
        function (value) { return Number(value); });

      var generation = section(body, 'AI video generation');
      var providerOptions = [['', '(use shipped default)']].concat(
        providers.map(function (provider) {
          return [provider.provider_id, provider.display_name || provider.provider_id];
        })
      );
      var preferred = select(providerOptions, routing.preferred || '');
      field(generation, 'Preferred model', preferred,
        'Video jobs run in the background and appear in Ora’s shared job queue.');
      var fallback = text((routing.fallback || []).join(', '));
      field(generation, 'Fallback models', fallback,
        'Provider IDs in retry order, separated by commas.');
      function saveGeneration() {
        var fallbacks = fallback.value.split(',').map(function (value) {
          return value.trim();
        }).filter(function (value) {
          return value && value !== preferred.value;
        });
        saveRouting(preferred.value, fallbacks, status);
      }
      preferred.addEventListener('change', saveGeneration);
      fallback.addEventListener('change', saveGeneration);
    }).catch(function (error) {
      body.textContent = 'Could not load video settings: ' + error.message;
    });
  }

  root.OraVideoSettings = { render: render };
})(typeof window !== 'undefined' ? window : globalThis);
