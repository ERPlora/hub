// Verifica que el output de OutfitKit sea compatible con CSP estricta (`script-src 'self'`):
// ningún bundle puede usar eval/new Function. Mismo listón que packages/module-cli y
// apps/web/snapshot.mjs. Uso: node scripts/assert-csp-safe.mjs dist
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';

function jsFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...jsFiles(p));
    else if (name.endsWith('.js')) out.push(p);
  }
  return out;
}

function assertCspSafe(code, label) {
  const hits = [];
  for (const _ of code.matchAll(/\beval\s*\(/g)) hits.push('eval(');
  for (const _ of code.matchAll(/new\s+Function\s*\(/g)) hits.push('new Function(');
  if (hits.length) {
    throw new Error(`${label}: ${hits.length} uso(s) que la CSP estricta bloquearía (${[...new Set(hits)].join(', ')}).`);
  }
}

const dir = resolve(process.cwd(), process.argv[2] ?? 'dist');
const files = jsFiles(dir);
if (!files.length) throw new Error(`No hay .js en ${dir} — ¿ejecutaste el build?`);
for (const f of files) assertCspSafe(readFileSync(f, 'utf8'), f.replace(dir, '').replace(/^\//, ''));
console.log(`✓ CSP-safe: ${files.length} fichero(s) en ${dir} sin eval/new Function`);
