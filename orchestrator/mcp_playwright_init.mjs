import { spawn } from 'node:child_process';

const installedContexts = new WeakSet();
const MAX_URL_BYTES = 8192;
const MAX_OUTPUT_BYTES = 1024;
const POLICY_TIMEOUT_MS = 4000;

// This hook is deliberately best-effort transport defense, not a claim of
// complete browser egress confinement. Pinned Chromium does not deliver
// redirect hops to route callbacks; Chrome resolves DNS independently after
// this Python check; and WebRTC/WebTransport do not traverse these handlers.
function validateWithPython(url) {
  return new Promise((resolve, reject) => {
    if (typeof url !== 'string' || Buffer.byteLength(url, 'utf8') > MAX_URL_BYTES)
      return reject(new Error('destination rejected'));
    const python = process.env.ORA_MCP_POLICY_PYTHON;
    const policyCli = process.env.ORA_MCP_POLICY_CLI;
    if (!python || !policyCli)
      return reject(new Error('destination policy unavailable'));

    const env = { PYTHONUNBUFFERED: '1' };
    for (const key of ['SystemRoot', 'WINDIR', 'TMPDIR', 'TMP', 'TEMP', 'LANG', 'LC_ALL', 'LC_CTYPE']) {
      if (process.env[key]) env[key] = process.env[key];
    }
    const child = spawn(python, [policyCli], {
      shell: false,
      stdio: ['pipe', 'pipe', 'pipe'],
      env,
    });
    let outputBytes = 0;
    let stdout = '';
    let settled = false;
    let timer;
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve();
    };
    const bound = (chunk, keep) => {
      outputBytes += chunk.length;
      if (outputBytes > MAX_OUTPUT_BYTES) {
        child.kill('SIGKILL');
        finish(new Error('destination policy response exceeded its bound'));
        return;
      }
      if (keep) stdout += chunk.toString('utf8');
    };
    child.stdout.on('data', chunk => bound(chunk, true));
    child.stderr.on('data', chunk => bound(chunk, false));
    child.on('error', () => finish(new Error('destination policy unavailable')));
    child.on('close', code => {
      if (code === 0 && stdout === 'ok\n') finish();
      else finish(new Error('destination rejected'));
    });
    timer = setTimeout(() => {
      child.kill('SIGKILL');
      finish(new Error('destination policy timed out'));
    }, POLICY_TIMEOUT_MS);
    child.stdin.end(url, 'utf8');
  });
}

export async function installRoutes(context, checker = validateWithPython) {
  if (installedContexts.has(context)) return;
  installedContexts.add(context);
  await context.route('**/*', async route => {
    try {
      await checker(route.request().url());
      await route.continue();
    } catch {
      await route.abort('blockedbyclient');
    }
  });
  await context.routeWebSocket(/.*/, async route => {
    try {
      await checker(route.url());
      route.connectToServer();
    } catch {
      await route.close({ code: 1008, reason: 'Destination blocked' });
    }
  });
}

export default async ({ page }) => {
  await installRoutes(page.context());
};
