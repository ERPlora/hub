// hub#135: validate debe verificar que el handler WASM (dist) se genera desde el source presente.
//
// Regresión de ERPlora/services#11: un módulo pasaba `erplora validate` con un `dist/handler.wasm`
// cuyo source actual NO compilaba (`round_cents`), o — peor — con un dist ALTERADO que no se
// generaba desde el source revisado. El validador comprobaba manifest/SQL/bundle, pero NO que el
// wasm se generase desde el source.
//
// Estos tests cubren la LÓGICA de detección sin invocar `cargo` (lento y dependiente de toolchain).
// Un smoke end-to-end con build reproducible real lo cubre el último test (solo si la toolchain
// wasm32 está instalada; se salta en caso contrario para no romper CI sin Rust).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, copyFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  verifyWasmHandler,
  fileSha256,
  dirTreeSha256,
  readRecordedHashPair,
  resolveWasmToolchain,
} from './validate.mjs';

function mod(files, manifest) {
  const dir = mkdtempSync(join(tmpdir(), 'erplora-wasm-'));
  for (const [name, body] of Object.entries(files)) {
    const full = join(dir, name);
    mkdirSync(join(full, '..'), { recursive: true });
    writeFileSync(full, body);
  }
  return { dir, manifest };
}

function wasmManifest() {
  return {
    id: 'm',
    name: 'M',
    version: '1.0.0',
    commands: {
      'm.create': {
        permission: 'm.write',
        sql: ['commands/create.sql'],
        handler: { type: 'wasm', file: 'dist/handler.wasm', function: 'create' },
      },
    },
  };
}

// ---------------------------------------------------------------------
// Casos declarativos (sin cargo): qué se comprueba y qué no.
// ---------------------------------------------------------------------

test('módulo sin handler WASM → checked:null, sin errores ni warnings', () => {
  const { dir, manifest } = mod(
    { 'commands/insert.sql': 'INSERT INTO t (x) VALUES (1);' },
    { commands: { 'm.insert': { permission: 'm.write', sql: ['commands/insert.sql'] } } },
  );
  const r = verifyWasmHandler(dir, manifest);
  assert.equal(r.checked, null);
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.warnings, []);
});

test('handler WASM declarado PERO sin handler/Cargo.toml ni hash-pair → warning (no bloquea)', () => {
  // El dist existe pero no hay source: no se puede verificar que corresponda al commit.
  const { dir, manifest } = mod({ 'dist/handler.wasm': Buffer.from([0x00, 0x61, 0x73, 0x6d]) }, wasmManifest());
  const r = verifyWasmHandler(dir, manifest);
  assert.equal(r.checked, null);
  assert.deepEqual(r.errors, []);
  assert.equal(r.warnings.length, 1);
  assert.match(r.warnings[0], /handler\/Cargo\.toml/);
});

test('handler WASM declarado sin dist ni source → FAIL (no puede cargar nada en runtime)', () => {
  const { dir, manifest } = mod({}, wasmManifest());
  const r = verifyWasmHandler(dir, manifest);
  assert.deepEqual(r.errors.length, 1);
  assert.match(r.errors[0], /no existe dist\/handler\.wasm ni handler\//);
});

test('wasm precompilado de terceros CON par source-hash/dist-hash válido → checked:hash-pair', () => {
  const wasm = Buffer.from([0x00, 0x61, 0x73, 0x6d]);
  const { dir, manifest } = mod(
    {
      'dist/handler.wasm': wasm,
      'handler/manifest.json': JSON.stringify({
        'source-hash': 'deadbeef'.repeat(8),
        'dist-hash': 'placeholder',
      }),
    },
    wasmManifest(),
  );
  // Ajusta el dist-hash al hash real del dist comprometido para que el par case.
  const realDistHash = fileSha256(join(dir, 'dist/handler.wasm'));
  writeFileSync(
    join(dir, 'handler', 'manifest.json'),
    JSON.stringify({ 'source-hash': 'deadbeef'.repeat(8), 'dist-hash': realDistHash }),
  );
  const r = verifyWasmHandler(dir, manifest);
  assert.equal(r.checked, 'hash-pair');
  assert.deepEqual(r.errors, []);
});

test('par hash-pair registrado pero dist ALTERADO → FAIL (el dist ya no es el verificado)', () => {
  const { dir, manifest } = mod(
    {
      'dist/handler.wasm': Buffer.from([0x00, 0x61, 0x73, 0x6d]),
      'handler/manifest.json': JSON.stringify({
        'source-hash': 'deadbeef'.repeat(8),
        'dist-hash': 'aabbccdd'.repeat(8), // deliberadamente distinto al hash real del dist
      }),
    },
    wasmManifest(),
  );
  const r = verifyWasmHandler(dir, manifest);
  assert.ok(r.errors.length >= 1, 'debe fallar: el dist no coincide con el dist-hash registrado');
  assert.match(r.errors.join('\n'), /no coincide con el dist-hash registrado/);
});

// ---------------------------------------------------------------------
// Helpers de hashing (pure, deterministas).
// ---------------------------------------------------------------------

test('fileSha256 es determinista y null si falta el fichero', () => {
  const d = mkdtempSync(join(tmpdir(), 'sha-'));
  const f = join(d, 'x.bin');
  writeFileSync(f, Buffer.from('hola'));
  assert.equal(fileSha256(f), fileSha256(f));
  assert.equal(fileSha256(join(d, 'no-existe')), null);
});

test('dirTreeSha256 ignora target/dist/.* y es estable al reordenar', () => {
  const d = mkdtempSync(join(tmpdir(), 'tree-'));
  mkdirSync(join(d, 'src'));
  writeFileSync(join(d, 'src', 'lib.rs'), 'fn main(){}');
  writeFileSync(join(d, 'Cargo.toml'), '[package]\nname="h"\n');
  const h1 = dirTreeSha256(d);
  // Reescribe en orden inverso: el hash del árbol (ordenado) no cambia.
  writeFileSync(join(d, 'Cargo.toml'), '[package]\nname="h"\n');
  writeFileSync(join(d, 'src', 'lib.rs'), 'fn main(){}');
  assert.equal(dirTreeSha256(d), h1);
  // Un cambio de contenido sí cambia el hash.
  writeFileSync(join(d, 'src', 'lib.rs'), 'fn main(){ }');
  assert.notEqual(dirTreeSha256(d), h1);
});

test('dirTreeSha256 ignora target/ y dist/ (ruido del build)', () => {
  const d = mkdtempSync(join(tmpdir(), 'tree2-'));
  mkdirSync(join(d, 'src'));
  writeFileSync(join(d, 'src', 'lib.rs'), 'fn main(){}');
  const before = dirTreeSha256(d);
  mkdirSync(join(d, 'target', 'release'), { recursive: true });
  writeFileSync(join(d, 'target', 'release', 'h.wasm'), Buffer.from([0, 1, 2]));
  mkdirSync(join(d, 'dist'), { recursive: true });
  writeFileSync(join(d, 'dist', 'handler.wasm'), Buffer.from([9, 9, 9]));
  assert.equal(dirTreeSha256(d), before, 'target/ y dist/ no deben afectar al source-hash');
});

test('readRecordedHashPair lee handler/manifest.json y los ficheros sueltos', () => {
  const d = mkdtempSync(join(tmpdir(), 'pair-'));
  mkdirSync(join(d, 'handler'));
  mkdirSync(join(d, 'dist'));
  writeFileSync(join(d, 'handler', 'manifest.json'), JSON.stringify({ 'source-hash': 'aa', 'dist-hash': 'bb' }));
  assert.deepEqual(readRecordedHashPair(d), { sourceHash: 'aa', distHash: 'bb', file: 'handler/manifest.json' });

  const d2 = mkdtempSync(join(tmpdir(), 'pair2-'));
  mkdirSync(join(d2, 'handler'));
  mkdirSync(join(d2, 'dist'));
  writeFileSync(join(d2, 'handler', 'source.sha256'), 'cccc  handler\n');
  writeFileSync(join(d2, 'dist', 'handler.wasm.sha256'), 'dddd  handler.wasm\n');
  assert.deepEqual(readRecordedHashPair(d2), {
    sourceHash: 'cccc',
    distHash: 'dddd',
    file: 'handler/source.sha256 + dist/handler.wasm.sha256',
  });

  assert.equal(readRecordedHashPair(mkdtempSync(join(tmpdir(), 'pair3-'))), null);
});

// ---------------------------------------------------------------------
// Smoke reproducible REAL: compila un handler mínimo y verifica dist↔source.
// Requiere cargo + target wasm32-unknown-unknown; se salta (`skip`) si no están.
// Este es el camino que cazaría el bug de services#11 si el source no compilara.
// ---------------------------------------------------------------------

test('build reproducible real: dist coincide con el wasm recién compilado', { timeout: 180_000 }, async () => {
  const tc = resolveWasmToolchain();
  if (!tc.available) {
    console.warn(`  [skip] toolchain wasm no disponible: ${tc.reason}`);
    return; // no rompe CI sin Rust
  }

  const handlerSrc = `
#![no_std]
#[panic_handler] fn panic(_: &core::panic::PanicInfo) -> ! { loop {} }
#[no_mangle] pub extern "C" fn create() -> i32 { 0 }
`;
  const cargoToml = `
[package]
name = "h"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]
[profile.release]
panic = "abort"
`;
  const manifest = wasmManifest();
  const dir = mod(
    {
      'handler/src/lib.rs': handlerSrc,
      'handler/Cargo.toml': cargoToml,
      'module.json': JSON.stringify(manifest),
    },
    manifest,
  ).dir;

  // Construye con el MISMO comando que usa validate, copia el artefacto a dist/, y entonces
  // validate() debe reconstruirlo y hashear igual → checked:'reproducible'.
  const { buildWasmRelease } = await import('./validate.mjs');
  const build = buildWasmRelease(join(dir, 'handler', 'Cargo.toml'), tc);
  assert.equal(build.status, 0, 'el handler mínimo debe compilar a wasm32');
  assert.ok(build.artifact, 'locateWasmArtifact debe resolver el .wasm generado');
  mkdirSync(join(dir, 'dist'), { recursive: true });
  copyFileSync(build.artifact, join(dir, 'dist', 'handler.wasm'));

  const r = verifyWasmHandler(dir, manifest);
  assert.deepEqual(r.errors, [], `no esperaba errores: ${JSON.stringify(r.errors)}`);
  assert.equal(r.checked, 'reproducible');

  rmSync(join(dir, 'handler', 'target'), { recursive: true, force: true });
});
