import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import { EditorState, Compartment } from '@codemirror/state';
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightSpecialChars, drawSelection } from '@codemirror/view';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { foldGutter, foldKeymap, syntaxHighlighting, defaultHighlightStyle, bracketMatching } from '@codemirror/language';
import { markdownLanguage, markdownKeymap } from '@codemirror/lang-markdown';

const READ_LIMIT = 4 * 1024 * 1024;
const parser = new MarkdownIt({ html: false, linkify: false, typographer: false, highlight: null });
const escape = parser.utils.escapeHtml;
const activeUrl = value => /^(https?:|mailto:)/i.test(value) && !/[\u0000-\u0020\u007f]/.test(value);
// Unsupported destinations still deserve a meaningful, inert label.
parser.validateLink = () => true;
parser.renderer.rules.link_open = (tokens, index) => {
  const href = tokens[index].attrGet('href') || '';
  return activeUrl(href)
    ? `<a href="${escape(href)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">`
    : '<span>';
};
parser.renderer.rules.link_close = (tokens, index) => {
  let depth = 0;
  for (let prior = index - 1; prior >= 0; prior--) {
    if (tokens[prior].type === 'link_close') depth++;
    if (tokens[prior].type === 'link_open' && depth-- === 0) {
      const href = tokens[prior].attrGet('href') || '';
      return activeUrl(href) ? '</a>' : ` (link: ${escape(href)}; unavailable in Ora)</span>`;
    }
  }
  return '</span>';
};
parser.renderer.rules.image = (tokens, index) => {
  const token = tokens[index];
  return `<span>[Image: ${escape(token.content || 'untitled')} — ${escape(token.attrGet('src') || '')}; not loaded]</span>`;
};
parser.renderer.rules.text = (tokens, index) => escape(tokens[index].content).replace(
  /(!?)\[\[([^\]\r\n]+)\]\]/g,
  (_, embed, target) => `<span>[${embed ? 'Embed' : 'Wiki link'}: ${target}; unavailable in Ora]</span>`,
);
const sanitizeOptions = {
  ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'em', 'strong', 's', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'br', 'a', 'span'],
  ALLOWED_ATTR: ['href', 'target', 'rel', 'referrerpolicy', 'start'],
  ALLOW_DATA_ATTR: false,
  ALLOW_ARIA_ATTR: false,
};

let liveEditor = null;

function literal(host, text, message) {
  const diagnostic = document.createElement('p');
  diagnostic.className = 'ora-document-diagnostic';
  diagnostic.setAttribute('role', 'status');
  diagnostic.textContent = message;
  const source = document.createElement('pre');
  source.className = 'ora-document-literal';
  source.textContent = text;
  host.replaceChildren(diagnostic, source);
}

function renderRead({ host, markdown: source, ariaLabel }) {
  if (!host || typeof source !== 'string') throw new Error('A document host and Markdown text are required.');
  if (liveEditor && (host.contains(liveEditor.host) || liveEditor.host.contains(host))) {
    throw new Error('Close the current editor before replacing its document.');
  }
  const content = document.createElement('article');
  content.className = 'ora-document-read';
  content.setAttribute('aria-label', ariaLabel || 'Read document');
  try {
    if (new TextEncoder().encode(source).byteLength > READ_LIMIT) {
      literal(content, source, 'This document exceeds the 4 MiB rendered Read limit. Showing the complete literal text.');
    } else {
      const clean = DOMPurify.sanitize(parser.render(source), sanitizeOptions);
      if (typeof clean !== 'string' || (source.trim() && !clean.trim())) throw new Error('Invalid rendered document.');
      content.innerHTML = clean;
    }
  } catch (error) {
    content.classList.add('ora-document-read--unavailable');
    literal(content, source, 'Rendered Read is unavailable. Showing the complete literal text.');
    console.error('Ora document rendering failed:', error);
  }
  host.replaceChildren(content);
  let destroyed = false;
  return { mode: 'read', destroy() { if (!destroyed) { destroyed = true; content.remove(); } } };
}

function createEditor({ host, text, ariaLabel, onChange }) {
  if (liveEditor) throw new Error('An editor is already open. Close it before opening another document.');
  if (!host || typeof text !== 'string') throw new Error('A document host and complete text are required.');
  const shell = document.createElement('div');
  shell.className = 'ora-document-editor';
  // CodeMirror mounts its own style modules in this root. Removing the shell
  // removes those styles as well; no style cache is left in the Ora document.
  const root = shell.attachShadow({ mode: 'open' });
  const disabled = new Compartment();
  let view;
  try {
    view = new EditorView({
      parent: root,
      root,
      state: EditorState.create({
        doc: text,
        extensions: [
          history(), lineNumbers(), foldGutter(), drawSelection(),
          highlightActiveLine(), highlightSpecialChars(), bracketMatching(),
          syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
          markdownLanguage, EditorView.lineWrapping,
          keymap.of([...markdownKeymap, ...defaultKeymap, ...historyKeymap, ...foldKeymap]),
          EditorView.contentAttributes.of({ 'aria-label': ariaLabel || 'Edit Markdown' }),
          disabled.of([EditorState.readOnly.of(false), EditorView.editable.of(true)]),
          EditorView.updateListener.of(update => {
            if (update.docChanged && typeof onChange === 'function') onChange(update.state.doc.toString());
          }),
        ],
      }),
    });
    host.replaceChildren(shell);
  } catch (error) {
    if (view) view.destroy();
    shell.remove();
    throw error;
  }
  const owner = { host };
  liveEditor = owner;
  let destroyed = false;
  return {
    getText: () => view.state.doc.toString(),
    setDisabled(value) {
      if (destroyed) return;
      view.dispatch({ effects: disabled.reconfigure([
        EditorState.readOnly.of(Boolean(value)), EditorView.editable.of(!value),
        EditorView.contentAttributes.of({ 'aria-disabled': String(Boolean(value)) }),
      ]) });
    },
    focus() { if (!destroyed) view.focus(); },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      view.destroy();
      root.replaceChildren();
      if (root.adoptedStyleSheets) root.adoptedStyleSheets = [];
      shell.remove();
      if (liveEditor === owner) liveEditor = null;
    },
  };
}

window.OraDocumentSurface = Object.freeze({ renderRead, createEditor });
