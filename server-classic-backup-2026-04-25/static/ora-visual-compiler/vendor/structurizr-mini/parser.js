/**
 * ora-visual-compiler / vendor/structurizr-mini/parser.js
 *
 * Hand-written, minimal Structurizr DSL parser (WP-1.2d).
 * Scope: Context + Container levels only. No themes, styles, configuration,
 * dynamic / deployment / filtered views.
 *
 * Public surface:
 *   window.OraVisualCompiler._vendor.structurizrMini.parser.parse(dslText)
 *       → AST object (see README-shape below).
 *
 * Errors: throws `StructurizrParseError` with .line / .col / .kind.
 *   kind ∈ { 'parse', 'unresolved_ref' }.
 *
 * AST shape:
 *   {
 *     workspace: { name: string|null, description: string|null },
 *     model: {
 *       people: [{ id, name, description, tags: [] }],
 *       softwareSystems: [{ id, name, description, tags: [], external: bool,
 *                           containers: [{ id, name, description, technology, tags: [] }] }],
 *       relationships: [{ fromId, toId, description }],
 *     },
 *     views: [{ kind, scopeId, name, include: ['*' | id, ...], layout: 'lr'|'tb'|null }],
 *   }
 *
 * Design note: this is a tokenizer + recursive-block parser. It is deliberately
 * strict-enough to catch the kinds of drift LLMs introduce (unbalanced braces,
 * missing quotes, relationships to undeclared ids) and deliberately lenient
 * about whitespace, comments, and the `model` / `views` ordering inside a
 * workspace block.
 *
 * Load order: errors.js → validator.js → renderers/stub.js → dispatcher.js →
 *             index.js → vendor/structurizr-mini/parser.js → vendor/.../renderer.js
 *             → renderers/c4.js
 *
 * Depends on: nothing (pure ES5-ish, no Ora imports).
 */

window.OraVisualCompiler = window.OraVisualCompiler || {};
window.OraVisualCompiler._vendor = window.OraVisualCompiler._vendor || {};
window.OraVisualCompiler._vendor.structurizrMini =
  window.OraVisualCompiler._vendor.structurizrMini || {};

window.OraVisualCompiler._vendor.structurizrMini.parser = (function () {

  // ── Error type ────────────────────────────────────────────────────────────
  function StructurizrParseError(message, line, col, kind) {
    this.name = 'StructurizrParseError';
    this.message = message;
    this.line = line || 0;
    this.col = col || 0;
    this.kind = kind || 'parse';
  }
  StructurizrParseError.prototype = Object.create(Error.prototype);

  // ── Tokenizer ─────────────────────────────────────────────────────────────
  // Token kinds: 'ident', 'string', 'lbrace', 'rbrace', 'assign', 'arrow',
  //              'newline' (treated as stmt separator), 'eof'.
  // Comments: `//` to end of line; `#` to end of line; `/* ... */` block.
  function tokenize(src) {
    const tokens = [];
    let i = 0;
    let line = 1;
    let col = 1;
    const n = src.length;

    function peek(off) { return src[i + (off || 0)]; }
    function advance() {
      const c = src[i++];
      if (c === '\n') { line++; col = 1; } else { col++; }
      return c;
    }
    function pushTok(kind, value, L, C) {
      tokens.push({ kind: kind, value: value, line: L, col: C });
    }

    while (i < n) {
      const c = src[i];

      // Whitespace but keep newlines as statement separators
      if (c === '\n') {
        pushTok('newline', '\n', line, col);
        advance();
        continue;
      }
      if (c === ' ' || c === '\t' || c === '\r') { advance(); continue; }

      // Line comments: // or #
      if ((c === '/' && peek(1) === '/') || c === '#') {
        while (i < n && src[i] !== '\n') i++;
        continue;
      }
      // Block comments /* ... */
      if (c === '/' && peek(1) === '*') {
        advance(); advance();
        while (i < n && !(src[i] === '*' && src[i + 1] === '/')) {
          advance();
        }
        if (i < n) { advance(); advance(); }
        continue;
      }

      // Braces
      if (c === '{') { pushTok('lbrace', '{', line, col); advance(); continue; }
      if (c === '}') { pushTok('rbrace', '}', line, col); advance(); continue; }

      // Assignment
      if (c === '=' && peek(1) !== '>') {
        pushTok('assign', '=', line, col); advance(); continue;
      }

      // Arrow ->
      if (c === '-' && peek(1) === '>') {
        pushTok('arrow', '->', line, col); advance(); advance(); continue;
      }

      // Strings "…" with backslash escapes
      if (c === '"') {
        const startL = line, startC = col;
        advance(); // skip opening quote
        let s = '';
        while (i < n && src[i] !== '"') {
          if (src[i] === '\\' && i + 1 < n) {
            const esc = src[i + 1];
            advance(); advance();
            if (esc === 'n') s += '\n';
            else if (esc === 't') s += '\t';
            else if (esc === '"') s += '"';
            else if (esc === '\\') s += '\\';
            else s += esc;
          } else {
            s += src[i]; advance();
          }
        }
        if (i >= n) {
          throw new StructurizrParseError(
            'Unterminated string literal', startL, startC, 'parse');
        }
        advance(); // closing quote
        pushTok('string', s, startL, startC);
        continue;
      }

      // Identifiers / keywords (a-zA-Z_ followed by alnum / _ / . / *)
      if (/[A-Za-z_]/.test(c)) {
        const startL = line, startC = col;
        let s = '';
        while (i < n && /[A-Za-z0-9_.]/.test(src[i])) {
          s += src[i]; advance();
        }
        pushTok('ident', s, startL, startC);
        continue;
      }

      // Bare '*' is an identifier-shaped include target
      if (c === '*') {
        pushTok('ident', '*', line, col); advance(); continue;
      }

      throw new StructurizrParseError(
        "Unexpected character '" + c + "'", line, col, 'parse');
    }

    pushTok('eof', null, line, col);
    return tokens;
  }

  // ── Token stream helpers ──────────────────────────────────────────────────
  function makeStream(tokens) {
    let idx = 0;
    function peek(off) {
      let k = idx + (off || 0);
      // Skip newlines when peeking for the next meaningful token.
      while (k < tokens.length && tokens[k].kind === 'newline' &&
             (off === undefined || off === 0)) k++;
      return tokens[k];
    }
    function raw(off) { return tokens[idx + (off || 0)]; }
    function advance() { return tokens[idx++]; }
    function skipNewlines() {
      while (idx < tokens.length && tokens[idx].kind === 'newline') idx++;
    }
    function expect(kind, value) {
      skipNewlines();
      const t = tokens[idx];
      if (!t || t.kind !== kind || (value !== undefined && t.value !== value)) {
        throw new StructurizrParseError(
          'Expected ' + kind + (value ? " '" + value + "'" : '') +
          ' but got ' + (t ? t.kind + " '" + t.value + "'" : 'eof'),
          t ? t.line : 0, t ? t.col : 0, 'parse');
      }
      return advance();
    }
    function match(kind, value) {
      skipNewlines();
      const t = tokens[idx];
      if (!t) return null;
      if (t.kind === kind && (value === undefined || t.value === value)) {
        return advance();
      }
      return null;
    }
    return {
      peek: peek, raw: raw, advance: advance,
      skipNewlines: skipNewlines,
      expect: expect, match: match,
      pos: function () { return idx; },
    };
  }

  // ── Parser ────────────────────────────────────────────────────────────────
  function parse(src) {
    const tokens = tokenize(src);
    const st = makeStream(tokens);

    // Top-level: `workspace` block (the DSL entry point).
    // Strictly speaking Structurizr allows bare `workspace { … }` or with
    // name + description strings. We accept both.
    st.skipNewlines();
    const wsHead = st.expect('ident');
    if (wsHead.value !== 'workspace') {
      throw new StructurizrParseError(
        "Expected 'workspace' keyword at top of DSL, got '" + wsHead.value + "'",
        wsHead.line, wsHead.col, 'parse');
    }

    let wsName = null;
    let wsDesc = null;
    // Optional "name" or "name" "desc"
    st.skipNewlines();
    if (st.raw() && st.raw().kind === 'string') { wsName = st.advance().value; }
    st.skipNewlines();
    if (st.raw() && st.raw().kind === 'string') { wsDesc = st.advance().value; }

    st.expect('lbrace');

    const ast = {
      workspace: { name: wsName, description: wsDesc },
      model: { people: [], softwareSystems: [], relationships: [] },
      views: [],
    };

    // A known-id index for forward-reference checking.
    const declaredIds = new Set();
    // Deferred relationships captured before target exists — they get
    // resolved at end of `model` block, not end of file, to catch
    // "relationship declared after containing block ends" style bugs.
    const deferredRels = [];

    while (true) {
      st.skipNewlines();
      const t = st.raw();
      if (!t) {
        throw new StructurizrParseError(
          "Unexpected end of input inside 'workspace'", 0, 0, 'parse');
      }
      if (t.kind === 'rbrace') { st.advance(); break; }
      if (t.kind === 'eof') {
        throw new StructurizrParseError(
          "Unterminated 'workspace' block", t.line, t.col, 'parse');
      }
      if (t.kind !== 'ident') {
        throw new StructurizrParseError(
          "Expected keyword inside workspace, got " + t.kind,
          t.line, t.col, 'parse');
      }
      if (t.value === 'model') {
        st.advance();
        st.expect('lbrace');
        parseModelBody(st, ast, declaredIds, deferredRels);
      } else if (t.value === 'views') {
        st.advance();
        st.expect('lbrace');
        parseViewsBody(st, ast, declaredIds);
      } else if (t.value === 'configuration') {
        // Out of scope — skip the block.
        st.advance();
        skipBlock(st);
      } else {
        throw new StructurizrParseError(
          "Unknown top-level workspace keyword '" + t.value + "'",
          t.line, t.col, 'parse');
      }
    }

    // Resolve deferred relationships. At this point every id declared
    // anywhere in `model` is known.
    for (let j = 0; j < deferredRels.length; j++) {
      const r = deferredRels[j];
      if (!declaredIds.has(r.fromId)) {
        throw new StructurizrParseError(
          "Relationship references undeclared id '" + r.fromId + "'",
          r.line, r.col, 'unresolved_ref');
      }
      if (!declaredIds.has(r.toId)) {
        throw new StructurizrParseError(
          "Relationship references undeclared id '" + r.toId + "'",
          r.line, r.col, 'unresolved_ref');
      }
    }

    return ast;
  }

  // Skip a {…}-balanced block already past the opening `{`-less point.
  // Used when we encounter `configuration`.
  function skipBlock(st) {
    st.expect('lbrace');
    let depth = 1;
    while (depth > 0) {
      const t = st.raw();
      if (!t || t.kind === 'eof') {
        throw new StructurizrParseError(
          'Unterminated block', t ? t.line : 0, t ? t.col : 0, 'parse');
      }
      if (t.kind === 'lbrace') depth++;
      if (t.kind === 'rbrace') depth--;
      st.advance();
    }
  }

  // ── model { … } body ──────────────────────────────────────────────────────
  function parseModelBody(st, ast, declaredIds, deferredRels) {
    while (true) {
      st.skipNewlines();
      const t = st.raw();
      if (!t) {
        throw new StructurizrParseError(
          "Unterminated 'model' block", 0, 0, 'parse');
      }
      if (t.kind === 'rbrace') { st.advance(); return; }

      // Possible forms inside model:
      //   <id> = person "Name" "Desc?"
      //   <id> = softwareSystem "Name" "Desc?" [ { … container declarations + `tags` } ]
      //   <id> -> <id> "Desc?"
      //   person "Name" "Desc?"                 (anonymous, rare — we allow + skip)
      //   softwareSystem "Name" "Desc?" [ { … } ]
      if (t.kind !== 'ident') {
        throw new StructurizrParseError(
          "Expected identifier in model, got " + t.kind,
          t.line, t.col, 'parse');
      }

      // Lookahead for `ident =` (declaration) or `ident ->` (relationship).
      // Peek past newlines for the second significant token.
      const saved = st.pos();
      const first = st.advance();
      st.skipNewlines();
      const second = st.raw();

      if (second && second.kind === 'assign') {
        // Declaration: <id> = <type> ...
        st.advance(); // consume =
        parseDeclaration(st, ast, first, declaredIds, deferredRels);
      } else if (second && second.kind === 'arrow') {
        // Relationship with no explicit description token consumed yet.
        st.advance(); // consume ->
        parseRelationship(st, ast, first, declaredIds, deferredRels);
      } else if (first.value === 'person' || first.value === 'softwareSystem') {
        // Anonymous declaration — allowed but we just need to consume
        // the structure safely so parsing continues.
        consumeAnonymousDeclaration(st, first);
      } else {
        throw new StructurizrParseError(
          "Expected '=' or '->' after identifier '" + first.value + "'",
          first.line, first.col, 'parse');
      }
    }
  }

  function consumeAnonymousDeclaration(st, firstIdent) {
    // Consume name + optional description strings, optional { … } body.
    if (st.raw() && st.raw().kind === 'string') st.advance();
    if (st.raw() && st.raw().kind === 'string') st.advance();
    if (st.raw() && st.raw().kind === 'string') st.advance();
    st.skipNewlines();
    if (st.raw() && st.raw().kind === 'lbrace') {
      skipBlock(st);
    }
  }

  function parseDeclaration(st, ast, idTok, declaredIds, deferredRels) {
    const kindTok = st.expect('ident');
    const kind = kindTok.value;

    if (kind === 'person') {
      const name = st.raw() && st.raw().kind === 'string' ? st.advance().value : '';
      const desc = st.raw() && st.raw().kind === 'string' ? st.advance().value : '';
      declaredIds.add(idTok.value);
      ast.model.people.push({
        id: idTok.value, name: name, description: desc, tags: [],
      });
      // Optional { tags "x" } block
      st.skipNewlines();
      if (st.raw() && st.raw().kind === 'lbrace') {
        const tags = parsePersonOrSystemBody(st);
        ast.model.people[ast.model.people.length - 1].tags = tags.tags;
      }
      return;
    }

    if (kind === 'softwareSystem') {
      const name = st.raw() && st.raw().kind === 'string' ? st.advance().value : '';
      const desc = st.raw() && st.raw().kind === 'string' ? st.advance().value : '';
      declaredIds.add(idTok.value);
      const sys = {
        id: idTok.value, name: name, description: desc,
        tags: [], external: false, containers: [],
      };
      ast.model.softwareSystems.push(sys);
      st.skipNewlines();
      if (st.raw() && st.raw().kind === 'lbrace') {
        parseSoftwareSystemBody(st, sys, declaredIds);
        // Harvest deferred relationships declared inline inside the system.
        if (sys._deferredRels && deferredRels) {
          sys._deferredRels.forEach(function (r) {
            ast.model.relationships.push({
              fromId: r.fromId, toId: r.toId, description: r.description,
            });
            deferredRels.push({
              fromId: r.fromId, toId: r.toId,
              line: r.line, col: r.col,
            });
          });
          delete sys._deferredRels;
        }
      }
      sys.external = sys.tags.indexOf('External') !== -1;
      return;
    }

    throw new StructurizrParseError(
      "Unsupported declaration kind '" + kind + "' in model. " +
      'Supported: person, softwareSystem.',
      kindTok.line, kindTok.col, 'parse');
  }

  function parsePersonOrSystemBody(st) {
    st.expect('lbrace');
    const tags = [];
    while (true) {
      st.skipNewlines();
      const t = st.raw();
      if (!t) {
        throw new StructurizrParseError(
          'Unterminated block', 0, 0, 'parse');
      }
      if (t.kind === 'rbrace') { st.advance(); break; }
      if (t.kind === 'ident' && t.value === 'tags') {
        st.advance();
        while (st.raw() && st.raw().kind === 'string') {
          tags.push(st.advance().value);
        }
        continue;
      }
      // Skip any other recognized but unused idents in this scope.
      if (t.kind === 'ident') { st.advance(); continue; }
      if (t.kind === 'string') { st.advance(); continue; }
      throw new StructurizrParseError(
        'Unexpected token in block', t.line, t.col, 'parse');
    }
    return { tags: tags };
  }

  function parseSoftwareSystemBody(st, sys, declaredIds) {
    st.expect('lbrace');
    // Inline relationships (container1 -> container2) must defer
    // reference-checking to the end of the model block, because container ids
    // declared later in THIS block are also legal sources/targets.
    // We push them onto the ast-level deferred list — but since this function
    // doesn't have that list we expose a local array and re-emit on exit.
    const localDeferred = [];
    while (true) {
      st.skipNewlines();
      const t = st.raw();
      if (!t) {
        throw new StructurizrParseError(
          "Unterminated softwareSystem block", 0, 0, 'parse');
      }
      if (t.kind === 'rbrace') {
        st.advance();
        // Caller merges localDeferred via the outer deferredRels list. We
        // stash them on the sys object briefly; caller picks them up.
        sys._deferredRels = localDeferred;
        return;
      }

      if (t.kind !== 'ident') {
        throw new StructurizrParseError(
          'Expected identifier inside softwareSystem',
          t.line, t.col, 'parse');
      }
      if (t.value === 'tags') {
        st.advance();
        while (st.raw() && st.raw().kind === 'string') {
          sys.tags.push(st.advance().value);
        }
        continue;
      }

      // Container declaration: <id> = container "Name" "Desc?" "Tech?"
      // or bare `container "Name" ...`
      // Inline relationship: <id> -> <id> "Desc?"
      const first = st.advance();
      st.skipNewlines();
      const second = st.raw();
      if (second && second.kind === 'assign') {
        st.advance();
        const cKind = st.expect('ident');
        if (cKind.value !== 'container') {
          throw new StructurizrParseError(
            "Inside softwareSystem only 'container' declarations are supported, got '" +
            cKind.value + "'", cKind.line, cKind.col, 'parse');
        }
        const name = st.raw() && st.raw().kind === 'string' ? st.advance().value : '';
        const desc = st.raw() && st.raw().kind === 'string' ? st.advance().value : '';
        const tech = st.raw() && st.raw().kind === 'string' ? st.advance().value : '';
        declaredIds.add(first.value);
        const container = {
          id: first.value, name: name, description: desc,
          technology: tech, tags: [],
        };
        sys.containers.push(container);
        st.skipNewlines();
        if (st.raw() && st.raw().kind === 'lbrace') {
          const sub = parsePersonOrSystemBody(st);
          container.tags = sub.tags;
        }
        continue;
      }

      if (second && second.kind === 'arrow') {
        st.advance();
        const toTok = st.expect('ident');
        let desc = '';
        if (st.raw() && st.raw().kind === 'string') desc = st.advance().value;
        while (st.raw() && st.raw().kind === 'string') st.advance();
        localDeferred.push({
          fromId: first.value, toId: toTok.value, description: desc,
          line: first.line, col: first.col,
        });
        continue;
      }

      if (first.value === 'container') {
        // Anonymous container — consume, don't emit.
        if (st.raw() && st.raw().kind === 'string') st.advance();
        if (st.raw() && st.raw().kind === 'string') st.advance();
        if (st.raw() && st.raw().kind === 'string') st.advance();
        st.skipNewlines();
        if (st.raw() && st.raw().kind === 'lbrace') skipBlock(st);
        continue;
      }

      throw new StructurizrParseError(
        "Unexpected token inside softwareSystem: '" + first.value + "'",
        first.line, first.col, 'parse');
    }
  }

  function parseRelationship(st, ast, fromTok, declaredIds, deferredRels) {
    const toTok = st.expect('ident');
    let desc = '';
    if (st.raw() && st.raw().kind === 'string') desc = st.advance().value;
    // Technology + tags tokens (optional) — consume and discard.
    while (st.raw() && st.raw().kind === 'string') st.advance();
    const rel = {
      fromId: fromTok.value,
      toId: toTok.value,
      description: desc,
    };
    ast.model.relationships.push(rel);
    deferredRels.push({
      fromId: fromTok.value, toId: toTok.value,
      line: fromTok.line, col: fromTok.col,
    });
  }

  // ── views { … } body ─────────────────────────────────────────────────────
  function parseViewsBody(st, ast, declaredIds) {
    while (true) {
      st.skipNewlines();
      const t = st.raw();
      if (!t) {
        throw new StructurizrParseError(
          "Unterminated 'views' block", 0, 0, 'parse');
      }
      if (t.kind === 'rbrace') { st.advance(); return; }

      if (t.kind !== 'ident') {
        throw new StructurizrParseError(
          'Expected view keyword', t.line, t.col, 'parse');
      }

      const kw = t.value;
      if (kw !== 'systemContext' && kw !== 'container') {
        // Skip unsupported view kinds (e.g. dynamic, deployment, filtered).
        st.advance();
        // Consume idents/strings until we hit `{` then skip the block.
        while (st.raw() && st.raw().kind !== 'lbrace' &&
               st.raw().kind !== 'rbrace' && st.raw().kind !== 'eof') {
          st.advance();
        }
        if (st.raw() && st.raw().kind === 'lbrace') skipBlock(st);
        continue;
      }

      st.advance(); // consume systemContext / container
      const scopeTok = st.expect('ident');
      if (!declaredIds.has(scopeTok.value)) {
        throw new StructurizrParseError(
          "View references undeclared id '" + scopeTok.value + "'",
          scopeTok.line, scopeTok.col, 'unresolved_ref');
      }
      let viewName = '';
      if (st.raw() && st.raw().kind === 'string') viewName = st.advance().value;
      // Optional description string
      if (st.raw() && st.raw().kind === 'string') st.advance();

      const view = {
        kind: kw, scopeId: scopeTok.value, name: viewName,
        include: [], layout: null,
      };
      ast.views.push(view);

      st.expect('lbrace');
      while (true) {
        st.skipNewlines();
        const v = st.raw();
        if (!v) {
          throw new StructurizrParseError(
            'Unterminated view block', 0, 0, 'parse');
        }
        if (v.kind === 'rbrace') { st.advance(); break; }
        if (v.kind !== 'ident') {
          throw new StructurizrParseError(
            'Expected keyword inside view', v.line, v.col, 'parse');
        }
        if (v.value === 'include') {
          st.advance();
          while (st.raw() && (st.raw().kind === 'ident')) {
            view.include.push(st.advance().value);
          }
        } else if (v.value === 'autolayout') {
          st.advance();
          if (st.raw() && st.raw().kind === 'ident') {
            const hint = st.advance().value.toLowerCase();
            if (hint === 'lr' || hint === 'rl' || hint === 'tb' || hint === 'bt') {
              view.layout = (hint === 'lr' || hint === 'rl') ? 'lr' : 'tb';
            } else {
              view.layout = null;
            }
          } else {
            view.layout = 'tb';
          }
        } else {
          // Unknown view directive — skip to next newline.
          st.advance();
          while (st.raw() && st.raw().kind !== 'newline' &&
                 st.raw().kind !== 'rbrace' && st.raw().kind !== 'eof') {
            st.advance();
          }
        }
      }
    }
  }

  // ── Public API ────────────────────────────────────────────────────────────
  return {
    parse: parse,
    StructurizrParseError: StructurizrParseError,
  };

}());
