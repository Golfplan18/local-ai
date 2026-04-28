const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const COMPILER_DIR = '/Users/oracle/ora/server/static/ora-visual-compiler';

async function main() {
  const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { runScripts: 'outside-only' });
  const win = dom.window;
  win.structuredClone = globalThis.structuredClone || ((v) => JSON.parse(JSON.stringify(v)));
  win.HTMLCanvasElement.prototype.getContext = function() {
    return { measureText: (t) => ({ width: (t||'').length * 6 }), fillText:()=>{}, save:()=>{}, restore:()=>{}, scale:()=>{}, translate:()=>{}, rotate:()=>{}, beginPath:()=>{}, closePath:()=>{}, fillRect:()=>{}, strokeRect:()=>{}, clearRect:()=>{}, moveTo:()=>{}, lineTo:()=>{}, stroke:()=>{}, fill:()=>{}, arc:()=>{}, rect:()=>{}, getImageData:()=>({data:new Uint8ClampedArray(4)}), putImageData:()=>{}, createImageData:()=>({data:new Uint8ClampedArray(4)}), setTransform:()=>{}, canvas:this };
  };

  function loadScript(p) { win.eval(fs.readFileSync(p, 'utf-8')); }
  loadScript(path.join(COMPILER_DIR, 'errors.js'));
  loadScript(path.join(COMPILER_DIR, 'validator.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'stub.js'));
  loadScript(path.join(COMPILER_DIR, 'dispatcher.js'));
  loadScript(path.join(COMPILER_DIR, 'index.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'ajv', 'ajv2020.bundle.min.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'vega', 'vega.min.js'));
  loadScript(path.join(COMPILER_DIR, 'vendor', 'vega-lite', 'vega-lite.min.js'));
  loadScript(path.join(COMPILER_DIR, 'ajv-init.js'));
  loadScript(path.join(COMPILER_DIR, 'renderers', 'vega-lite.js'));

  const envelope = {
    schema_version: '0.2', id: 'x', type: 'comparison', mode_context: 'test',
    relation_to_prose: 'integrated',
    spec: {
      $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
      data: { values: [{c:'A', v:10}] },
      mark: 'bar',
      encoding: { x:{field:'c', type:'nominal'}, y:{field:'v', type:'quantitative'} },
      caption: {source:'t', period:'Q1', n:1, units:'u'}
    },
    semantic_description: { level_1_elemental:'x', level_2_statistical:'x', level_3_perceptual:'x', level_4_contextual: null, short_alt:'x', data_table_fallback: null },
    title: 'T'
  };

  // Call compile
  const res = win.OraVisualCompiler.compile(envelope);
  console.log('compile result type:', typeof res);
  console.log('has .then:', typeof res.then === 'function');
  console.log('res keys:', Object.keys(res));
  console.log('res.svg type:', typeof res.svg);
  console.log('res.svg length:', (res.svg || '').length);
  console.log('res.errors:', JSON.stringify(res.errors));
  console.log('res.warnings:', JSON.stringify(res.warnings));
}

main().catch(e => console.error('fatal:', e.stack || e));
