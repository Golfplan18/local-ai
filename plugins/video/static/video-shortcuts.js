/* Keyboard shortcut definitions owned by the optional video feature. */
(function (root) {
  'use strict';

  if (!root.OraKeyboardShortcuts
      || typeof root.OraKeyboardShortcuts.register !== 'function') {
    if (root.console && typeof root.console.warn === 'function') {
      root.console.warn('[video-plugin] keyboard shortcut registry is unavailable');
    }
    return;
  }

  root.OraKeyboardShortcuts.register([
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
  ]);
})(typeof window !== 'undefined' ? window : globalThis);
