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
  // Un módulo puede declarar VARIAS vistas de navegación, cada una con su propio
  // component. El bundle ui.entry debe incluir TODAS (no solo navigation[0]), o las
  // vistas secundarias serían custom elements no definidos en runtime (nav muerta).
  const tags = [...new Set((manifest.navigation ?? []).map((n) => n.component).filter(Boolean))];
  if (!tags.length) {
    console.warn(`⚠ ${id}: navigation[].component ausente; salto`);
    continue;
  }
  // Cada custom element transpilado vive en .stencil-out/<tag>.js y se auto-define al importarse.
  const missing = tags.filter((t) => !existsSync(join(stencilOut, `${t}.js`)));
  if (missing.length) {
    console.warn(`⚠ ${id}: no encuentro en .stencil-out: ${missing.join(', ')} (¿@Component tag correcto?)`);
    continue;
  }
  const outfile = join(modulesRoot, id, manifest.ui.entry);
  mkdirSync(dirname(outfile), { recursive: true });
  // Entry sintético que importa (efecto secundario → auto-define) cada componente de nav.
  const entryContents = tags.map((t) => `import './${t}.js';`).join('\n');
  await esbuild({
    stdin: { contents: entryContents, resolveDir: stencilOut, sourcefile: `${id}.entry.js`, loader: 'js' },
    bundle: true,
    format: 'esm',
    outfile,
    minify: true,
    sourcemap: false,
    target: 'es2022',
    legalComments: 'none',
  });
  const kb = (readFileSync(outfile).length / 1024).toFixed(1);
  console.log(`✓ ${id} → ${manifest.ui.entry} (${kb} KB, ${tags.map((t) => `<${t}>`).join(' ')} auto-define)`);
}
