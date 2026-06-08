// `erplora module build:all`: compila el Web Component de TODOS los módulos con UI a su
// `dist/<id>.esm.js` (Lit, auto-contenido, CSP-safe) reutilizando el builder de `build.mjs`.
// Reemplaza al antiguo compilador Stencil compartido (`@erplora/module-stencil`). ARQUITECTURA.md §4.
//
// Uso:  node src/build-all.mjs [<id> ...]   (sin args = todos los módulos con entry de WC)
import { readdirSync, existsSync, statSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from './build.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const modulesRoot = resolve(here, '../../../modules');

// Un módulo es "construible" si tiene un entry de WC: `src/*.js` (ejemplos legacy) o
// `ui/components/**/*.ts` (Lit post-migración). El resto (solo manifest/SQL) se salta.
function hasEntry(dir) {
  const srcDir = join(dir, 'src');
  if (existsSync(srcDir) && readdirSync(srcDir).some((n) => n.endsWith('.js'))) return true;
  return existsSync(join(dir, 'ui', 'components'));
}

const want = process.argv.slice(2);
const ids = readdirSync(modulesRoot)
  .filter((name) => {
    if (want.length && !want.includes(name)) return false;
    const dir = join(modulesRoot, name);
    return existsSync(join(dir, 'module.json')) && statSync(dir).isDirectory() && hasEntry(dir);
  })
  .sort();

let ok = 0;
const failed = [];
for (const id of ids) {
  try {
    await build(join(modulesRoot, id));
    ok++;
  } catch (err) {
    failed.push(id);
    console.error(`✗ build ${id}: ${err.message}`);
  }
}

console.log(`\n${ok}/${ids.length} módulo(s) construido(s)${failed.length ? `, ${failed.length} con error: ${failed.join(', ')}` : ''}.`);
if (failed.length) process.exit(1);
