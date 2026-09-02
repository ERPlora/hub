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
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
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
// (a code `may_reach_the_client`, `crates/server/src/dispatch_api.rs`, redacts exactly like its five
// plumbing siblings, but one only a module-INSTALL-time error had ever needed). This test is the
// guard: the shell now imports `platformFailureMessage` straight from this file instead of holding
// its own catalogue, so any code the runtime's authenticated door can answer with has to have an
// entry HERE, in both languages, or a screen falls back to the runtime's raw English sentence
// (`hub#1102`'s original bug, for a code nobody thought to cover).
test('hub#1315: every code the authenticated door can answer with has an entry, in both languages', () => {
  // Mirrors `may_reach_the_client` (`crates/server/src/dispatch_api.rs`): the six codes it redacts to the
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

// ── hub#1337 — `other` is NOT plumbing, and the runtime already said so ────────────────────────
//
// `may_reach_the_client` (`crates/server/src/dispatch_api.rs`) puts `E::Other(_)` on the SPEAKING side of
// the door — the same side as `Domain`, `InvalidField` or `PermissionDenied` — with
// `carries_driver_text` as the net underneath it, precisely so that the readable half of the ~50
// `Other(...)` sites ("usuario no encontrado", `hub_users.rs`) reaches whoever is reading while the
// half that wraps a `DbError` does not. This table then threw that decision away: `other` answered
// the same fixed PLUMBING sentence as the six codes the runtime DOES redact, so a screen calling
// `platformFailureMessage` could never show the authored sentence.
//
// The two codes are not the same thing, and one commit proves it: hub#1074 (`594eb485`) replaced
// the door's flat `_ => "error"` bucket with `error_code_of` — which is where `other` comes from —
// in the SAME change that introduced `may_reach_the_client`. So a hub that can answer `other` is by
// construction a hub that already redacts, and its sentence is safe to show; a hub that answers
// `error` is one from BEFORE that gate, whose bucket carried the driver's own words. Hence `other`
// steps aside and `error` keeps the plumbing sentence.

/** The line `error_payload` sends when it redacts — pinned here, and against the Rust below. */
const RUNTIME_REDACTED_LINE = 'the request could not be completed — the hub recorded the details';

test('hub#1337: an authored `other` reaches the reader — the runtime already decided it may', () => {
  const failure = { code: 'other', message: 'usuario no encontrado' };

  assert.equal(
    platformFailureMessage(failure, 'es'),
    null,
    'stepping aside is what lets the caller keep the sentence `may_reach_the_client` let through',
  );
});

test('hub#1337: the till reads the authored sentence, not the generic one', async () => {
  const transport = transportWith({ code: 'other', message: 'usuario no encontrado' });

  await assert.rejects(
    () => transport.command('hub.users.set_pin', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'other');
      assert.equal(e.message, 'usuario no encontrado');
      return true;
    },
  );
});

test('hub#1337: a REDACTED `other` still speaks the language of whoever is reading', () => {
  // `carries_driver_text` fired, so the sentence on the wire is the runtime's fixed ENGLISH line
  // written for the log. Leaving it alone would put it on a Spanish till — hub#1102 all over again.
  const es = platformFailureMessage({ code: 'other', message: RUNTIME_REDACTED_LINE }, 'es');

  assert.ok(es);
  assert.doesNotMatch(es!, /could not be completed/, 'the log line never reaches a counter');
  assert.match(es!, /No se pudo/);
});

test('hub#1337: an `other` with nothing to say keeps the plumbing sentence', () => {
  // An older runtime, or a caller that only carries the code: «unknown error» says less.
  assert.ok(platformFailureMessage({ code: 'other' }, 'es'));
  assert.ok(platformFailureMessage({ code: 'other', message: '   ' }, 'es'));
});

test('hub#1337: `error` stays plumbing — the hubs that answer it are the ones that never redacted', () => {
  const es = platformFailureMessage(
    { code: 'error', message: 'sqlx: error returned from database' },
    'es',
  );

  assert.ok(es);
  assert.doesNotMatch(es!, /sqlx/, 'the pre-hub#1074 bucket is what put driver text on a till');
});

/**
 * The `REDACTED_MESSAGE` literal a Rust source declares, or `null` when it declares none.
 *
 * `\s` and not a space, and that is the whole point (hub#1337). `rustfmt` puts the literal on its
 * OWN line whenever the declaration does not fit in 100 columns — which is exactly what
 * `dispatch_api.rs` looks like today:
 *
 * ```rust
 * pub(crate) const REDACTED_MESSAGE: &str =
 *     "the request could not be completed — the hub recorded the details";
 * ```
 *
 * A pattern that demanded `= "…";` on the same line found ZERO there and the guard below went red
 * with «found 0 (none)» — not because the constant was gone, but because a line got wrapped. That
 * is the same class of brittleness the hard-coded path had: a control that stops finding the
 * positive stops being a control. Lifetimes (`&'static str`) and escaped quotes are tolerated for
 * the same reason.
 */
function redactedLineIn(source: string): string | null {
  const found = source.match(
    /const\s+REDACTED_MESSAGE\s*:\s*&\s*(?:'\w+\s+)?str\s*=\s*"((?:[^"\\]|\\.)*)"\s*;/,
  );
  return found ? found[1]! : null;
}

test('hub#1337: the guard reads the constant however `rustfmt` lays it out', () => {
  // The shape `crates/server/src/dispatch_api.rs` HAS — the one that made this guard find zero.
  assert.equal(
    redactedLineIn('pub(crate) const REDACTED_MESSAGE: &str =\n    "wrapped by rustfmt";\n'),
    'wrapped by rustfmt',
  );
  // And the shape it had before the line grew past 100 columns, which must keep working.
  assert.equal(
    redactedLineIn('const REDACTED_MESSAGE: &str = "on one line";'),
    'on one line',
  );
  // A lifetime is still a plain `&str` literal.
  assert.equal(
    redactedLineIn("pub const REDACTED_MESSAGE: &'static str = \"with a lifetime\";"),
    'with a lifetime',
  );

  // POSITIVE CONTROLS — the reason this helper is tested at all is that a finder which never
  // fails is indistinguishable from one that never looks.
  assert.equal(redactedLineIn('fn main() {}'), null, 'no declaration is no match');
  assert.equal(
    redactedLineIn('const REDACTED_MESSAGE: String = String::new();'),
    null,
    'it is not a plain `&str` literal any more, and the guard must say so',
  );
  assert.equal(
    redactedLineIn('const REDACTED_MESSAGE_PREFIX: &str = "not this one";'),
    null,
    'a different constant whose name merely starts the same is not the one the door sends',
  );
});

test('hub#1337: the redaction line this table recognises is the one `crates/server` sends', () => {
  // The guard under the rule above: `other` is told apart from a redaction by ONE constant, and a
  // constant mirrored across two languages drifts unless something compares them. Same shape as
  // `contract:check` — the copy is checked against the source, not trusted.
  //
  // The source file is FOUND, never pinned. hub#1418 split `crates/server/src/lib.rs` and carried
  // `REDACTED_MESSAGE` over to `dispatch_api.rs`; a hard-coded path turned this guard into a red
  // that rode on every push of the web stage instead of a check that reads the constant. So walk
  // `crates/server/src/` and demand EXACTLY ONE declaration: zero means the constant is gone or is
  // no longer a plain `&str` literal, and two means a split left divergent copies, with neither
  // this table nor the reader knowing which one the door actually sends.
  const srcRoot = fileURLToPath(new URL('../../../crates/server/src/', import.meta.url));
  const declared = readdirSync(srcRoot, { recursive: true, encoding: 'utf8' })
    .filter((entry) => entry.endsWith('.rs'))
    .sort()
    .flatMap((entry) => {
      const found = redactedLineIn(readFileSync(join(srcRoot, entry), 'utf8'));
      return found === null ? [] : [{ file: entry, line: found }];
    });

  assert.equal(
    declared.length,
    1,
    'expected exactly ONE `const REDACTED_MESSAGE: &str = "…";` under `crates/server/src/`, found ' +
      `${declared.length} (${declared.map((d) => d.file).join(', ') || 'none'}): ` +
      'hub#1337 tells an authored `other` from a redacted one by comparing against it',
  );
  assert.equal(
    declared[0]!.line,
    RUNTIME_REDACTED_LINE,
    'the runtime changed its redaction line and `PLATFORM_FAILURES.other` would start showing it ' +
      'raw, in English, on a Spanish till',
  );
});
