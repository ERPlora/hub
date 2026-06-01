// `erplora module build`: compila el Web Component del módulo a un ESM autocontenido
// (dist/<id>.esm.js) — el artefacto que va en `ui.entry` del module.zip y que el shell
// carga en runtime. Tras compilar, valida que el bundle sea compatible con CSP estricta.
import { build as esbuild } from 'esbuild';
import { readFileSync, mkdirSync, readdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { assertCspSafe } from './validate.mjs';

export async function build(moduleDir) {
  const dir = resolve(process.cwd(), moduleDir);
  const manifest = JSON.parse(readFileSync(join(dir, 'module.json'), 'utf8'));
  const id = manifest.id;

  const entryPoint = resolveEntry(dir);
  const outfile = join(dir, 'dist', `${id}.esm.js`);
  mkdirSync(join(dir, 'dist'), { recursive: true });

  await esbuild({
    entryPoints: [entryPoint],
    bundle: true,
    format: 'esm',
    target: 'es2022',
    outfile,
    minify: false,
    legalComments: 'none',
  });

  const code = readFileSync(outfile, 'utf8');
  assertCspSafe(code, `${id} bundle`);
  console.log(`✓ build ${id}: ${outfile} (${(code.length / 1024).toFixed(1)} KB, CSP-safe)`);
  return outfile;
}

// Convención: el entry del WC es el primer .js de src/ (los módulos de ejemplo tienen uno).
function resolveEntry(dir) {
  const srcDir = join(dir, 'src');
  const f = readdirSync(srcDir).find((n) => n.endsWith('.js'));
  if (!f) throw new Error(`No encuentro un .js en ${srcDir}`);
  return join(srcDir, f);
}
