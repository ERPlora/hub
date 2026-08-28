// Regression test for ERPlora/hub#1236 — the SDK a bundle compiled against has a NAME.
//
// Until this test existed, `@erplora/module-sdk` was `private: true, version: "0.0.0"` and the
// 24 module repos declared it as `workspace:*`: a published `dist/<id>.esm.js` had no way of
// saying which SDK it was built with, and the answer was "whatever checkout of the hub the
// developer happened to have". `SDK_VERSION` is that answer, and this test is what keeps it from
// drifting away from the two files that also carry the number.
//
// The three have to agree because the release stamps all three from the SAME tag
// (`scripts/stamp-version.sh`, run by `.github/workflows/build-hub.yml`): a mismatch in the
// committed tree means one of them was edited by hand, which is exactly how a bundle ends up
// claiming a version the hub never served.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { SDK_VERSION } from './version.ts';

const packageDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = join(packageDir, '..', '..');

/** `[workspace.package] version` of the Cargo workspace — the hub's `CORE_VERSION`. */
function coreVersion(): string {
  const manifest = readFileSync(join(repoRoot, 'Cargo.toml'), 'utf8');
  const section = manifest.split(/^\[/m).find((block) => block.startsWith('workspace.package]'));
  assert.ok(section, 'no encuentro `[workspace.package]` en el Cargo.toml raíz');
  const match = /^\s*version\s*=\s*"([^"]+)"/m.exec(section);
  assert.ok(match, '`[workspace.package]` no declara `version`');
  return match[1];
}

test('SDK_VERSION es semver y nunca el hueco 0.0.0 (hub#1236)', () => {
  assert.match(SDK_VERSION, /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$/);
  assert.notEqual(SDK_VERSION, '0.0.0', 'el hueco sin rellenar no es una versión');
});

test('SDK_VERSION === la versión publicable del package.json (hub#1236)', () => {
  const pkg = JSON.parse(readFileSync(join(packageDir, 'package.json'), 'utf8'));
  assert.equal(
    SDK_VERSION,
    pkg.version,
    'lo que el bundle imprime y lo que npm publica tienen que ser el mismo número',
  );
});

test('la versión del SDK sigue a la del hub (CORE_VERSION) (hub#1236)', () => {
  assert.equal(
    SDK_VERSION,
    coreVersion(),
    'el SDK se publica DESDE el hub y con su mismo tag: `scripts/stamp-version.sh` estampa los tres',
  );
});

test('el paquete es publicable: ni `private`, ni sin registro (hub#1236)', () => {
  const pkg = JSON.parse(readFileSync(join(packageDir, 'package.json'), 'utf8'));
  assert.equal(pkg.private, undefined, '`private: true` hace que `npm publish` se niegue');
  assert.equal(pkg.publishConfig?.registry, 'https://npm.pkg.github.com');
});
