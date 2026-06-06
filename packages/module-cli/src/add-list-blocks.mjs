// Migración masiva (one-off): añade el bloque `list` a las queries `*_list.sql`/`list.sql` y
// limpia el SELECT base (quita ORDER BY/LIMIT/OFFSET/`;` que ahora pone el runtime).
//
// SEGURIDAD: por defecto DRY-RUN (no escribe nada; solo informa). Pasa `--apply` para escribir.
// Salta (y reporta) cualquier query "compleja" que no sea seguro transformar con regex
// (CTE/GROUP BY/agregados/window/UNION/subconsultas/filtros hand-rolled) → revisión manual.
//
// Heurística del bloque `list` (tuneable a mano después):
//  - sort   = TODAS las columnas proyectadas (identificadores simples). "por cada campo".
//  - filters= TODAS las columnas: `range` si el nombre parece numérico/fecha; si no, `eq`.
//  - search = columnas con pinta de texto (name/sku/title/email/…); si ninguna, ninguna.
//  - default_sort = created_at | name | 1ª columna; dir = desc si created_at, si no asc.
//
// Uso:  node src/add-list-blocks.mjs [--apply] [<moduleId> ...]
import { readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const modulesRoot = resolve(here, '../../../modules');
const APPLY = process.argv.includes('--apply');
const KEEP_CONTEXT = process.argv.includes('--keep-context');
const want = process.argv.slice(2).filter((a) => !a.startsWith('--'));

const TEXT_COL = /(^|_)(name|sku|title|subject|email|phone|reference|ref|code|description|label|slug|number|company|customer|supplier|tax_id|full_name)(_|$)/i;
const RANGE_COL = /(_at$|_date$|^date$|_on$)|(^|_)(price|cost|total|subtotal|amount|tax|qty|quantity|stock|balance|rate|discount|hours|commission|net|gross|paid|due|value|count|threshold|score|limit|min|max)(_|$)/i;
// Solo lo que de verdad rompe el wrapping `(base) AS sub` o el parseo de columnas:
// GROUP BY / UNION / CTE / window. Un subselect escalar en la proyección
// (`(SELECT COUNT(*) …) AS x`) es SEGURO de envolver → no se considera complejo.
const COMPLEX = /\b(group\s+by|union|with\s+[a-z_]+\s+as\s*\(|over\s*\()/i;
// Idioma de filtro opcional hand-rolled a eliminar: `AND ( :param … OR … )`. El bloque `list`
// del runtime los sustituye (cada columna pasa a ser filtrable). Tras quitarlos, si queda algún
// `:param` obligatorio en la base (p.ej. una ventana de fechas `>= :day_start`) → revisión manual.
const OPTIONAL_FILTER = /\s*AND\s*\(\s*:\w+\b[^)]*\bOR\b[^)]*\)/gi;

function isIdent(s) {
  return /^[a-z_][a-z0-9_]*$/i.test(s);
}

// Encuentra el índice del `FROM` de nivel superior (depth 0), ignorando el que pueda haber
// dentro de un subselect en la proyección. Devuelve -1 si no hay.
function topLevelFromIndex(code) {
  let depth = 0;
  let inStr = false;
  for (let i = 0; i < code.length; i++) {
    const c = code[i];
    if (inStr) {
      if (c === "'") inStr = false;
      continue;
    }
    if (c === "'") inStr = true;
    else if (c === '(') depth++;
    else if (c === ')') depth--;
    else if (depth === 0 && (c === 'f' || c === 'F')) {
      if (/^from\b/i.test(code.slice(i)) && /\s/.test(code[i - 1] ?? ' ')) return i;
    }
  }
  return -1;
}

// Extrae el SELECT base (sin comentarios líderes), separa proyección y "resto" (FROM…WHERE…).
function parseSelect(sql) {
  // Quita comentarios de línea para el análisis (no para reescribir).
  const code = sql
    .split('\n')
    .filter((l) => !l.trim().startsWith('--'))
    .join('\n')
    .trim();
  if (!/^select\s/i.test(code)) return null;
  if (COMPLEX.test(code)) return { complex: true, reason: 'GROUP BY/UNION/CTE/window' };
  const fromIdx = topLevelFromIndex(code);
  if (fromIdx < 0) return { complex: true, reason: 'sin FROM de nivel superior' };
  const projection = code.slice(6, fromIdx); // tras "select"
  // Un subselect en la proyección con ORDER BY/LIMIT confundiría al stripper de cola → manual.
  if (/\border\s+by\b|\blimit\b|\boffset\b/i.test(projection)) {
    return { complex: true, reason: 'subselect con ORDER BY/LIMIT en la proyección' };
  }
  // Separa por comas de nivel superior (respeta paréntesis).
  const items = [];
  let depth = 0;
  let cur = '';
  for (const ch of projection) {
    if (ch === '(') depth++;
    else if (ch === ')') depth--;
    if (ch === ',' && depth === 0) {
      items.push(cur);
      cur = '';
    } else cur += ch;
  }
  if (cur.trim()) items.push(cur);
  const cols = [];
  for (const raw of items) {
    const item = raw.trim();
    let name;
    const asMatch = /\s+as\s+([a-z_][a-z0-9_]*)\s*$/i.exec(item);
    if (asMatch) name = asMatch[1];
    else {
      const tail = /([a-z_][a-z0-9_]*)\s*$/i.exec(item);
      name = tail ? tail[1] : null;
      // si el item es una expresión/función sin alias → no es columna referenciable
      if (name && /[)(*+\-/]/.test(item.replace(/\.[a-z_]/gi, ''))) name = null;
    }
    if (name && isIdent(name)) cols.push(name.toLowerCase());
  }
  return { complex: false, cols };
}

// Reescribe el SELECT base: quita los filtros opcionales hand-rolled (`AND (:x … OR …)`) y la
// cola `ORDER BY`/`LIMIT`/`OFFSET`/`;` (los pone el runtime). Devuelve el SQL limpio y la lista
// de `:params` que aún quedan (aparte de :hub_id) → si hay, la query tiene params obligatorios
// y NO es segura de auto-migrar.
function transformBase(sql) {
  let out = sql.replace(OPTIONAL_FILTER, '');
  out = out.replace(/;\s*$/, '').trimEnd();
  let changed = true;
  while (changed) {
    changed = false;
    const before = out;
    out = out.replace(/\s+offset\s+[^\s;]+\s*$/i, '');
    out = out.replace(/\s+limit\s+[^\s;]+(\s+offset\s+[^\s;]+)?\s*$/i, '');
    out = out.replace(/\s+order\s+by\s+[\s\S]*$/i, '');
    if (out !== before) changed = true;
  }
  out = out.trimEnd() + '\n';
  // Params que sobreviven (fuera de comentarios), excluyendo :hub_id.
  const codeOnly = out
    .split('\n')
    .filter((l) => !l.trim().startsWith('--'))
    .join('\n');
  const stray = [...new Set([...codeOnly.matchAll(/:(\w+)/g)].map((m) => m[1]))].filter(
    (p) => p !== 'hub_id',
  );
  return { sql: out, stray };
}

function buildListBlock(cols) {
  if (!cols.length) return null;
  const sort = cols.slice();
  const search = cols.filter((c) => TEXT_COL.test(c));
  const filters = {};
  for (const c of cols) {
    if (c === 'id') continue; // filtrar por id exacto rara vez aporta en una lista
    filters[c] = { op: RANGE_COL.test(c) ? 'range' : 'eq' };
  }
  const default_sort = cols.includes('created_at') ? 'created_at' : cols.includes('name') ? 'name' : cols[0];
  const default_dir = default_sort === 'created_at' ? 'desc' : 'asc';
  const block = { sort, default_sort, default_dir, filters, page_size: 50 };
  if (search.length) block.search = search;
  // Orden de claves estético: search, sort, default_sort, default_dir, filters, page_size.
  const ordered = {};
  if (search.length) ordered.search = search;
  ordered.sort = sort;
  ordered.default_sort = default_sort;
  ordered.default_dir = default_dir;
  ordered.filters = filters;
  ordered.page_size = 50;
  return ordered;
}

const stats = { modules: 0, queries: 0, migrated: 0, skippedComplex: 0, alreadyDone: 0, noFile: 0 };
const skips = [];
const context = []; // queries migradas con params de contexto (sub-listas de hijos)

const moduleIds = readdirSync(modulesRoot).filter((d) => {
  if (want.length && !want.includes(d)) return false;
  return existsSync(join(modulesRoot, d, 'module.json'));
});

for (const id of moduleIds) {
  const manifestPath = join(modulesRoot, id, 'module.json');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  const queries = manifest.queries ?? {};
  let touchedManifest = false;
  let moduleCounted = false;

  for (const [qname, qdef] of Object.entries(queries)) {
    const sqlRel = qdef.sql;
    if (!sqlRel || !/(_list|\/list)\.sql$/.test(sqlRel)) continue;
    stats.queries++;
    if (!moduleCounted) {
      stats.modules++;
      moduleCounted = true;
    }
    if (qdef.list) {
      stats.alreadyDone++;
      continue;
    }
    const sqlPath = join(modulesRoot, id, sqlRel);
    if (!existsSync(sqlPath)) {
      stats.noFile++;
      skips.push(`${id}/${qname}: SQL no encontrado (${sqlRel})`);
      continue;
    }
    const sql = readFileSync(sqlPath, 'utf8');
    const parsed = parseSelect(sql);
    if (!parsed || parsed.complex || !parsed.cols.length) {
      stats.skippedComplex++;
      const reason = parsed?.reason ?? 'no-parseable';
      skips.push(`${id}/${qname}: ${reason} → manual (${sqlRel})`);
      continue;
    }
    const { sql: cleaned, stray } = transformBase(sql);
    // `--keep-context`: migra queries con params obligatorios (sub-listas de hijos) manteniendo
    // su `:parent_id` en la base = "contexto". Salvo colisión con params reservados del runtime.
    const RESERVED = stray.filter((p) => p === 'search' || p === 'sort' || p === 'limit' || p === 'offset' || p.startsWith('f_'));
    if (stray.length && (!KEEP_CONTEXT || RESERVED.length)) {
      stats.skippedComplex++;
      const why = RESERVED.length ? `colisión con reservados [${RESERVED.join(', ')}]` : `params obligatorios [${stray.map((p) => ':' + p).join(', ')}]`;
      skips.push(`${id}/${qname}: ${why} → manual (${sqlRel})`);
      continue;
    }
    if (stray.length) context.push(`${id}/${qname}: contexto [${stray.map((p) => ':' + p).join(', ')}]`);
    const list = buildListBlock(parsed.cols);
    stats.migrated++;
    if (APPLY) {
      if (cleaned !== sql) writeFileSync(sqlPath, cleaned);
      // Inserta `list` antes de `ai` (o al final del objeto query) preservando el resto.
      const newDef = {};
      for (const [k, v] of Object.entries(qdef)) {
        if (k === 'ai') newDef.list = list;
        newDef[k] = v;
      }
      if (!('list' in newDef)) newDef.list = list;
      queries[qname] = newDef;
      touchedManifest = true;
    } else {
      console.log(`  • ${id}/${qname}  cols=[${parsed.cols.join(', ')}]  search=[${(list.search ?? []).join(',')}]`);
    }
  }

  if (APPLY && touchedManifest) {
    writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
  }
}

console.log('\n── Resumen ──');
console.log(stats);
if (context.length) {
  console.log(`\n── ${context.length} migradas con params de CONTEXTO (sub-listas; el caller debe pasarlos) ──`);
  for (const c of context) console.log('  ◦ ' + c);
}
if (skips.length) {
  console.log(`\n── ${skips.length} a revisar manualmente ──`);
  for (const s of skips) console.log('  ⚠ ' + s);
}
console.log(APPLY ? '\n✅ APLICADO (ficheros escritos)' : '\nℹ DRY-RUN (nada escrito). Re-ejecuta con --apply para aplicar.');
