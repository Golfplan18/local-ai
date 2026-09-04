'use strict';

// The repository owns these narrow seams, not a vendored Playwright bundle.
// Reinstallation starts from the lock; unexpected upstream bytes stop patching.
const fs = require('node:fs');
const path = require('node:path');
const core = path.join(__dirname, 'node_modules/playwright-core');
const marker = 'const oraBrowserBinding = require("../../../browser-target-binding.cjs");';
const seams = [
  ['"use strict";\n', `"use strict";\n${marker}\n`],
  ['      async send(method, params2) {\n        if (this._crashed || this._closed || this._connection._closed',
   '      async send(method, params2) {\n        await oraBrowserBinding.beforeSend(this, method, params2);\n        if (this._crashed || this._closed || this._connection._closed'],
  ['        const id = this._connection._rawSend(this._sessionId, method, params2);',
   '        oraBrowserBinding.checkSend(method);\n        const id = this._connection._rawSend(this._sessionId, method, params2);'],
  ['        const id = this._connection._rawSend(this._sessionId, method, params2);\n        return new Promise((resolve, reject) => {',
   '        const id = this._connection._rawSend(this._sessionId, method, params2);\n        oraBrowserBinding.sent(method, params2);\n        return new Promise((resolve, reject) => {'],
  ['      async down(progress2, key) {\n        const description',
   '      async down(progress2, key) {\n        oraBrowserBinding.inputState("keyboard", this);\n        const description'],
  ['      async up(progress2, key) {\n        const description',
   '      async up(progress2, key) {\n        oraBrowserBinding.inputState("keyboard", this);\n        const description'],
  ['      async move(progress2, x, y, options = {}) {\n        const { steps = 1 }',
   '      async move(progress2, x, y, options = {}) {\n        oraBrowserBinding.inputState("mouse", this);\n        const { steps = 1 }'],
  ['      async down(progress2, options = {}) {\n        const { button = "left", clickCount = 1 }',
   '      async down(progress2, options = {}) {\n        oraBrowserBinding.inputState("mouse", this);\n        const { button = "left", clickCount = 1 }'],
  ['      async up(progress2, options = {}) {\n        const { button = "left", clickCount = 1 }',
   '      async up(progress2, options = {}) {\n        oraBrowserBinding.inputState("mouse", this);\n        const { button = "left", clickCount = 1 }'],
  ['      async _retryWithProgressIfNotConnected(progress2, selector, options, action) {\n',
   '      async _retryWithProgressIfNotConnected(progress2, selector, options, action) {\n        if (oraBrowserBinding.active())\n          return oraBrowserBinding.withTarget(this, progress2, selector, options, action);\n'],
  ['      async _selectOption(progress2, elements, values, options) {\n',
   '      async _selectOption(progress2, elements, values, options) {\n        const pinned = oraBrowserBinding.optionsFor(this, values);\n        if (pinned) { elements = pinned; values = []; }\n'],
  ['      async _focus(progress2, resetSelectionIfNotFocused) {\n',
   '      async _focus(progress2, resetSelectionIfNotFocused) {\n        const receiver = oraBrowserBinding.focusTarget(this);\n        if (receiver) return receiver._focus(progress2, resetSelectionIfNotFocused);\n'],
  ['        const point = roundPoint(maybeResult.point);\n',
   '        const point = roundPoint(maybeResult.point);\n        oraBrowserBinding.pointerPoint(this, point);\n'],
  // A bound click must check each native send after the preceding event. The
  // unbound zero-delay path retains Playwright's concurrent protocol sends.
  ['        if (delay) {\n          await this.move(progress2, x, y, { forClick: true, steps });',
   '        if (delay || oraBrowserBinding.active()) {\n          await this.move(progress2, x, y, { forClick: true, steps });'],
  ['            await progress2.wait(delay);\n            await this.up(progress2, { ...options, clickCount: cc });\n            if (cc < clickCount)',
   '            if (delay) await progress2.wait(delay);\n            await this.up(progress2, { ...options, clickCount: cc });\n            if (cc < clickCount && delay)'],
  ['      async ensureTab() {\n        await this.ensureBrowserContext();',
   '      async ensureTab() {\n        const bound = oraBrowserBinding.boundTab(this);\n        if (bound) return bound;\n        await this.ensureBrowserContext();'],
  ['    result2 = await callback();\n    await tab2.waitForTimeout(settleMs);',
   '    result2 = await oraBrowserBinding.nativeCompletion(callback);\n    await tab2.waitForTimeout(settleMs);'],
  ['        const cwd = rawArguments._meta?.cwd;\n',
   '        if (oraBrowserBinding.supports(name) && rawArguments._meta?.ora?.phase !== "execute") {\n          try {\n            return await oraBrowserBinding.control(this, name, parsedArguments, rawArguments._meta?.ora);\n          } catch (error) { return formatError(error.stack || String(error)); }\n        }\n        const cwd = rawArguments._meta?.cwd;\n'],
  ['          await tool.handle(context2, parsedArguments, response2, signal);\n',
   '          await oraBrowserBinding.run(this, name, parsedArguments, rawArguments._meta?.ora,\n            () => tool.handle(context2, parsedArguments, response2, signal));\n'],
  ['        await this._context?.dispose().catch((e) => debug10("pw:tools:error")(e));',
   '        await oraBrowserBinding.dispose(this);\n        await this._context?.dispose().catch((e) => debug10("pw:tools:error")(e));'],
];

function patch() {
  if (JSON.parse(fs.readFileSync(path.join(core, 'package.json'))).version !== '1.63.0-alpha-2026-08-05')
    throw new Error('Ora browser binding requires the locked Playwright version');
  const filename = path.join(core, 'lib/coreBundle.js');
  let source = fs.readFileSync(filename, 'utf8');
  const before = source;
  for (const [original, replacement] of seams) {
    if (source.includes(replacement)) continue;
    // The prologue is deliberately anchored; the other seams must be unique.
    const at = source.indexOf(original);
    if (at < 0 || (original !== '"use strict";\n' && source.indexOf(original, at + original.length) !== -1))
      throw new Error('Locked Playwright browser-binding seam changed');
    source = source.slice(0, at) + replacement + source.slice(at + original.length);
  }
  if (source !== before) fs.writeFileSync(filename, source);
}

if (require.main === module) patch();
module.exports = { patch, marker };
