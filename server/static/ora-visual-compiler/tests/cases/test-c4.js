/**
 * ora-visual-compiler / tests/cases/test-c4.js
 *
 * Test case index for the C4 renderer (WP-1.2d), ready for consumption by
 * the forthcoming WP-1.2a harness (see Working Plan §WP-1.2 nits:
 * "Add a tests/visual-compiler/ harness (node-based, jsdom, or headless
 * browser) as part of WP-1.2a so the new renderers have a regression surface
 * from the start").
 *
 * Until that harness lands, the standalone runner at
 *   ~/ora/server/static/ora-visual-compiler/tests/standalone-c4.js
 * covers the same surface via a minimal `window` shim.
 *
 * Exports CASES so a harness can iterate without re-parsing this file.
 */

'use strict';

const CASES = [
  // ── Valid context (3) ─────────────────────────────────────────────────────
  {
    name: 'context-minimal',
    level: 'context',
    expect: 'ok',
    dsl: [
      'workspace {',
      '  model {',
      '    u = person "User" "A human user"',
      '    ss = softwareSystem "System" "The core system"',
      '    u -> ss "Uses"',
      '  }',
      '  views {',
      '    systemContext ss "Context" {',
      '      include *',
      '      autolayout lr',
      '    }',
      '  }',
      '}',
    ].join('\n'),
  },
  {
    name: 'context-external-system',
    level: 'context',
    expect: 'ok',
    dsl: [
      'workspace "Big Bank" "Example workspace" {',
      '  model {',
      '    u = person "Customer" "A bank customer"',
      '    ss = softwareSystem "Internet Banking System" "Core banking"',
      '    ex = softwareSystem "Mainframe" "Legacy mainframe" { tags "External" }',
      '    u -> ss "Uses"',
      '    ss -> ex "Reads from"',
      '  }',
      '  views {',
      '    systemContext ss "SystemContext" { include * autolayout lr }',
      '  }',
      '}',
    ].join('\n'),
  },
  {
    name: 'context-multiple-people',
    level: 'context',
    expect: 'ok',
    dsl: [
      'workspace {',
      '  model {',
      '    admin = person "Admin" "System admin"',
      '    customer = person "Customer" "End user"',
      '    ss = softwareSystem "Portal" "Main portal"',
      '    notify = softwareSystem "Notifier" "Notification service" { tags "External" }',
      '    admin -> ss "Manages"',
      '    customer -> ss "Uses"',
      '    ss -> notify "Sends alerts via"',
      '  }',
      '  views {',
      '    systemContext ss "Ctx" { include * autolayout tb }',
      '  }',
      '}',
    ].join('\n'),
  },

  // ── Valid container (3) ───────────────────────────────────────────────────
  {
    name: 'container-nested',
    level: 'container',
    expect: 'ok',
    dsl: [
      'workspace {',
      '  model {',
      '    u = person "User" "A user"',
      '    ss = softwareSystem "App" "Web app" {',
      '      web = container "Web App" "Browser UI" "React"',
      '      api = container "API" "HTTP API" "Node.js"',
      '      db = container "DB" "Relational store" "Postgres"',
      '      web -> api "Calls"',
      '      api -> db "Queries"',
      '    }',
      '    u -> web "Browses"',
      '  }',
      '  views {',
      '    container ss "Containers" { include * autolayout lr }',
      '  }',
      '}',
    ].join('\n'),
  },
  {
    name: 'container-with-person',
    level: 'container',
    expect: 'ok',
    dsl: [
      'workspace {',
      '  model {',
      '    u = person "Customer" "Customer"',
      '    ss = softwareSystem "Shop" "E-commerce" {',
      '      ui = container "Storefront" "Public site" "Next.js"',
      '      api = container "API" "REST API" "Go"',
      '      ui -> api "Calls"',
      '    }',
      '    u -> ui "Shops on"',
      '  }',
      '  views {',
      '    container ss "Containers" { include * autolayout tb }',
      '  }',
      '}',
    ].join('\n'),
  },
  {
    name: 'container-with-external-system',
    level: 'container',
    expect: 'ok',
    dsl: [
      'workspace {',
      '  model {',
      '    ss = softwareSystem "Core" "Core" {',
      '      api = container "API" "HTTP" "Python"',
      '      worker = container "Worker" "Async" "Go"',
      '      api -> worker "Enqueues"',
      '    }',
      '    ext = softwareSystem "PaymentProvider" "Stripe-like" { tags "External" }',
      '    api -> ext "Charges via"',
      '  }',
      '  views {',
      '    container ss "Containers" { include * autolayout lr }',
      '  }',
      '}',
    ].join('\n'),
  },

  // ── Invalid (3) ───────────────────────────────────────────────────────────
  {
    name: 'invalid-forward-ref',
    level: 'context',
    expect: 'error',
    expectCode: 'E_UNRESOLVED_REF',
    dsl: [
      'workspace {',
      '  model {',
      '    u = person "User" "U"',
      '    u -> ghost "Uses"',
      '  }',
      '}',
    ].join('\n'),
  },
  {
    name: 'invalid-malformed-missing-brace',
    level: 'context',
    expect: 'error',
    expectCode: 'E_DSL_PARSE',
    dsl: [
      'workspace {',
      '  model {',
      '    u = person "User" "U"',
    ].join('\n'),
  },
  {
    name: 'invalid-level-mismatch',
    level: 'context',
    expect: 'error',
    expectCode: 'E_SCHEMA_INVALID',
    dsl: [
      'workspace {',
      '  model {',
      '    u = person "User" "U"',
      '    ss = softwareSystem "S" "Sys" {',
      '      c = container "C" "Thing" "Tech"',
      '    }',
      '    u -> c "Uses"',
      '  }',
      '  views {',
      '    container ss "Containers" { include * autolayout lr }',
      '  }',
      '}',
    ].join('\n'),
  },
];

if (typeof module !== 'undefined') module.exports = { CASES: CASES };
