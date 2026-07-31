// `erplora module validate`: valida el manifest contra schemas/module.schema.json
// (validación mínima sin dependencias) y, si hay bundle, que sea CSP-safe.
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { resolve, join } from 'node:path';

// Validación CSP: el bundle no puede usar eval/new Function (los bloquea `script-src 'self'`).
export function assertCspSafe(code, label = 'bundle') {
  const hits = [];
  for (const m of code.matchAll(/\beval\s*\(/g)) hits.push('eval(');
  for (const m of code.matchAll(/new\s+Function\s*\(/g)) hits.push('new Function(');
  if (hits.length) {
    throw new Error(`${label}: ${hits.length} uso(s) que la CSP estricta bloquearía (${[...new Set(hits)].join(', ')}).`);
  }
}

export async function validate(moduleDir) {
  const dir = resolve(process.cwd(), moduleDir);
  const manifest = JSON.parse(readFileSync(join(dir, 'module.json'), 'utf8'));

  // Comprobaciones mínimas del contrato (espejo de schemas/module.schema.json).
  const errs = [];
  if (!/^[a-z][a-z0-9_]*$/.test(manifest.id ?? '')) errs.push('id inválido');
  if (!manifest.name) errs.push('name requerido');
  if (!/^\d+\.\d+\.\d+/.test(manifest.version ?? '')) errs.push('version SemVer inválida');
  for (const nav of manifest.navigation ?? []) {
    if (!/^[a-z][a-z0-9]*-[a-z0-9-]+$/.test(nav.component ?? '')) {
      errs.push(`navigation.component inválido: ${nav.component}`);
    }
  }
  // La clasificación de marketplace NO debe estar en el manifest (ARQUITECTURA.md §2.4).
  for (const forbidden of ['sectors', 'business_types', 'functional_unit', 'pricing']) {
    if (forbidden in manifest) errs.push(`campo prohibido en manifest (vive en Cloud): ${forbidden}`);
  }

  if (errs.length) throw new Error('manifest inválido:\n  - ' + errs.join('\n  - '));

  // hub#135: si un comando declara `handler.type === "wasm"`, el `dist/handler.wasm` debe ser
  // REPRODUCIBLE desde el source Rust presente (`handler/`). Antes `validate` solo tocaba el
  // bundle JS: un módulo pasaba `erplora validate` con un `dist/handler.wasm` cuyo source actual
  // no compilaba (ERPlora/services#11 `round_cents`), o — peor — con un dist ALTERADO que no se
  // generaba desde el source revisado. El runtime ejecutaba el wasm viejo/troyanizado en silencio.
  //
  // Política (para no romper módulos ya publicados ni módulos sin WASM):
  //  - Sin handler wasm declarado → válido, no se comprueba.
  //  - Con `handler/Cargo.toml` → build determinista (`cargo build --release --target wasm32`)
  //    y comparación SHA256 del artefacto recién construido contra el `dist/handler.wasm`
  //    comprometido. Si el source no compila → FAIL. Si los hashes difieren → FAIL (dist
  //    alterado o no regenerado). Es la condición que cazaba el bug real.
  //  - Con handler wasm pero sin `handler/` (wasm precompilado de terceros) → se exige y verifica
  //    un par registrado `source-hash`+`dist-hash` (issue #135 requisito mínimo); si no existe,
  //    WARN (no bloquea, para no romper módulos ya publicados sin source).
  //  - Si `cargo`/`rustup` o el target `wasm32` no están disponibles → se cae al par de hashes
  //    registrado (build reproducible no factible en ese entorno) y se avisa.
  const wasm = verifyWasmHandler(dir, manifest);
  for (const w of wasm.warnings) console.warn(`⚠ ${manifest.id}: ${w}`);
  if (wasm.errors.length) {
    throw new Error('handler WASM no se verifica contra el source (hub#135):\n  - ' + wasm.errors.join('\n  - '));
  }

  // Si ya hay bundle, comprueba CSP.
  const bundle = join(dir, 'dist', `${manifest.id}.esm.js`);
  if (existsSync(bundle)) assertCspSafe(readFileSync(bundle, 'utf8'), `${manifest.id} bundle`);

  const wasmNote = wasm.checked ? ` + handler WASM ${wasm.checked}` : '';
  console.log(`✓ validate ${manifest.id}: manifest OK${existsSync(bundle) ? ' + bundle CSP-safe' : ''}${wasmNote}`);
}

/// Verifica que todo `commands[].handler` de tipo `wasm` tenga un `dist/handler.wasm` que se genera
/// (o que está ligado por hash) al source Rust presente. hub#135.
///
/// Devuelve `{ checked: string|null, errors: string[], warnings: string[] }`:
/// - `checked: null` y sin errores → el módulo no declara WASM (o cae a warning): válido.
/// - `checked: 'reproducible'` → se compiló el source y el hash del artefacto coincide con el dist.
/// - `checked: 'hash-pair'` → no había toolchain, pero el par source-hash+dist-hash registrado coincide.
/// - `errors` no vacío → FAIL (el source no compila, o el dist no coincide con el source).
export function verifyWasmHandler(dir, manifest) {
  const out = { checked: null, errors: [], warnings: [] };
  const cmds = Object.values(manifest.commands ?? {});
  const wasmHandler = cmds.find((c) => c?.handler?.type === 'wasm');
  if (!wasmHandler) return out; // módulo sin handler WASM: nada que verificar.

  // El dist comprometido que el runtime termina cargando. Por convención `dist/handler.wasm`
  // (lo que declara `handler.file` si está, o el default del paquete).
  const distPath = join(dir, wasmHandler.handler.file || 'dist/handler.wasm');
  const handlerDir = join(dir, 'handler');
  const cargoToml = join(handlerDir, 'Cargo.toml');

  if (!existsSync(cargoToml)) {
    // Handler wasm declarado pero sin source distribuido. Válido SOLO si hay un par de hashes
    // registrado (política explícita de "wasm precompilado de terceros"); sin esa señal, avisamos.
    const hashPair = readRecordedHashPair(dir);
    if (hashPair) {
      const distHashActual = fileSha256(distPath);
      if (distHashActual && distHashActual !== hashPair.distHash) {
        out.errors.push(
          `dist/handler.wasm (sha256 ${distHashActual.slice(0, 12)}…) no coincide con el ` +
            `dist-hash registrado (${hashPair.distHash.slice(0, 12)}…) en ${hashPair.file} (hub#135).`,
        );
      } else {
        out.checked = 'hash-pair';
      }
    } else if (existsSync(distPath)) {
      out.warnings.push(
        'declara handler.type=wasm pero no trae handler/Cargo.toml ni un par source-hash/dist-hash ' +
          'registrado: no se puede verificar que dist/handler.wasm se genere desde este commit. ' +
          'Si es un módulo first-party, añade handler/. (hub#135)',
      );
    } else {
      out.errors.push('declara handler.type=wasm pero no existe dist/handler.wasm ni handler/ (hub#135).');
    }
    return out;
  }

  // --- Camino reproducible: compilar el source y comparar hashes. ---
  const toolchain = resolveWasmToolchain();
  if (!toolchain.available) {
    // Sin toolchain wasm no se puede construir. Cae al par de hashes registrado (issue #135
    // requisito mínimo) si existe; si no, avisa para no bloquear a un dev sin toolchain.
    out.warnings.push(
      `no se pudo construir el handler WASM (${toolchain.reason}). ` +
        'Verifica source↔dist en un entorno con cargo + target wasm32-unknown-unknown. (hub#135)',
    );
    const hashPair = readRecordedHashPair(dir);
    if (hashPair) {
      const srcHashActual = dirTreeSha256(handlerDir);
      const distHashActual = fileSha256(distPath);
      if (srcHashActual && srcHashActual !== hashPair.sourceHash) {
        out.errors.push(
          `handler/ (sha256 ${srcHashActual.slice(0, 12)}…) no coincide con el source-hash registrado ` +
            `(${hashPair.sourceHash.slice(0, 12)}…) en ${hashPair.file} (hub#135).`,
        );
      } else if (distHashActual && distHashActual !== hashPair.distHash) {
        out.errors.push(
          `dist/handler.wasm (sha256 ${distHashActual.slice(0, 12)}…) no coincide con el dist-hash ` +
            `registrado (${hashPair.distHash.slice(0, 12)}…) en ${hashPair.file} (hub#135).`,
        );
      } else {
        out.checked = 'hash-pair';
      }
    }
    return out;
  }

  // 1) El source debe compilar (primera barrera del bug real: `round_cents` no existía).
  const build = buildWasmRelease(cargoToml, toolchain);
  if (build.status !== 0) {
    const tail = (build.stderr || build.stdout || '').split('\n').filter(Boolean).slice(-8).join('\n    ');
    out.errors.push(`handler/ no compila a wasm32 (hub#135):\n    ${tail || 'cargo terminó sin salida'}`);
    return out;
  }

  // 2) El artefacto recién construido debe hashear igual que el dist comprometido.
  if (!existsSync(distPath)) {
    out.errors.push(
      `handler/ compila pero no existe dist/handler.wasm: ejecuta el build del módulo para regenerarlo (hub#135).`,
    );
    return out;
  }
  const builtHash = fileSha256(build.artifact);
  const distHash = fileSha256(distPath);
  if (builtHash !== distHash) {
    out.errors.push(
      `dist/handler.wasm no se genera desde el source presente: hash del build ${builtHash.slice(0, 12)}… ` +
        `≠ hash del dist ${distHash.slice(0, 12)}…. Regenera dist/handler.wasm con el build estándar ` +
        `(cargo build --release --target wasm32-unknown-unknown) o, si el build no es determinista en ` +
        `tu entorno, registra un par source-hash/dist-hash. (hub#135)`,
    );
    return out;
  }
  out.checked = 'reproducible';
  return out;
}

/// Comprueba que `cargo` y el target `wasm32-unknown-unknown` estén disponibles para un build
/// determinista del handler. Devuelve `{ available, cargo?, reason? }`.
export function resolveWasmToolchain() {
  // Comprueba si un ejecutable está en el PATH sin invocar una shell (evita DEP0190).
  const which = (exe) => {
    const paths = (process.env.PATH || '').split(':');
    return paths.some((p) => p && existsSync(join(p, exe))) ? exe : null;
  };
  const cargo = which('cargo');
  if (!cargo) return { available: false, reason: 'cargo no instalado' };
  // `rustup target list --installed` confirma el target wasm; sin él `cargo build --target wasm32`
  // falla. Si no hay rustup (cargo standalone), asumimos que el target está (el build lo dirá).
  const rustup = which('rustup');
  if (rustup) {
    const res = spawnSync(rustup, ['target', 'list', '--installed'], { encoding: 'utf8' });
    const targets = (res.stdout || '').split('\n');
    if (!targets.includes('wasm32-unknown-unknown')) {
      return { available: false, reason: 'target wasm32-unknown-unknown no instalado (rustup target add wasm32-unknown-unknown)' };
    }
  }
  return { available: true, cargo };
}

/// `cargo build --release --target wasm32-unknown-unknown` del crate del handler. Devuelve el
/// resultado de spawn + la ruta al artefacto `.wasm` generado (nombre del crate + `.wasm`).
export function buildWasmRelease(cargoToml, toolchain) {
  const res = spawnSync(toolchain.cargo, ['build', '--release', '--target', 'wasm32-unknown-unknown', '--manifest-path', cargoToml, '--quiet'], {
    encoding: 'utf8',
    timeout: 300000,
  });
  let artifact = null;
  if (res.status === 0) {
    artifact = locateWasmArtifact(cargoToml);
  }
  return { status: res.status, stdout: res.stdout, stderr: res.stderr, artifact };
}

/// Resuelve la ruta del `.wasm` que `cargo build` deja en `target/wasm32-unknown-unknown/release/`.
/// El nombre del fichero es `<crate-name>.wasm`, donde el crate-name viene del `[package].name` del
/// `Cargo.toml` (con `-` → `_` para el nombre de la cdylib).
export function locateWasmArtifact(cargoToml) {
  const manifestDir = join(cargoToml, '..');
  // target/ compartido del workspace si existe, si no el del propio módulo.
  const workspaceTarget = findUpTarget(manifestDir);
  const targetDir = workspaceTarget || join(manifestDir, 'target');
  const crateName = readCrateName(cargoToml).replace(/-/g, '_');
  const candidate = join(targetDir, 'wasm32-unknown-unknown', 'release', `${crateName}.wasm`);
  return existsSync(candidate) ? candidate : null;
}

/// Busca el `target/` del workspace caminando hacia arriba desde `startDir` hasta hallar
/// `target/wasm32-unknown-unknown` (señal de que hay un target compartido ya usado).
function findUpTarget(startDir) {
  let dir = startDir;
  for (let i = 0; i < 8; i++) {
    const candidate = join(dir, 'target');
    if (existsSync(join(candidate, 'wasm32-unknown-unknown'))) return candidate;
    const parent = join(dir, '..');
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

/// Lee el `[package].name` de un `Cargo.toml` (parseo ligero, sin dependencias).
function readCrateName(cargoToml) {
  const text = readFileSync(cargoToml, 'utf8');
  const m = text.match(/^\s*\[package\][\s\S]*?^\s*name\s*=\s*"([^"]+)"/m);
  return m ? m[1] : 'handler';
}

/// SHA-256 de un fichero (hex). `null` si no existe.
export function fileSha256(path) {
  if (!existsSync(path)) return null;
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

/// SHA-256 determinista de un árbol de directorios (contenido de ficheros, ordenado, sin metadatos
/// del FS). Estable entre sistemas para el MISMO contenido de source.
export function dirTreeSha256(dir) {
  if (!existsSync(dir)) return null;
  const entries = [];
  const walk = (d, rel = '') => {
    for (const name of readdirSyncSorted(d)) {
      if (name === 'target' || name === 'dist' || name.startsWith('.')) continue;
      const full = join(d, name);
      const r = rel ? `${rel}/${name}` : name;
      if (statSync(full).isDirectory()) walk(full, r);
      else entries.push([r, readFileSync(full)]);
    }
  };
  walk(dir);
  if (!entries.length) return null;
  const h = createHash('sha256');
  entries.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  for (const [rel, bytes] of entries) {
    h.update(rel);
    h.update('\0');
    h.update(bytes);
    h.update('\0');
  }
  return h.digest('hex');
}

function readdirSyncSorted(d) {
  return readdirSync(d).sort();
}

/// Lee el par registrado `source-hash`/`dist-hash` del módulo desde `handler.manifest.json` (junto
/// al `Cargo.toml`) o `dist/handler.wasm.sha256` + `handler/source.sha256`. Devuelve `{ sourceHash,
/// distHash, file }` o `null` si no hay par completo.
export function readRecordedHashPair(dir) {
  // Forma preferida: un único fichero `handler/manifest.json` con ambos hashes.
  const handlerManifest = join(dir, 'handler', 'manifest.json');
  if (existsSync(handlerManifest)) {
    try {
      const j = JSON.parse(readFileSync(handlerManifest, 'utf8'));
      const sh = j['source-hash'] || j['sourceHash'];
      const dh = j['dist-hash'] || j['distHash'];
      if (sh && dh) return { sourceHash: sh, distHash: dh, file: 'handler/manifest.json' };
    } catch {
      /* ilegible → cae a ficheros sueltos */
    }
  }
  // Forma suelta: dos ficheros junto a cada artefacto.
  const srcFile = join(dir, 'handler', 'source.sha256');
  const distFile = join(dir, 'dist', 'handler.wasm.sha256');
  if (existsSync(srcFile) && existsSync(distFile)) {
    const sh = firstHashLine(readFileSync(srcFile, 'utf8'));
    const dh = firstHashLine(readFileSync(distFile, 'utf8'));
    if (sh && dh) return { sourceHash: sh, distHash: dh, file: 'handler/source.sha256 + dist/handler.wasm.sha256' };
  }
  return null;
}

function firstHashLine(text) {
  // Acepta `<hash>` o el formato coreutils `<hash>  <file>`.
  const line = text.split('\n').map((l) => l.trim()).find(Boolean);
  return line ? line.split(/\s+/)[0] : null;
}
