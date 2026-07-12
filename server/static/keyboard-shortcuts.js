/*
 * keyboard-shortcuts.js
 *
 * Runtime shortcut registry for Ora's browser UI. It owns the canonical
 * defaults, user overrides from /api/settings, duplicate checks, and the
 * built-in documentation data used by Settings -> Shortcuts.
 */
(function (root) {
  'use strict';

  var _settings = {};
  var _loaded = false;

  var isMac = (typeof navigator !== 'undefined')
    ? /Mac|iPhone|iPad|iPod/.test(navigator.platform || '')
    : true;

  var DEFINITIONS = [
    {
      id: 'app_open_sidebar',
      category: 'Navigation',
      label: 'Open Dialogue sidebar',
      description: 'Expands the Dialogue list and focuses navigation.',
      context: 'Global',
      defaultShortcut: 'Mod+K',
      editable: true,
    },
    {
      id: 'app_new_conversation',
      category: 'Navigation',
      label: 'Start new Dialogue',
      description: 'Creates a fresh Ora Dialogue.',
      context: 'Global',
      defaultShortcut: 'Mod+J',
      editable: true,
    },
    {
      id: 'app_show_shortcuts',
      category: 'Navigation',
      label: 'Open shortcut help',
      description: 'Opens Settings directly to the shortcut documentation.',
      context: 'Global',
      defaultShortcut: 'Shift+?',
      editable: true,
    },
    {
      id: 'chat_submit',
      category: 'Composer',
      label: 'Submit focused input',
      description: 'Sends the focused composer input (the Inquiry pane). Shift+Enter inserts a newline.',
      context: 'Composer text fields',
      defaultShortcut: 'Enter',
      editable: false,
    },
    {
      id: 'overlay_dismiss',
      category: 'Overlays',
      label: 'Dismiss active overlay',
      description: 'Closes the active menu, popover, sidebar, or modal when that surface owns Escape.',
      context: 'Active overlay',
      defaultShortcut: 'Escape',
      editable: false,
    },
    {
      id: 'video_toggle_capture',
      category: 'Video',
      label: 'Toggle capture',
      description: 'Starts, resumes, or stops capture while video mode is active.',
      context: 'Video mode',
      defaultShortcut: 'Mod+Alt+R',
      editable: true,
    },
    {
      id: 'video_export',
      category: 'Video',
      label: 'Render last-used export preset',
      description: 'Starts a render using the most recently used export preset.',
      context: 'Video mode',
      defaultShortcut: 'Mod+Shift+E',
      editable: true,
    },
    {
      id: 'timeline_undo',
      category: 'Timeline',
      label: 'Undo timeline edit',
      description: 'Steps the timeline edit history backward.',
      context: 'Visible timeline',
      defaultShortcut: 'Mod+Z',
      editable: true,
    },
    {
      id: 'timeline_redo',
      category: 'Timeline',
      label: 'Redo timeline edit',
      description: 'Steps the timeline edit history forward.',
      context: 'Visible timeline',
      defaultShortcut: 'Mod+Shift+Z',
      editable: true,
    },
    {
      id: 'timeline_duplicate',
      category: 'Timeline',
      label: 'Duplicate selected clip',
      description: 'Copies the selected clip and places the copy after it.',
      context: 'Visible timeline',
      defaultShortcut: 'Mod+D',
      editable: true,
    },
    {
      id: 'timeline_copy',
      category: 'Timeline',
      label: 'Copy selected clip',
      description: 'Copies the selected clip to the timeline clipboard.',
      context: 'Visible timeline',
      defaultShortcut: 'Mod+C',
      editable: true,
    },
    {
      id: 'timeline_paste',
      category: 'Timeline',
      label: 'Paste clip at playhead',
      description: 'Pastes the timeline clipboard on the source track at the playhead.',
      context: 'Visible timeline',
      defaultShortcut: 'Mod+V',
      editable: true,
    },
    {
      id: 'timeline_split',
      category: 'Timeline',
      label: 'Split selected clip',
      description: 'Splits the selected clip at the current playhead.',
      context: 'Visible timeline',
      defaultShortcut: 'S',
      editable: true,
    },
    {
      id: 'timeline_delete',
      category: 'Timeline',
      label: 'Delete selected clip',
      description: 'Removes the selected clip from the timeline.',
      context: 'Visible timeline',
      defaultShortcut: 'Delete',
      editable: true,
      aliases: ['Backspace'],
    },
    {
      id: 'visual_zoom_in',
      category: 'Visual canvas',
      label: 'Zoom in',
      description: 'Zooms the visual canvas in.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Plus',
      editable: true,
      aliases: ['=', 'Shift+Plus'],
      binding: 'tool:zoom_in',
    },
    {
      id: 'visual_zoom_out',
      category: 'Visual canvas',
      label: 'Zoom out',
      description: 'Zooms the visual canvas out.',
      context: 'Focused visual canvas',
      defaultShortcut: '-',
      editable: true,
      aliases: ['_', 'Shift+_'],
      binding: 'tool:zoom_out',
    },
    {
      id: 'visual_zoom_100',
      category: 'Visual canvas',
      label: 'Zoom to 100%',
      description: 'Returns the visual canvas to 100 percent zoom.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Mod+0',
      editable: true,
      binding: 'tool:zoom_100',
    },
    {
      id: 'visual_zoom_fit',
      category: 'Visual canvas',
      label: 'Zoom to fit',
      description: 'Fits the visual content into the canvas viewport.',
      context: 'Focused visual canvas',
      defaultShortcut: 'F',
      editable: true,
      aliases: ['Z E'],
      binding: 'tool:zoom_fit',
    },
    {
      id: 'visual_zoom_selection',
      category: 'Visual canvas',
      label: 'Zoom to selection',
      description: 'Frames the current selection, falling back to fit when nothing is selected.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Mod+Shift+F',
      editable: true,
    },
    {
      id: 'visual_pan_hold',
      category: 'Visual canvas',
      label: 'Hold to pan',
      description: 'Temporarily enters pan mode while held.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Space',
      editable: false,
      binding: 'tool:pan',
    },
    {
      id: 'visual_nudge_view',
      category: 'Visual canvas',
      label: 'Nudge view',
      description: 'Moves the canvas viewport when no semantic node or user object is selected. Shift+Arrow nudges farther.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Arrow keys',
      fixedDisplay: 'Arrow keys',
      editable: false,
    },
    {
      id: 'visual_semantic_nav',
      category: 'Visual canvas',
      label: 'Navigate semantic visual nodes',
      description: 'Arrow keys move between semantic nodes, Enter descends, and Escape ascends.',
      context: 'Focused rendered visual',
      defaultShortcut: 'Arrow keys / Enter / Escape',
      fixedDisplay: 'Arrow keys / Enter / Escape',
      editable: false,
    },
    {
      id: 'visual_select_tool',
      category: 'Visual tools',
      label: 'Select tool',
      description: 'Activates selection for user-created canvas objects.',
      context: 'Focused visual canvas',
      defaultShortcut: 'S',
      editable: true,
      binding: 'tool:select',
    },
    {
      id: 'visual_rect_tool',
      category: 'Visual tools',
      label: 'Rectangle tool',
      description: 'Activates rectangle drawing.',
      context: 'Focused visual canvas',
      defaultShortcut: 'R',
      editable: true,
      binding: 'tool:rect',
    },
    {
      id: 'visual_ellipse_tool',
      category: 'Visual tools',
      label: 'Ellipse tool',
      description: 'Activates ellipse drawing.',
      context: 'Focused visual canvas',
      defaultShortcut: 'E',
      editable: true,
      binding: 'tool:ellipse',
    },
    {
      id: 'visual_diamond_tool',
      category: 'Visual tools',
      label: 'Diamond tool',
      description: 'Activates diamond drawing.',
      context: 'Focused visual canvas',
      defaultShortcut: 'D',
      editable: true,
      binding: 'tool:diamond',
    },
    {
      id: 'visual_line_tool',
      category: 'Visual tools',
      label: 'Line tool',
      description: 'Activates line drawing.',
      context: 'Focused visual canvas',
      defaultShortcut: 'L',
      editable: true,
      binding: 'tool:line',
    },
    {
      id: 'visual_arrow_tool',
      category: 'Visual tools',
      label: 'Arrow tool',
      description: 'Activates arrow drawing.',
      context: 'Focused visual canvas',
      defaultShortcut: 'A',
      editable: true,
      binding: 'tool:arrow',
    },
    {
      id: 'visual_text_tool',
      category: 'Visual tools',
      label: 'Text tool',
      description: 'Activates text placement.',
      context: 'Focused visual canvas',
      defaultShortcut: 'T',
      editable: true,
      binding: 'tool:text',
    },
    {
      id: 'visual_callout_tool',
      category: 'Annotation tools',
      label: 'Callout tool',
      description: 'Activates callout annotation.',
      context: 'Focused visual canvas',
      defaultShortcut: 'C',
      editable: true,
      binding: 'tool:callout',
    },
    {
      id: 'visual_highlight_tool',
      category: 'Annotation tools',
      label: 'Highlight tool',
      description: 'Activates highlight annotation.',
      context: 'Focused visual canvas',
      defaultShortcut: 'H',
      editable: true,
      binding: 'tool:highlight',
    },
    {
      id: 'visual_strike_tool',
      category: 'Annotation tools',
      label: 'Strikethrough tool',
      description: 'Activates strikethrough annotation.',
      context: 'Focused visual canvas',
      defaultShortcut: 'X',
      editable: true,
      binding: 'tool:strikethrough',
    },
    {
      id: 'visual_sticky_tool',
      category: 'Annotation tools',
      label: 'Sticky note tool',
      description: 'Activates sticky-note annotation.',
      context: 'Focused visual canvas',
      defaultShortcut: 'N',
      editable: true,
      binding: 'tool:sticky',
    },
    {
      id: 'visual_pen_tool',
      category: 'Annotation tools',
      label: 'Pen tool',
      description: 'Activates pen annotation.',
      context: 'Focused visual canvas',
      defaultShortcut: 'P',
      editable: true,
      binding: 'tool:pen',
    },
    {
      id: 'visual_delete_selected',
      category: 'Visual canvas',
      label: 'Delete selected object',
      description: 'Deletes selected shapes or annotations.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Delete',
      editable: true,
      aliases: ['Backspace'],
    },
    {
      id: 'visual_undo',
      category: 'Visual canvas',
      label: 'Undo visual edit',
      description: 'Steps the canvas edit history backward.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Mod+Z',
      editable: true,
      binding: 'tool:undo',
    },
    {
      id: 'visual_redo',
      category: 'Visual canvas',
      label: 'Redo visual edit',
      description: 'Steps the canvas edit history forward.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Mod+Shift+Z',
      editable: true,
      aliases: ['Mod+Y'],
      binding: 'tool:redo',
    },
    {
      id: 'visual_save',
      category: 'Visual canvas',
      label: 'Save canvas',
      description: 'Saves the active canvas state.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Mod+S',
      editable: true,
      binding: 'tool:save',
    },
    {
      id: 'visual_new_canvas',
      category: 'Visual canvas',
      label: 'New canvas',
      description: 'Clears the current canvas after the normal canvas command guardrails.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Mod+N',
      editable: true,
      binding: 'tool:new_canvas',
    },
    {
      id: 'visual_generate_image',
      category: 'Visual tools',
      label: 'Generate image',
      description: 'Opens the image-generation capability popover.',
      context: 'Focused visual canvas',
      defaultShortcut: 'Shift+G',
      editable: true,
      binding: 'capability:image_generates',
    },
    {
      id: 'visual_toolbar_selector',
      category: 'Visual tools',
      label: 'Specialty toolbar selector',
      description: 'Opens the specialty toolbar picker.',
      context: 'Visual workspace',
      defaultShortcut: 'Shift+T',
      editable: true,
      binding: 'tool:toolbar_selector',
    },
    {
      id: 'mask_brush_smaller',
      category: 'Image mask',
      label: 'Decrease brush size',
      description: 'Shrinks the active mask brush.',
      context: 'Mask brush tool',
      defaultShortcut: '[',
      editable: true,
    },
    {
      id: 'mask_brush_larger',
      category: 'Image mask',
      label: 'Increase brush size',
      description: 'Enlarges the active mask brush.',
      context: 'Mask brush tool',
      defaultShortcut: ']',
      editable: true,
    },
    {
      id: 'mask_toggle_eraser',
      category: 'Image mask',
      label: 'Toggle mask eraser',
      description: 'Switches between drawing and erasing in the mask brush tool.',
      context: 'Mask brush tool',
      defaultShortcut: 'E',
      editable: true,
    },
    {
      id: 'mask_clear',
      category: 'Image mask',
      label: 'Clear mask',
      description: 'Clears the active mask overlay.',
      context: 'Mask brush tool',
      defaultShortcut: 'Escape',
      editable: false,
    },
    {
      id: 'sidebar_next_row',
      category: 'Sidebar',
      label: 'Move to next row',
      description: 'Moves focus to the next actionable sidebar row.',
      context: 'Open sidebar',
      defaultShortcut: 'ArrowDown',
      editable: false,
    },
    {
      id: 'sidebar_prev_row',
      category: 'Sidebar',
      label: 'Move to previous row',
      description: 'Moves focus to the previous actionable sidebar row.',
      context: 'Open sidebar',
      defaultShortcut: 'ArrowUp',
      editable: false,
    },
    {
      id: 'sidebar_activate_row',
      category: 'Sidebar',
      label: 'Activate focused row',
      description: 'Loads or activates the focused sidebar row.',
      context: 'Open sidebar',
      defaultShortcut: 'Enter',
      editable: false,
    },
    {
      id: 'sidebar_delete_row',
      category: 'Sidebar',
      label: 'Close focused row',
      description: 'Closes or dismisses the focused sidebar row.',
      context: 'Open sidebar',
      defaultShortcut: 'Delete',
      editable: false,
      aliases: ['Backspace'],
    },
  ];

  var RESERVED = [
    { shortcut: 'Mod+Q', label: 'Quit app/browser', source: 'macOS / browser', severity: 'block' },
    { shortcut: 'Mod+W', label: 'Close current tab or window', source: 'browser', severity: 'block' },
    { shortcut: 'Mod+Shift+W', label: 'Close current window', source: 'browser', severity: 'block' },
    { shortcut: 'Mod+T', label: 'Open new browser tab', source: 'browser', severity: 'block' },
    { shortcut: 'Mod+Shift+T', label: 'Reopen closed tab', source: 'browser', severity: 'block' },
    { shortcut: 'Mod+L', label: 'Focus address bar', source: 'browser', severity: 'block' },
    { shortcut: 'Mod+R', label: 'Reload page', source: 'browser', severity: 'block' },
    { shortcut: 'Mod+Shift+R', label: 'Hard reload page', source: 'browser', severity: 'block' },
    { shortcut: 'Mod+N', label: 'New browser window', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+Shift+N', label: 'New private/incognito window', source: 'browser', severity: 'block' },
    { shortcut: 'Mod+O', label: 'Open file', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+P', label: 'Print page', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+S', label: 'Save page', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+F', label: 'Find in page', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+G', label: 'Find next', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+D', label: 'Bookmark page', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+H', label: 'Browser history / hide app', source: 'browser / OS', severity: 'block' },
    { shortcut: 'Mod+M', label: 'Minimize window on macOS', source: 'macOS', severity: 'block', platform: 'mac' },
    { shortcut: 'Mod+Space', label: 'Spotlight search', source: 'macOS', severity: 'block', platform: 'mac' },
    { shortcut: 'Mod+Alt+Escape', label: 'Force Quit Applications', source: 'macOS', severity: 'block', platform: 'mac' },
    { shortcut: 'Mod+Alt+I', label: 'Open developer tools', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+Alt+J', label: 'Open developer console', source: 'browser', severity: 'warn' },
    { shortcut: 'Mod+Shift+C', label: 'Element picker / developer tools', source: 'browser', severity: 'warn' },
    { shortcut: 'Ctrl+Tab', label: 'Next browser tab', source: 'browser', severity: 'block' },
    { shortcut: 'Ctrl+Shift+Tab', label: 'Previous browser tab', source: 'browser', severity: 'block' },
    { shortcut: 'Alt+ArrowLeft', label: 'Browser back', source: 'browser', severity: 'block' },
    { shortcut: 'Alt+ArrowRight', label: 'Browser forward', source: 'browser', severity: 'block' },
  ];

  var _byId = Object.create(null);
  var _byBinding = Object.create(null);
  DEFINITIONS.forEach(function (def) {
    _byId[def.id] = def;
    if (def.binding && !_byBinding[def.binding]) _byBinding[def.binding] = def.id;
  });

  function _shortcutMap(settings) {
    var s = settings || _settings || {};
    return (s.keyboard && s.keyboard.shortcuts) || {};
  }

  function _hasShortcutOverride(id, settings) {
    var override = _shortcutMap(settings)[id];
    return typeof override === 'string' && !!override.trim();
  }

  function _isTypingTarget(target) {
    if (!target) return false;
    var tag = (target.tagName || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    return !!target.isContentEditable;
  }

  function normalizeShortcut(input) {
    if (!input) return '';
    var raw = String(input).trim();
    if (!raw) return '';
    if (raw === '+') return 'Plus';
    if (raw.indexOf(' ') > -1 && raw.indexOf('+') === -1) {
      return raw.split(/\s+/).map(normalizeShortcut).filter(Boolean).join(' ');
    }
    var parts = raw.split('+').map(function (p) { return p.trim(); }).filter(Boolean);
    var mods = { Mod: false, Ctrl: false, Alt: false, Shift: false };
    var key = '';
    parts.forEach(function (part) {
      var lower = part.toLowerCase();
      if (lower === 'mod' || lower === 'cmd' || lower === 'command') mods.Mod = true;
      else if (lower === 'ctrl' || lower === 'control') mods.Ctrl = true;
      else if (lower === 'alt' || lower === 'option' || lower === 'opt') mods.Alt = true;
      else if (lower === 'shift') mods.Shift = true;
      else key = _normalizeKey(part);
    });
    if (!key) return '';
    var out = [];
    if (mods.Mod) out.push('Mod');
    if (mods.Ctrl) out.push('Ctrl');
    if (mods.Alt) out.push('Alt');
    if (mods.Shift) out.push('Shift');
    out.push(key);
    return out.join('+');
  }

  function _normalizeKey(key) {
    var k = String(key || '').trim();
    if (!k) return '';
    var aliases = {
      '+': 'Plus',
      ' ': 'Space',
      Spacebar: 'Space',
      Esc: 'Escape',
      Del: 'Delete',
      Return: 'Enter',
      Up: 'ArrowUp',
      Down: 'ArrowDown',
      Left: 'ArrowLeft',
      Right: 'ArrowRight',
    };
    if (aliases[k]) return aliases[k];
    if (/^arrow(up|down|left|right)$/i.test(k)) {
      return 'Arrow' + k.slice(5, 6).toUpperCase() + k.slice(6).toLowerCase();
    }
    if (k.length === 1) return k.toUpperCase();
    if (/^f\d{1,2}$/i.test(k)) return k.toUpperCase();
    return k.slice(0, 1).toUpperCase() + k.slice(1);
  }

  function eventToShortcut(e) {
    if (!e) return '';
    var key = _normalizeKey(e.key || e.code || '');
    if (!key || key === 'Shift' || key === 'Alt' || key === 'Control' || key === 'Meta') {
      return '';
    }
    var out = [];
    if (isMac) {
      if (e.metaKey) out.push('Mod');
      if (e.ctrlKey) out.push('Ctrl');
    } else {
      if (e.ctrlKey) out.push('Mod');
      if (e.metaKey) out.push('Meta');
    }
    if (e.altKey) out.push('Alt');
    if (e.shiftKey) out.push('Shift');
    out.push(key);
    return normalizeShortcut(out.join('+'));
  }

  function shortcutFor(id, settings) {
    var def = _byId[id];
    if (!def) return '';
    var override = _shortcutMap(settings)[id];
    if (_hasShortcutOverride(id, settings)) {
      return normalizeShortcut(override) || normalizeShortcut(def.defaultShortcut);
    }
    return normalizeShortcut(def.defaultShortcut);
  }

  function shortcutsFor(id, settings) {
    var def = _byId[id];
    if (!def) return [];
    var primary = shortcutFor(id, settings);
    var values = primary ? [primary] : [];
    if (!_hasShortcutOverride(id, settings) && Array.isArray(def.aliases)) {
      def.aliases.forEach(function (a) {
        var norm = normalizeShortcut(a);
        if (norm && values.indexOf(norm) === -1) values.push(norm);
      });
    }
    return values;
  }

  function matches(id, e, opts) {
    opts = opts || {};
    if (!opts.allowTypingTarget && _isTypingTarget(e && e.target)) return false;
    var current = eventToShortcut(e);
    if (!current) return false;
    return shortcutsFor(id).indexOf(current) !== -1;
  }

  function displayShortcut(shortcut) {
    var norm = normalizeShortcut(shortcut);
    if (!norm) return 'Unassigned';
    if (norm.indexOf(' ') > -1) {
      return norm.split(' ').map(displayShortcut).join(' then ');
    }
    return norm.split('+').map(function (part) {
      if (part === 'Mod') return isMac ? 'Cmd' : 'Ctrl';
      if (part === 'Alt') return isMac ? 'Option' : 'Alt';
      if (part === 'Ctrl') return 'Ctrl';
      if (part === 'Shift') return 'Shift';
      if (part === 'Space') return 'Space';
      if (part === 'Plus') return '+';
      return part;
    }).join('+');
  }

  function displayFor(id) {
    return displayShortcut(shortcutFor(id));
  }

  function displayForBinding(binding, fallback) {
    var id = _byBinding[binding];
    if (!id) return fallback || '';
    return displayFor(id);
  }

  function _contextsConflict(a, b) {
    if (!a || !b) return false;
    if (a === b) return true;
    if (a === 'Global' || b === 'Global') return true;
    if (a === 'Visual workspace' && b.indexOf('visual') !== -1) return true;
    if (b === 'Visual workspace' && a.indexOf('visual') !== -1) return true;
    return false;
  }

  function validateShortcut(id, shortcut, settings) {
    var def = _byId[id];
    var norm = normalizeShortcut(shortcut);
    var result = { ok: true, errors: [], warnings: [], normalized: norm };
    if (!def) {
      result.ok = false;
      result.errors.push('Unknown shortcut id.');
      return result;
    }
    if (!norm) {
      result.ok = false;
      result.errors.push('No shortcut was captured.');
      return result;
    }
    if (norm.indexOf(' ') > -1) {
      result.ok = false;
      result.errors.push('Shortcut recording accepts one chord at a time.');
      return result;
    }
    DEFINITIONS.forEach(function (other) {
      if (other.id === id) return;
      if (!other.editable && other.defaultShortcut === 'Escape') return;
      if (shortcutsFor(other.id, settings).indexOf(norm) === -1) return;
      if (!_contextsConflict(def.context, other.context)) return;
      var message = 'Already used by "' + other.label + '" in ' + other.context + '.';
      if (other.editable) result.errors.push(message);
      else result.warnings.push(message);
    });
    RESERVED.forEach(function (row) {
      if (row.platform === 'mac' && !isMac) return;
      if (normalizeShortcut(row.shortcut) !== norm) return;
      var message = row.source + ': ' + row.label + '.';
      if (row.severity === 'block') result.errors.push(message);
      else result.warnings.push(message);
    });
    result.ok = result.errors.length === 0;
    return result;
  }

  function definitionRows(settings) {
    return DEFINITIONS.map(function (def) {
      var current = shortcutFor(def.id, settings);
      var validation = def.editable ? validateShortcut(def.id, current, settings) : null;
      return {
        id: def.id,
        category: def.category,
        label: def.label,
        description: def.description,
        context: def.context,
        editable: !!def.editable,
        defaultShortcut: normalizeShortcut(def.defaultShortcut),
        currentShortcut: current,
        currentDisplay: def.fixedDisplay || displayShortcut(current),
        defaultDisplay: def.fixedDisplay || displayShortcut(def.defaultShortcut),
        warnings: validation ? validation.warnings : [],
        errors: validation ? validation.errors : [],
        binding: def.binding || null,
      };
    });
  }

  function reservedRows() {
    return RESERVED.filter(function (row) {
      return row.platform !== 'mac' || isMac;
    }).map(function (row) {
      return {
        shortcut: normalizeShortcut(row.shortcut),
        display: displayShortcut(row.shortcut),
        label: row.label,
        source: row.source,
        severity: row.severity,
      };
    });
  }

  function audit(settings) {
    var rows = definitionRows(settings);
    var editable = rows.filter(function (r) { return r.editable; }).length;
    var errors = rows.reduce(function (n, r) { return n + r.errors.length; }, 0);
    var warnings = rows.reduce(function (n, r) { return n + r.warnings.length; }, 0);
    return {
      total: rows.length,
      editable: editable,
      fixed: rows.length - editable,
      errors: errors,
      warnings: warnings,
      rows: rows,
    };
  }

  function refresh(settings) {
    _settings = settings || {};
    _loaded = true;
  }

  function init() {
    if (typeof fetch !== 'function') return;
    fetch('/api/settings').then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.settings) refresh(data.settings);
      })
      .catch(function () { _loaded = true; });
  }

  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('ora:settings-saved', function (evt) {
      refresh((evt && evt.detail) || {});
    });
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  root.OraKeyboardShortcuts = {
    audit: audit,
    definitions: function () { return definitionRows(); },
    displayFor: displayFor,
    displayForBinding: displayForBinding,
    displayShortcut: displayShortcut,
    eventToShortcut: eventToShortcut,
    isLoaded: function () { return _loaded; },
    isTypingTarget: _isTypingTarget,
    matches: matches,
    normalizeShortcut: normalizeShortcut,
    refresh: refresh,
    reserved: reservedRows,
    shortcutFor: shortcutFor,
    shortcutsFor: shortcutsFor,
    validateShortcut: validateShortcut,
  };
})(typeof window !== 'undefined' ? window : globalThis);
