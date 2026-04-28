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
    schema_version: '0.2',
    id: 'fig-test',
    type: 'comparison',
    mode_context: 'test',
    relation_to_prose: 'integrated',
    spec: {
      $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
      data: { values: [{c:'A', v:10},{c:'B', v:20}] },
      mark: 'bar',
      encoding: {
        x: {field:'c', type:'nominal'},
        y: {field:'v', type:'quantitative'}
      },
      caption: { source:'test', period:'Q1', n:2, units:'u' }
    },
    semantic_description: {
      level_1_elemental: 'x', level_2_statistical: 'x', level_3_perceptual: 'x',
      level_4_contextual: null, short_alt: 'x', data_table_fallback: null
    },
    title: 'T'
  };

  // Try renderer directly without bootstrap, just to see
  const r = win.OraVisualCompiler._renderers.vegaLite;
  console.log('renderer type:', typeof r.render);
  const result = await r.render(envelope);
  console.log('render errors:', JSON.stringify(result.errors));
  console.log('render warnings:', JSON.stringify(result.warnings));
  console.log('svg length:', result.svg.length);
  if (result.svg) console.log('first 300:', result.svg.slice(0, 300));
}

main().catch(e => console.error('fatal:', e.stack || e));
