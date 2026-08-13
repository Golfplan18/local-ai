import { build } from "esbuild";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, "../static/vendor/excalidraw");

await rm(out, { recursive: true, force: true });
await mkdir(out, { recursive: true });

await build({
  entryPoints: [join(here, "src/island.jsx")],
  outfile: join(out, "ora-excalidraw.js"),
  bundle: true,
  minify: true,
  sourcemap: false,
  format: "iife",
  platform: "browser",
  target: ["chrome110", "safari16.4", "firefox115"],
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".woff2": "dataurl", ".woff": "dataurl", ".ttf": "dataurl" },
  legalComments: "external",
});

const excalidrawDist = resolve(here, "node_modules/@excalidraw/excalidraw/dist/prod");
await cp(join(excalidrawDist, "index.css"), join(out, "excalidraw.css"));
await cp(join(excalidrawDist, "fonts"), join(out, "fonts"), { recursive: true });
await rm(join(out, "fonts/Liberation"), { recursive: true, force: true });

const licensed = [
  ["@excalidraw/excalidraw", resolve(here, "licenses/EXCALIDRAW-LICENSE.txt")],
  ["react", "LICENSE"],
  ["react-dom", "LICENSE"],
  ["scheduler", "LICENSE"],
];
let notices = "Ora Excalidraw island — bundled third-party notices\n\n";
for (const [pkg, filename] of licensed) {
  const pkgDir = resolve(here, "node_modules", pkg);
  const metadata = JSON.parse(await readFile(join(pkgDir, "package.json"), "utf8"));
  notices += `${metadata.name} ${metadata.version} — ${metadata.license || "license in package"}\n`;
  const licensePath = filename.startsWith('/') ? filename : join(pkgDir, filename);
  const licenseText = await readFile(licensePath, "utf8");
  notices += `${licenseText.trim()}\n\n`;
}
const fontLicenses = await readFile(
  resolve(here, "licenses/FONT-LICENSES.txt"),
  "utf8",
);
notices += `${fontLicenses.trim()}\n`;
await writeFile(join(out, "THIRD_PARTY_NOTICES.txt"), notices, "utf8");
