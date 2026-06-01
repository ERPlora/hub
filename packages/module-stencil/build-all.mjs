// Compilador compartido: Stencil transpila TODOS los modules/<id>/ui/**/*.tsx
// (paso 1), y esbuild empaqueta el/los componente(s) de cada módulo en un único
// modules/<id>/dist/<id>.esm.js autocontenido y auto-registrable (paso 2).
//
// Uso:  node build-all.mjs [<id> ...]   (sin args = todos los módulos con ui/)
import { build as esbuild } from 'esbuild';
import { createNodeLogger, createNodeSys } from '@stencil/core/sys/node';
import { createCompiler, loadConfig } from '@stencil/core/compiler';
import { readdirSync, existsSync, readFileSync, mkdirSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const modulesRoot = resolve(here, '../../modules');
const stencilOut = resolve(here, '.stencil-out');

// ── Paso 1: Stencil transpila todos los componentes a .stencil-out/ ──────────
const logger = createNodeLogger();
const sys = createNodeSys({ logger });
const { config, diagnostics } = await loadConfig({
  logger,
  sys,
  configPath: resolve(here, 'stencil.config.ts'),
});
if (diagnostics.some((d) => d.level === 'error')) {
  for (const d of diagnostics) console.error(d.messageText);
  process.exit(1);
}
const compiler = await createCompiler(config);
const results = await compiler.build();
await compiler.destroy();
const errs = results.diagnostics.filter((d) => d.level === 'error');
if (errs.length) {
  for (const d of errs) console.error(`✗ ${d.messageText}`);
  process.exit(1);
}
console.log(`✓ Stencil transpiló ${results.componentGraph ? Object.keys(results.componentGraph).length : '?'} componente(s)`);

// ── Paso 2: por cada módulo con ui/, esbuild-bundle de su entry ──────────────
const want = process.argv.slice(2);
const moduleIds = readdirSync(modulesRoot).filter((d) => {
  if (want.length && !want.includes(d)) return false;
  return existsSync(join(modulesRoot, d, 'ui'));
});

for (const id of moduleIds) {
  const manifestPath = join(modulesRoot, id, 'module.json');
  if (!existsSync(manifestPath)) continue;
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  const entryTag = manifest.navigation?.[0]?.component;
  if (!entryTag) {
    console.warn(`⚠ ${id}: navigation[0].component ausente; salto`);
    continue;
  }
  // El custom element transpilado vive en .stencil-out/<tag>.js y se auto-define.
  const celPath = join(stencilOut, `${entryTag}.js`);
  if (!existsSync(celPath)) {
    console.warn(`⚠ ${id}: no encuentro ${entryTag}.js en .stencil-out (¿@Component tag correcto?)`);
    continue;
  }
  const outfile = join(modulesRoot, id, manifest.ui.entry);
  mkdirSync(dirname(outfile), { recursive: true });
  await esbuild({
    entryPoints: [celPath],
    bundle: true,
    format: 'esm',
    outfile,
    minify: true,
    sourcemap: false,
    target: 'es2022',
    legalComments: 'none',
  });
  const kb = (readFileSync(outfile).length / 1024).toFixed(1);
  console.log(`✓ ${id} → ${manifest.ui.entry} (${kb} KB, <${entryTag}> auto-define)`);
}
