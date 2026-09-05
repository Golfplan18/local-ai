import { build } from 'esbuild';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, '../static/vendor/document-surface');
const result = await build({
  absWorkingDir: here,
  entryPoints: ['src/index.js'],
  outfile: join(out, 'ora-document-surface.js'),
  bundle: true,
  minify: true,
  sourcemap: false,
  format: 'iife',
  platform: 'browser',
  target: ['chrome110', 'safari16.4', 'firefox115'],
  legalComments: 'inline',
  metafile: true,
  write: false,
});

// Attribute only code actually included in the runtime output, not the DOM
// harness or bundler. Resolve each input to its nearest real npm package.
const packages = new Map();
const inputs = Object.values(result.metafile.outputs).flatMap(output =>
  Object.entries(output.inputs).filter(([, value]) => value.bytesInOutput > 0).map(([input]) => input));
for (const input of inputs) {
  if (!input.includes('node_modules/')) continue;
  let directory = dirname(resolve(here, input));
  let metadata;
  while (directory.startsWith(join(here, 'node_modules'))) {
    try { metadata = JSON.parse(await readFile(join(directory, 'package.json'), 'utf8')); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (metadata && metadata.name && metadata.version) break;
    directory = dirname(directory);
  }
  if (!metadata || !metadata.name || !metadata.version) throw new Error(`No package identity for ${input}`);
  packages.set(directory, metadata);
}
let notices = 'Ora document surface — bundled runtime third-party notices\n\n';
for (const [directory, metadata] of [...packages].sort((a, b) => a[1].name.localeCompare(b[1].name, 'en'))) {
  const names = (await readdir(directory)).filter(name => /^(licen[sc]e|copying|notice)([.-]|$)/i.test(name)).sort();
  if (!names.some(name => /^(licen[sc]e|copying)([.-]|$)/i.test(name))) {
    throw new Error(`Missing runtime license material for ${metadata.name}`);
  }
  notices += `${metadata.name} ${metadata.version} — ${metadata.license || 'see license below'}\n`;
  for (const name of names) {
    const license = (await readFile(join(directory, name), 'utf8')).trim();
    if (!license) throw new Error(`Empty runtime license material for ${metadata.name}: ${name}`);
    notices += `${name}\n${license}\n\n`;
  }
}
await mkdir(out, { recursive: true });
for (const file of result.outputFiles) await writeFile(file.path, file.contents);
await writeFile(join(out, 'THIRD_PARTY_NOTICES.txt'), notices, 'utf8');
console.log(`Built local document surface; runtime notices cover ${packages.size} included packages.`);
