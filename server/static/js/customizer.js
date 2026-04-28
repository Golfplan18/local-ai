// Ora Customizer — Phases 1 + 2 (foundation + headings + body text + link + panes + buttons + wordmark + bridges)
//
// Customization mode entered by clicking the palette icon.
//   - Interface dims slightly
//   - Customizable elements rise above the dim and get a dashed outline
//   - Hovering shows a bolder outline; clicking opens an element overlay
//     near the clicked element with controls and (optionally) a sample
//   - Adjustments apply live and persist to localStorage as a layered
//     <style id="ora-user-customizations"> stylesheet
//   - Exit: click the palette icon again, press Escape, or click outside
//     any customizable element / overlay
//
// Axes are arrays of { label, var, type } so each registered element type
// can declare any combination of color / size / weight / font / unitless /
// pixel axes, and the renderer dispatches via AXIS_RENDERERS.

(() => {
  const STORAGE_KEY        = 'ora-customizations-by-theme';
  const LEGACY_STORAGE_KEY = 'ora-customizations';
  const MODE_CLASS         = 'customizer-active';
  const PALETTE_BUTTON_ID  = 'themeToggleBtn';
  const FONT_WEIGHTS       = ['100', '200', '300', '400', '500', '600', '700', '800', '900'];

  // ─── System fonts available on macOS, grouped by category ─────────
  // The font dropdown surfaces these. Each value is a complete font-family
  // declaration with sensible fallbacks.

  const SYSTEM_FONTS = [
    // System default (matches the foundation default)
    { label: 'System default', value: '-apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif', cat: 'system' },

    // Sans-serif
    { label: 'Helvetica Neue',   value: '"Helvetica Neue", Helvetica, Arial, sans-serif', cat: 'sans' },
    { label: 'Helvetica',        value: 'Helvetica, Arial, sans-serif', cat: 'sans' },
    { label: 'Arial',            value: 'Arial, sans-serif', cat: 'sans' },
    { label: 'Avenir',           value: 'Avenir, "Avenir Next", sans-serif', cat: 'sans' },
    { label: 'Avenir Next',      value: '"Avenir Next", Avenir, sans-serif', cat: 'sans' },
    { label: 'Futura',           value: 'Futura, sans-serif', cat: 'sans' },
    { label: 'Gill Sans',        value: '"Gill Sans", "Gill Sans MT", sans-serif', cat: 'sans' },
    { label: 'Lucida Grande',    value: '"Lucida Grande", sans-serif', cat: 'sans' },
    { label: 'Optima',           value: 'Optima, sans-serif', cat: 'sans' },
    { label: 'Tahoma',           value: 'Tahoma, sans-serif', cat: 'sans' },
    { label: 'Trebuchet MS',     value: '"Trebuchet MS", sans-serif', cat: 'sans' },
    { label: 'Verdana',          value: 'Verdana, sans-serif', cat: 'sans' },

    // Serif
    { label: 'American Typewriter', value: '"American Typewriter", serif', cat: 'serif' },
    { label: 'Baskerville',         value: 'Baskerville, serif', cat: 'serif' },
    { label: 'Didot',               value: 'Didot, serif', cat: 'serif' },
    { label: 'Garamond',            value: 'Garamond, serif', cat: 'serif' },
    { label: 'Georgia',             value: 'Georgia, serif', cat: 'serif' },
    { label: 'Hoefler Text',        value: '"Hoefler Text", serif', cat: 'serif' },
    { label: 'Palatino',            value: 'Palatino, "Palatino Linotype", serif', cat: 'serif' },
    { label: 'Times',               value: 'Times, serif', cat: 'serif' },
    { label: 'Times New Roman',     value: '"Times New Roman", Times, serif', cat: 'serif' },

    // Monospace
    { label: 'Courier',     value: 'Courier, monospace', cat: 'mono' },
    { label: 'Courier New', value: '"Courier New", Courier, monospace', cat: 'mono' },
    { label: 'Menlo',       value: 'Menlo, Monaco, Consolas, monospace', cat: 'mono' },
    { label: 'Monaco',      value: 'Monaco, Menlo, Consolas, monospace', cat: 'mono' },
    { label: 'SF Mono',     value: '"SF Mono", Menlo, Monaco, Consolas, monospace', cat: 'mono' },
  ];

  // ─── Element registry ──────────────────────────
  // Each entry declares which DOM elements are customizable, how to label
  // the element when selected, and which axes the customizer should expose.
  // Axes is an array of { label, var, type } — the renderer dispatches via
  // AXIS_RENDERERS based on the type field.

  const CUSTOMIZABLE = [
    {
      type: 'heading',
      selector: '.output-content h1, .output-content h2, .output-content h3, .output-content h4, .output-content h5, .output-content h6',
      label: (el) => `Heading ${parseInt(el.tagName.slice(1), 10)}`,
      getAxes: (el) => {
        const level = parseInt(el.tagName.slice(1), 10);
        return [
          { label: 'Color',       var: `--h${level}-color`,       type: 'color' },
          { label: 'Size',        var: `--h${level}-size`,        type: 'size' },
          { label: 'Weight',      var: `--h${level}-weight`,      type: 'weight' },
          { label: 'Font',        var: `--h${level}-font`,        type: 'font' },
          { label: 'Line-height', var: `--h${level}-line-height`, type: 'unitless' },
        ];
      },
      // Sample renders all 6 heading levels so the user can see the
      // hierarchy while editing one of them.
      renderSample: () => {
        const sample = document.createElement('div');
        sample.className = 'customizer-sample customizer-sample-headings';
        for (let i = 1; i <= 6; i++) {
          const h = document.createElement(`h${i}`);
          h.textContent = `Heading ${i}`;
          sample.appendChild(h);
        }
        return sample;
      }
    },
    {
      type: 'body-text',
      selector: '.output-content p',
      label: () => 'Body text',
      getAxes: () => [
        { label: 'Color', var: '--text-normal',     type: 'color' },
        { label: 'Size',  var: '--font-text-size',  type: 'size' },
        { label: 'Font',  var: '--font-text',       type: 'font' },
      ],
    },
    {
      type: 'link',
      selector: '.output-content a',
      label: () => 'Hyperlink',
      getAxes: () => [
        { label: 'Color',       var: '--link-color',       type: 'color' },
        { label: 'Hover color', var: '--link-color-hover', type: 'color' },
      ],
    },
    {
      type: 'pane',
      selector: '.input-pane, .chat-input-pane, .output-pane, .chat-output-pane, .right-pane',
      label: (el) => {
        const baseLabel = el.classList.contains('input-pane') || el.classList.contains('chat-input-pane') ? 'Input pane'
          : el.classList.contains('right-pane') ? 'Visual canvas'
          : 'Output pane';
        if (state.previewMode === 'private') return `${baseLabel} (Private mode)`;
        if (state.previewMode === 'stealth') return `${baseLabel} (Stealth mode)`;
        return baseLabel;
      },
      getAxes: (el) => {
        const isInput  = el.classList.contains('input-pane') || el.classList.contains('chat-input-pane');
        const isCanvas = el.classList.contains('right-pane');
        const surfaceVar = isInput  ? '--background-modifier-form-field'
                         : isCanvas ? '--ora-visual-canvas-bg'
                         :            '--background-secondary';

        // When previewing a mode, the border axis edits the universal
        // mode-tint variable (one color tints all panes in that mode).
        // Otherwise the per-pane border variable keeps panes independent.
        if (state.previewMode === 'private') {
          return [
            { label: 'Surface', var: surfaceVar, type: 'color' },
            { label: 'Border (Private)', var: '--ora-mode-private-pane-border', type: 'color' },
          ];
        }
        if (state.previewMode === 'stealth') {
          return [
            { label: 'Surface', var: surfaceVar, type: 'color' },
            { label: 'Border (Stealth)', var: '--ora-mode-stealth-pane-border', type: 'color' },
          ];
        }
        return [
          { label: 'Surface', var: surfaceVar, type: 'color' },
          {
            label: 'Border',
            var: isInput  ? '--ora-input-pane-border'
              : isCanvas ? '--ora-visual-canvas-border'
              :            '--ora-output-pane-border',
            type: 'color',
          },
        ];
      },
    },
    {
      type: 'spine-button',
      selector: '.spine-button',
      label: (el) => {
        if (state.previewMode === 'private' && el.dataset.modeButton === 'private') return 'Private mode button';
        if (state.previewMode === 'stealth' && el.dataset.modeButton === 'stealth') return 'Stealth mode button';
        return 'Spine button';
      },
      getAxes: (el) => {
        // Mode-button-in-its-mode: surface the four mode-specific tint axes.
        if (state.previewMode === 'private' && el.dataset.modeButton === 'private') {
          return [
            { label: 'Pane border',   var: '--ora-mode-private-pane-border',   type: 'color' },
            { label: 'Button border', var: '--ora-mode-private-button-border', type: 'color' },
            { label: 'Button icon',   var: '--ora-mode-private-button-icon',   type: 'color' },
            { label: 'Bridge label',  var: '--ora-mode-private-label',         type: 'color' },
          ];
        }
        if (state.previewMode === 'stealth' && el.dataset.modeButton === 'stealth') {
          return [
            { label: 'Pane border',   var: '--ora-mode-stealth-pane-border',   type: 'color' },
            { label: 'Button border', var: '--ora-mode-stealth-button-border', type: 'color' },
            { label: 'Button icon',   var: '--ora-mode-stealth-button-icon',   type: 'color' },
            { label: 'Bridge label',  var: '--ora-mode-stealth-label',         type: 'color' },
          ];
        }
        return [
          { label: 'Background', var: '--interactive-normal', type: 'color' },
          { label: 'Border',     var: '--ora-button-border',  type: 'color' },
          { label: 'Icon color', var: '--icon-color',         type: 'color' },
          { label: 'Icon hover', var: '--icon-color-hover',   type: 'color' },
        ];
      },
    },
    {
      type: 'wordmark',
      selector: '.spine-wordmark',
      label: () => 'Wordmark',
      getAxes: () => [
        { label: 'Base color',   var: '--ora-wordmark-base',   type: 'color' },
        { label: 'Bright color', var: '--ora-wordmark-bright', type: 'color' },
        { label: 'Hover color',  var: '--ora-wordmark-hover',  type: 'color' },
      ],
    },
    {
      type: 'bridge',
      selector: '.bridge-strip, .bridge-strip-right, .chatbot-divider',
      label: () => 'Bridge',
      getAxes: () => [
        { label: 'Handle color',   var: '--ora-bridge-handle',  type: 'color' },
        { label: 'Default height', var: '--ora-bridge-default', type: 'pixel' },
      ],
    },
  ];

  // ─── State ─────────────────────────────────────

  // previewMode = 'standard' | 'private' | 'stealth' — controls what the
  // interface visually shows during customization and which axes the
  // pane/spine-button entries expose. previewMode is captured by closures
  // in CUSTOMIZABLE entries via the `state` object so they can read it
  // even though the registry is defined before the state object.
  const state = { previewMode: 'standard' };

  let active         = false;
  let userStyle      = null;
  let starterOverlay = null;
  let elementOverlay = null;
  let currentTarget  = null;   // re-rendered when preview changes
  let savedMode      = null;   // actual mode preserved across customizer session

  // ─── Storage ───────────────────────────────────
  // Customizations are persisted per active theme. Each theme has its own
  // bucket inside the by-theme object, keyed by the theme id from
  // OraThemeLoader. On first load, any legacy "ora-customizations" blob
  // is migrated into the current active theme's bucket and the old key
  // is removed.

  const getActiveThemeId = () => {
    return (window.OraThemeLoader && window.OraThemeLoader.getActive()) || 'default';
  };

  const loadAllCustomizations = () => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; }
    catch { return {}; }
  };

  const saveAllCustomizations = (all) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  };

  const loadCustomizations = () => {
    const all = loadAllCustomizations();
    return all[getActiveThemeId()] || {};
  };

  const saveCustomizations = (customs) => {
    const all = loadAllCustomizations();
    const id = getActiveThemeId();
    if (Object.keys(customs).length === 0) {
      delete all[id];
    } else {
      all[id] = customs;
    }
    saveAllCustomizations(all);
  };

  const migrateLegacyCustomizations = () => {
    const legacy = localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!legacy) return;
    try {
      const data = JSON.parse(legacy);
      if (data && typeof data === 'object' && Object.keys(data).length > 0) {
        const all = loadAllCustomizations();
        const id = getActiveThemeId();
        // Don't clobber if the user already has by-theme customizations
        if (!all[id]) {
          all[id] = data;
          saveAllCustomizations(all);
        }
      }
    } catch {}
    localStorage.removeItem(LEGACY_STORAGE_KEY);
  };

  // ─── Apply user customizations as a layered stylesheet ─────────────

  const ensureUserStyle = () => {
    if (userStyle) return userStyle;
    userStyle = document.createElement('style');
    userStyle.id = 'ora-user-customizations';
    const base = document.querySelector('link[href*="ora-default.css"]');
    if (base && base.nextSibling) {
      base.parentNode.insertBefore(userStyle, base.nextSibling);
    } else {
      document.head.appendChild(userStyle);
    }
    return userStyle;
  };

  const applyCustomizations = () => {
    ensureUserStyle();
    const customs = loadCustomizations();
    if (Object.keys(customs).length === 0) {
      userStyle.textContent = '';
      return;
    }
    let css = ':root, body, body.theme-dark, body.theme-light {\n';
    for (const [variable, value] of Object.entries(customs)) {
      css += `  ${variable}: ${value};\n`;
    }
    css += '}\n';
    userStyle.textContent = css;
  };

  const setVariable = (variable, value) => {
    const customs = loadCustomizations();
    customs[variable] = value;
    saveCustomizations(customs);
    applyCustomizations();
  };

  const resetVariable = (variable) => {
    const customs = loadCustomizations();
    delete customs[variable];
    saveCustomizations(customs);
    applyCustomizations();
  };

  // ─── Tag/untag customizable elements ───────────────────

  const tagCustomizable = () => {
    CUSTOMIZABLE.forEach(entry => {
      document.querySelectorAll(entry.selector).forEach(el => {
        el.classList.add('customizable');
        el.dataset.customizableType = entry.type;
      });
    });
  };

  const untagCustomizable = () => {
    document.querySelectorAll('.customizable').forEach(el => {
      el.classList.remove('customizable');
      delete el.dataset.customizableType;
    });
  };

  const findEntry = (el) => {
    for (const entry of CUSTOMIZABLE) {
      if (el.matches(entry.selector)) return entry;
    }
    return null;
  };

  // ─── Helpers ───────────────────────────────────

  const getVariableValue = (name) => {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
  };

  const rgbToHex = (rgb) => {
    const m = rgb.match(/\d+/g);
    if (!m || m.length < 3) return '#000000';
    return '#' + m.slice(0, 3).map(x => parseInt(x).toString(16).padStart(2, '0')).join('');
  };

  const colorToHex = (value) => {
    if (!value) return '#000000';
    if (value.startsWith('#')) {
      // Pad 3-digit hex to 6-digit
      return value.length === 4 ? '#' + [...value.slice(1)].map(c => c + c).join('') : value;
    }
    if (value.startsWith('rgb')) return rgbToHex(value);
    return '#000000';
  };

  const makeControlRow = (label, control) => {
    const row = document.createElement('div');
    row.className = 'customizer-control-row';
    const lbl = document.createElement('label');
    lbl.textContent = label;
    row.appendChild(lbl);
    row.appendChild(control);
    return row;
  };

  // ─── Axis renderers (one per type) ─────────────────────

  const AXIS_RENDERERS = {
    color: (axis, el, controls) => {
      const value = getVariableValue(axis.var);
      const hex = colorToHex(value);
      const input = document.createElement('input');
      input.type = 'color';
      input.value = hex;
      input.addEventListener('input', e => setVariable(axis.var, e.target.value));
      controls.appendChild(makeControlRow(axis.label, input));
    },

    // Size — adapts unit (em/rem/px) to the current variable value
    size: (axis, el, controls) => {
      const variableValue = getVariableValue(axis.var);
      let unit, displayValue, step, min, max;
      if (variableValue.endsWith('em') && !variableValue.endsWith('rem')) {
        unit = 'em';
        const computed = getComputedStyle(el);
        const parentFs = parseFloat(getComputedStyle(el.parentElement).fontSize) || 16;
        displayValue = parseFloat(computed.fontSize) / parentFs;
        step = '0.05'; min = '0.5'; max = '5';
      } else if (variableValue.endsWith('rem')) {
        unit = 'rem';
        displayValue = parseFloat(variableValue);
        step = '0.05'; min = '0.5'; max = '5';
      } else {
        unit = 'px';
        displayValue = parseFloat(variableValue) || parseFloat(getComputedStyle(el).fontSize);
        step = '1'; min = '8'; max = '96';
      }
      const input = document.createElement('input');
      input.type = 'number';
      input.step = step;
      input.min = min;
      input.max = max;
      input.value = unit === 'px' ? Math.round(displayValue) : displayValue.toFixed(2);
      input.addEventListener('input', e => {
        if (e.target.value) setVariable(axis.var, e.target.value + unit);
      });
      controls.appendChild(makeControlRow(`${axis.label} (${unit})`, input));
    },

    // Pixel — for sizes that are always px (e.g., bridge default height)
    pixel: (axis, el, controls) => {
      const variableValue = getVariableValue(axis.var);
      const px = parseFloat(variableValue) || 0;
      const input = document.createElement('input');
      input.type = 'number';
      input.step = '1';
      input.min = '0';
      input.max = '500';
      input.value = Math.round(px);
      input.addEventListener('input', e => {
        if (e.target.value) setVariable(axis.var, e.target.value + 'px');
      });
      controls.appendChild(makeControlRow(`${axis.label} (px)`, input));
    },

    weight: (axis, el, controls) => {
      const variableValue = getVariableValue(axis.var);
      const select = document.createElement('select');
      FONT_WEIGHTS.forEach(w => {
        const opt = document.createElement('option');
        opt.value = w;
        opt.textContent = w;
        if (w === variableValue) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener('change', e => setVariable(axis.var, e.target.value));
      controls.appendChild(makeControlRow(axis.label, select));
    },

    // Font — dropdown of system fonts, grouped by category, with
    // "Current (custom)" surfacing if a non-listed value is set.
    font: (axis, el, controls) => {
      const variableValue = getVariableValue(axis.var);
      const select = document.createElement('select');

      const matched = SYSTEM_FONTS.find(f => f.value === variableValue);

      if (!matched && variableValue) {
        const opt = document.createElement('option');
        opt.value = variableValue;
        opt.textContent = 'Current (custom)';
        opt.selected = true;
        select.appendChild(opt);
      }

      // System default first
      const sys = SYSTEM_FONTS[0];
      const sysOpt = document.createElement('option');
      sysOpt.value = sys.value;
      sysOpt.textContent = sys.label;
      if (matched && matched === sys) sysOpt.selected = true;
      select.appendChild(sysOpt);

      // Grouped options
      [
        ['Sans-serif', 'sans'],
        ['Serif',      'serif'],
        ['Monospace',  'mono'],
      ].forEach(([groupLabel, cat]) => {
        const og = document.createElement('optgroup');
        og.label = groupLabel;
        SYSTEM_FONTS.filter(f => f.cat === cat).forEach(f => {
          const opt = document.createElement('option');
          opt.value = f.value;
          opt.textContent = f.label;
          if (matched && matched === f) opt.selected = true;
          og.appendChild(opt);
        });
        select.appendChild(og);
      });

      select.addEventListener('change', e => setVariable(axis.var, e.target.value));
      controls.appendChild(makeControlRow(axis.label, select));
    },

    // Unitless — for things like line-height (a numeric multiplier)
    unitless: (axis, el, controls) => {
      const variableValue = getVariableValue(axis.var);
      const input = document.createElement('input');
      input.type = 'number';
      input.step = '0.1';
      input.min = '0.8';
      input.max = '3';
      input.value = parseFloat(variableValue || '1.4').toFixed(2);
      input.addEventListener('input', e => {
        if (e.target.value) setVariable(axis.var, e.target.value);
      });
      controls.appendChild(makeControlRow(axis.label, input));
    },
  };

  // ─── Starter overlay (light/dark + instructions, near palette) ─────

  const showStarterOverlay = () => {
    if (starterOverlay) return;
    const palette = document.getElementById(PALETTE_BUTTON_ID);
    if (!palette) return;

    starterOverlay = document.createElement('div');
    starterOverlay.className = 'customizer-starter';
    starterOverlay.innerHTML = `
      <div class="customizer-starter-row">
        <button type="button" class="customizer-theme-toggle">
          <span class="customizer-theme-toggle-label"></span>
        </button>
      </div>
      <div class="customizer-preview-row">
        <div class="customizer-preview-label">Preview mode</div>
        <div class="customizer-preview-buttons">
          <button type="button" data-preview="standard">Standard</button>
          <button type="button" data-preview="private">Private</button>
          <button type="button" data-preview="stealth">Stealth</button>
        </div>
      </div>
      <div class="customizer-starter-hint">Click any highlighted item to customize it.</div>
    `;
    document.body.appendChild(starterOverlay);

    const rect = palette.getBoundingClientRect();
    starterOverlay.style.position = 'fixed';
    starterOverlay.style.bottom = `${window.innerHeight - rect.bottom}px`;
    starterOverlay.style.right = `${window.innerWidth - rect.left + 12}px`;

    const refreshLabel = () => {
      const label = starterOverlay.querySelector('.customizer-theme-toggle-label');
      const current = window.OraTheme ? window.OraTheme.get() : 'dark';
      label.textContent = current === 'dark' ? 'Switch to light' : 'Switch to dark';
    };
    refreshLabel();

    starterOverlay.querySelector('.customizer-theme-toggle').addEventListener('click', (e) => {
      e.stopPropagation();
      if (window.OraTheme) {
        window.OraTheme.toggle();
        refreshLabel();
      }
    });

    // Preview-mode picker — switches the visual tint of the interface and
    // the axes shown in element overlays. Doesn't actually enter the mode.
    const refreshPreviewActive = () => {
      starterOverlay.querySelectorAll('.customizer-preview-buttons button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.preview === state.previewMode);
      });
    };
    refreshPreviewActive();

    starterOverlay.querySelectorAll('.customizer-preview-buttons button').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        setPreviewMode(btn.dataset.preview);
        refreshPreviewActive();
      });
    });
  };

  const hideStarterOverlay = () => {
    if (starterOverlay) {
      starterOverlay.remove();
      starterOverlay = null;
    }
  };

  // ─── Element overlay (popover with arrow + sample + controls) ─────

  const showElementOverlay = (el) => {
    hideElementOverlay();
    const entry = findEntry(el);
    if (!entry) return;

    currentTarget = el;

    const label = entry.label(el);
    const axes  = entry.getAxes(el);

    elementOverlay = document.createElement('div');
    elementOverlay.className = 'customizer-element-overlay';

    const header = document.createElement('div');
    header.className = 'customizer-overlay-header';
    header.textContent = label;
    elementOverlay.appendChild(header);

    if (entry.renderSample) {
      elementOverlay.appendChild(entry.renderSample());
    }

    const controls = document.createElement('div');
    controls.className = 'customizer-overlay-controls';
    axes.forEach(axis => {
      const renderer = AXIS_RENDERERS[axis.type];
      if (renderer) renderer(axis, el, controls);
    });
    elementOverlay.appendChild(controls);

    const reset = document.createElement('button');
    reset.type = 'button';
    reset.className = 'customizer-overlay-reset';
    reset.textContent = 'Reset to default';
    reset.addEventListener('click', (e) => {
      e.stopPropagation();
      axes.forEach(axis => resetVariable(axis.var));
      showElementOverlay(el);
    });
    elementOverlay.appendChild(reset);

    const arrow = document.createElement('div');
    arrow.className = 'customizer-overlay-arrow';
    elementOverlay.appendChild(arrow);

    document.body.appendChild(elementOverlay);
    positionOverlay(elementOverlay, el, arrow);
  };

  const hideElementOverlay = () => {
    if (elementOverlay) {
      elementOverlay.remove();
      elementOverlay = null;
    }
    currentTarget = null;
  };

  // ─── Preview mode (simulates Private/Stealth without actually entering) ───

  const PREVIEW_LABELS = { private: 'Private', stealth: 'Stealth' };

  const setPreviewMode = (mode) => {
    if (mode !== 'standard' && mode !== 'private' && mode !== 'stealth') return;
    state.previewMode = mode;

    document.body.classList.remove('customizer-preview-private', 'customizer-preview-stealth');
    if (mode === 'private' || mode === 'stealth') {
      document.body.classList.add(`customizer-preview-${mode}`);
    }

    // Mirror the bridge-label text behavior of real modes during preview
    const modeLabel      = document.getElementById('bridgeModeLabel');
    const modeLabelRight = document.getElementById('bridgeModeLabelRight');
    const text = PREVIEW_LABELS[mode] || '';
    if (modeLabel) modeLabel.textContent = text;
    if (modeLabelRight) modeLabelRight.textContent = text;

    // Re-render the open overlay so axes reflect the new preview
    if (elementOverlay && currentTarget) {
      showElementOverlay(currentTarget);
    }
  };

  const positionOverlay = (overlay, target, arrow) => {
    const targetRect  = target.getBoundingClientRect();
    const overlayRect = overlay.getBoundingClientRect();
    const padding = 12;

    let left = targetRect.right + padding;
    let arrowSide = 'left';

    if (left + overlayRect.width > window.innerWidth - padding) {
      left = targetRect.left - overlayRect.width - padding;
      arrowSide = 'right';
    }

    let top = targetRect.top + (targetRect.height / 2) - (overlayRect.height / 2);
    if (top < padding) top = padding;
    if (top + overlayRect.height > window.innerHeight - padding) {
      top = window.innerHeight - overlayRect.height - padding;
    }

    overlay.style.position = 'fixed';
    overlay.style.left = `${left}px`;
    overlay.style.top  = `${top}px`;

    const arrowTop = (targetRect.top + targetRect.height / 2) - top - 6;
    arrow.style.top = `${arrowTop}px`;
    arrow.dataset.side = arrowSide;
  };

  // ─── Event handlers ────────────────────────────

  const onKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      exit();
    }
  };

  const onDocumentClick = (e) => {
    if (!active) return;

    if (e.target.closest('.customizer-starter') ||
        e.target.closest('.customizer-element-overlay') ||
        e.target.closest('.theme-library')) {
      return;
    }

    const customizable = e.target.closest('.customizable');
    if (customizable) {
      e.stopPropagation();
      e.preventDefault();
      showElementOverlay(customizable);
      return;
    }

    if (e.target.closest('#' + PALETTE_BUTTON_ID)) {
      return;
    }

    if (elementOverlay) {
      hideElementOverlay();
    }
    exit();
  };

  // ─── Public API ────────────────────────────────

  const enter = () => {
    if (active) return;
    active = true;
    document.body.classList.add(MODE_CLASS);

    // Save any active real mode and drop its class so preview is the only
    // tint source. Default the preview picker to whatever mode was active.
    savedMode = null;
    let initialPreview = 'standard';
    if (document.body.classList.contains('private-mode')) {
      savedMode = 'private';
      initialPreview = 'private';
      document.body.classList.remove('private-mode');
    } else if (document.body.classList.contains('stealth-mode')) {
      savedMode = 'stealth';
      initialPreview = 'stealth';
      document.body.classList.remove('stealth-mode');
    }

    tagCustomizable();
    showStarterOverlay();
    setPreviewMode(initialPreview);

    // Mount the theme library into the right pane while customization is active.
    const rightPane = document.querySelector('.right-pane');
    if (rightPane && window.OraThemeLibrary) {
      window.OraThemeLibrary.mount(rightPane);
    }

    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('click', onDocumentClick, true);
  };

  const exit = () => {
    if (!active) return;
    active = false;
    document.body.classList.remove(MODE_CLASS);
    document.body.classList.remove('customizer-preview-private', 'customizer-preview-stealth');
    state.previewMode = 'standard';

    // Clear preview-driven label text; if we restore a real mode, that mode's
    // own logic (inside index-v3.html's setMode) will repopulate it on next toggle.
    const modeLabel      = document.getElementById('bridgeModeLabel');
    const modeLabelRight = document.getElementById('bridgeModeLabelRight');
    if (modeLabel) modeLabel.textContent = '';
    if (modeLabelRight) modeLabelRight.textContent = '';

    if (savedMode) {
      document.body.classList.add(`${savedMode}-mode`);
      // Re-set the bridge labels to the restored mode's text
      const labels = { private: 'Private', stealth: 'Stealth' };
      const text = labels[savedMode] || '';
      if (modeLabel) modeLabel.textContent = text;
      if (modeLabelRight) modeLabelRight.textContent = text;
      savedMode = null;
    }

    untagCustomizable();
    hideStarterOverlay();
    hideElementOverlay();

    // Unmount theme library, restore right pane to its normal state.
    if (window.OraThemeLibrary) window.OraThemeLibrary.unmount();

    document.removeEventListener('keydown', onKeyDown);
    document.removeEventListener('click', onDocumentClick, true);
  };

  const toggle = () => {
    if (active) exit();
    else enter();
  };

  migrateLegacyCustomizations();
  applyCustomizations();

  // When the active theme changes, reapply customizations from that theme's
  // bucket (so each theme's tweaks come back when you switch to it).
  document.addEventListener('ora-theme-changed', () => {
    applyCustomizations();
  });

  window.OraCustomizer = { enter, exit, toggle };
})();
