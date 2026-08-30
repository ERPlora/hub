// hub#1102 — a PLATFORM failure is not a sentence a module wrote, so no module should be printing
// it.
//
// The incident: with `taxes` uninstalled, the cashier tapped Charge and the pay dialog showed
// «required read `taxes.rules.list` is unavailable — the command was aborted (hub#701)» — English,
// backticks, the name of an internal query and a GitHub issue number, on the till, in front of a
// customer. `erp-pos-touch` was doing the ordinary thing (`this.error = e.message`) and every one
// of the 25 modules does the same, so fixing it module by module fixes it 25 times and misses the
// 26th.
//
// The runtime half landed in hub#1074: the plumbing no longer travels as prose, and what survives
// is a stable `code` plus the app as a FIELD. This is the other half — the SDK turns that code into
// the sentence a person can act on, in their language (ADR-0055: `en` is the source, `es` the
// translation), so a module that shows `e.message` is right without changing a line.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ErploraError, HttpWsTransport, platformFailureMessage } from './index.ts';

/** The runtime's answer, verbatim in shape: envelope, stable code, app as a field. */
function runtimeAnswering(error: Record<string, unknown>): typeof fetch {
  return (async () => ({
    ok: false,
    status: 409,
    headers: { get: () => 'application/json' },
    json: async () => ({ ok: false, error }),
  })) as unknown as typeof fetch;
}

function transportWith(error: Record<string, unknown>): HttpWsTransport {
  return new HttpWsTransport({ baseUrl: 'http://h', fetchImpl: runtimeAnswering(error) });
}

test('hub#1102: the cashier reads about the missing app, not about the query that needed it', async () => {
  const transport = transportWith({
    code: 'read_unavailable',
    message: 'a required read (`taxes.rules.list`) could not be resolved, so the command was aborted',
    query: 'taxes.rules.list',
  });

  await assert.rejects(
    () => transport.command('sales.complete_sale', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      // The code is untouched: it is what a module branches on and what hub#1074 stabilised.
      assert.equal(e.code, 'read_unavailable');
      assert.match(e.message, /taxes/, 'the sentence names the app to go after');
      assert.doesNotMatch(e.message, /`/, 'no backticks on a till');
      assert.doesNotMatch(e.message, /hub#/, 'no issue numbers on a till');
      assert.doesNotMatch(e.message, /rules\.list/, 'no internal query names on a till');
      return true;
    },
  );
});

test('hub#1102: a module that is not installed says so in business language, with the remedy', () => {
  const es = platformFailureMessage(
    { code: 'module_not_installed', module: 'taxes' },
    'es',
  );
  assert.ok(es, 'a code the till can hit must have a sentence');
  assert.match(es!, /taxes/);
  assert.match(es!, /Apps/, 'the remedy names WHERE to go, or it is not a remedy');

  const en = platformFailureMessage({ code: 'module_not_installed', module: 'taxes' }, 'en');
  assert.notEqual(en, es, 'en is the source and es the translation (ADR-0055), not one string');
});

test('hub#1102: a switched-off app is a different sentence from a missing one', () => {
  const off = platformFailureMessage({ code: 'module_inactive', module: 'taxes' }, 'es');
  const gone = platformFailureMessage({ code: 'module_not_installed', module: 'taxes' }, 'es');
  assert.notEqual(off, gone, 'switching one back on and installing it are different actions');
});

test('hub#1074/#1102: the redacted plumbing gets the one sentence there is to say', async () => {
  // What `/api/command` answers now for a foreign-key violation: a stable code and an English
  // placeholder written for the log, not for a person.
  const transport = transportWith({
    code: 'db',
    message: 'the request could not be completed — the hub recorded the details',
  });

  await assert.rejects(
    () => transport.command('sales.complete_sale', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'db');
      assert.match(e.message, /No se pudo/, 'the till speaks Spanish by default (ADR-0055)');
      return true;
    },
  );
});

test('hub#139: a module domain refusal is NEVER rewritten — it is the module talking', async () => {
  const sentence = 'No quedan unidades de este producto';
  const transport = transportWith({ code: 'inventory.insufficient_stock', message: sentence });

  await assert.rejects(
    () => transport.command('sales.complete_sale', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.message, sentence);
      return true;
    },
  );
});

test('an unknown code keeps the sentence the runtime sent: inventing one would say less', () => {
  assert.equal(platformFailureMessage({ code: 'flow.grant_denied' }, 'es'), null);
  assert.equal(platformFailureMessage({ code: 'permission_denied' }, 'es'), null);
});

test('a platform code with no app to name still produces a usable sentence', () => {
  // `read_unavailable` always carries `query`, but an older runtime does not. Naming nothing beats
  // printing «undefined» at a counter.
  const message = platformFailureMessage({ code: 'read_unavailable' }, 'es');
  assert.ok(message);
  assert.doesNotMatch(message!, /undefined/);
});

test('hub#1070/#1185: `invalid_field` pasa intacto — su `detail` dice más de lo que podríamos inventar', async () => {
  const transport = transportWith({
    code: 'invalid_field',
    message: 'role `admin` is a base role of the hub: base roles are always active and cannot be switched off',
    field: 'role_key',
    reason: 'immutable',
  });

  await assert.rejects(
    () => transport.command('hub.roles.activate', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'invalid_field');
      // Ni lo reescribimos ni lo tocamos: la frase del runtime nombra el rol y el motivo, y una
      // que construyéramos con `field` + `reason` diría menos.
      assert.match(e.message, /base role/);
      return true;
    },
  );

  // Y el motivo es DATO, no prosa: quien quiera traducirlo ramifica sobre `reason`.
  assert.equal(platformFailureMessage({ code: 'invalid_field', field: 'role_key', reason: 'immutable' }, 'es'), null);
});

// hub#1315: `apps/web/src/lib/platform-failure.ts` (hub#1258) kept a BYTE-IDENTICAL copy of these
// same ten sentences for the shell, over vue-i18n keys instead of this table — a wording tweak on
// either side would drift the other in silence, and this table was already missing `manifest`
// (a code `may_reach_the_client`, `crates/server/src/lib.rs`, redacts exactly like its five
// plumbing siblings, but one only a module-INSTALL-time error had ever needed). This test is the
// guard: the shell now imports `platformFailureMessage` straight from this file instead of holding
// its own catalogue, so any code the runtime's authenticated door can answer with has to have an
// entry HERE, in both languages, or a screen falls back to the runtime's raw English sentence
// (`hub#1102`'s original bug, for a code nobody thought to cover).
test('hub#1315: every code the authenticated door can answer with has an entry, in both languages', () => {
  // Mirrors `may_reach_the_client` (`crates/server/src/lib.rs`): the six codes it redacts to the
  // fixed PLUMBING line — db/io/wasm/native/schema/manifest — plus the four whose remedy names an
  // app (`error_code_of`, `crates/runtime/src/error_registry.rs`).
  const codes = [
    'db', 'io', 'wasm', 'native', 'schema', 'manifest',
    'module_not_installed', 'module_inactive', 'missing_dependency', 'read_unavailable',
  ] as const;

  for (const code of codes) {
    for (const locale of ['es', 'en'] as const) {
      const message = platformFailureMessage({ code, module: 'taxes', query: 'taxes.rules.list' }, locale);
      assert.ok(
        message,
        `code "${code}" (${locale}) has no entry in PLATFORM_FAILURES — a screen would show the ` +
          'runtime\'s raw sentence instead, exactly the incident hub#1102 fixed for the other codes',
      );
    }
  }
});
