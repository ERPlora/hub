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
import type { PlatformFailure } from './index.ts';

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

// hub#2428: a module action too big for the hub's instruction budget (moving a very long series of
// appointments, say) is rolled back whole. The receptionist used to read the same line as for a
// crash — «could not complete the operation, try again» — and repeated the same click. Its own code
// gets its own sentence: it is not a crash, nothing changed, and trying again as-is will not help.
test('hub#2428: an action over the hub budget is told apart from a crash, in both languages', async () => {
  const transport = transportWith({ code: 'wasm_budget_exceeded', message: RUNTIME_REDACTED_LINE_2428 });

  await assert.rejects(
    () => transport.command('appointments.recurring.update', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'wasm_budget_exceeded', 'the code is what a module branches on');
      assert.notEqual(e.message, RUNTIME_REDACTED_LINE_2428, 'never the English line aimed at the log');
      return true;
    },
  );

  for (const locale of ['es', 'en'] as const) {
    const budget = platformFailureMessage({ code: 'wasm_budget_exceeded' }, locale);
    const crash = platformFailureMessage({ code: 'wasm' }, locale);
    assert.ok(budget, `no ${locale} sentence for wasm_budget_exceeded`);
    assert.notEqual(budget, crash, `${locale}: «too big, nothing changed» is not «it broke, try again»`);
  }
  assert.notEqual(
    platformFailureMessage({ code: 'wasm_budget_exceeded' }, 'en'),
    platformFailureMessage({ code: 'wasm_budget_exceeded' }, 'es'),
    'en is the source and es the translation (ADR-0055), not one string',
  );
});

// hub#2431: the sibling of hub#2428 — an action that takes longer than the hub's clock allows (a
// huge batch on a slow machine) is cut and rolled back whole. The screen used to say «could not
// complete the operation, try again», and trying again repeated the same click and the same cut. Its
// own code gets its own sentence: not a crash, nothing changed, and asking for less is what helps.
test('hub#2431: an action over the hub time limit is told apart from a crash, in both languages', async () => {
  const transport = transportWith({ code: 'wasm_timeout', message: RUNTIME_REDACTED_LINE_2428 });

  await assert.rejects(
    () => transport.command('appointments.recurring.update', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'wasm_timeout', 'the code is what a module branches on');
      assert.notEqual(e.message, RUNTIME_REDACTED_LINE_2428, 'never the English line aimed at the log');
      return true;
    },
  );

  for (const locale of ['es', 'en'] as const) {
    const timeout = platformFailureMessage({ code: 'wasm_timeout' }, locale);
    const crash = platformFailureMessage({ code: 'wasm' }, locale);
    const budget = platformFailureMessage({ code: 'wasm_budget_exceeded' }, locale);
    assert.ok(timeout, `no ${locale} sentence for wasm_timeout`);
    assert.notEqual(timeout, crash, `${locale}: «took too long, nothing changed» is not «it broke, try again»`);
    assert.notEqual(timeout, budget, `${locale}: «took too long» is not «too big» — the person reads what happened`);
  }
  assert.notEqual(
    platformFailureMessage({ code: 'wasm_timeout' }, 'en'),
    platformFailureMessage({ code: 'wasm_timeout' }, 'es'),
    'en is the source and es the translation (ADR-0055), not one string',
  );
});

/** The redacted line the runtime sends beside the code (`REDACTED_MESSAGE`, pinned further down). */
const RUNTIME_REDACTED_LINE_2428 = 'the request could not be completed — the hub recorded the details';

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
    // hub#2428: a handler out of its instruction budget, redacted like `wasm` but with its own code.
    'wasm_budget_exceeded',
    // hub#2431: a handler over its time limit, redacted like `wasm` but with its own code.
    'wasm_timeout',
    'module_not_installed', 'module_inactive', 'missing_dependency', 'read_unavailable',
    // hub#2434: the fiscal precondition — its `Display` is a log line with the setting keys in it.
    'fiscal_precondition_failed',
    // hub#2383: a query asked without a value it needs — its `Display` is an English line for the
    // log and the assistant, with the query and the bind in backticks.
    'missing_required_param',
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

/** What the envelope carries: `message` travels on the wire but is not part of the public PlatformFailure. */
const onWire = (f: PlatformFailure & { message?: string }): PlatformFailure => f;

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
  const es = platformFailureMessage(onWire({ code: 'other', message: RUNTIME_REDACTED_LINE }), 'es');

  assert.ok(es);
  assert.doesNotMatch(es!, /could not be completed/, 'the log line never reaches a counter');
  assert.match(es!, /No se pudo/);
});

test('hub#1337: an `other` with nothing to say keeps the plumbing sentence', () => {
  // An older runtime, or a caller that only carries the code: «unknown error» says less.
  assert.ok(platformFailureMessage({ code: 'other' }, 'es'));
  assert.ok(platformFailureMessage(onWire({ code: 'other', message: '   ' }), 'es'));
});

test('hub#1337: `error` stays plumbing — the hubs that answer it are the ones that never redacted', () => {
  const es = platformFailureMessage(
    onWire({ code: 'error', message: 'sqlx: error returned from database' }),
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

// ── hub#2428: every code the door REDACTS has a sentence here — read from the Rust, not listed ──
//
// A code the door redacts arrives with nothing but the English line aimed at the log. If this table
// has no entry for it, `unwrap` keeps that line and a Spanish till reads it raw — hub#1102's bug,
// again. hub#2428 added such a code (`wasm_budget_exceeded`); the hand-kept list above only catches
// it if whoever adds the code also remembers the list. This one reads the two Rust tables instead:
// the variants `may_reach_the_client` sends to the `false` side, and the code `error_code_of` gives
// each of them.

/** Body of the Rust `fn <name>` in `source`, with line comments stripped, or `''` when absent. */
function rustFnBody(source: string, name: string): string {
  const start = source.search(new RegExp(String.raw`fn\s+${name}\s*\(`));
  if (start < 0) return '';
  const end = source.indexOf('\n}\n', start);
  return source.slice(start, end < 0 ? undefined : end).replace(/\/\/[^\n]*/g, '');
}

/** The stable codes of the variants `may_reach_the_client` redacts (its `=> false` arms). */
function redactedCodesIn(doorSource: string, registrySource: string): string[] {
  const door = rustFnBody(doorSource, 'may_reach_the_client');
  const registry = rustFnBody(registrySource, 'error_code_of');
  const codeOf = new Map<string, string>();
  for (const [, variant, code] of registry.matchAll(/E::(\w+)\b[^\n]*?=>\s*"([a-z_]+)"/g)) {
    codeOf.set(variant!, code!);
  }
  const redacted: string[] = [];
  for (const [, arm, side] of door.matchAll(
    /((?:\s*\|?\s*E::\w+(?:\s*\{\s*\.\.\s*\}|\s*\([^)]*\))?)+)\s*=>\s*\{?\s*(true|false)/g,
  )) {
    if (side !== 'false') continue;
    for (const [, variant] of arm!.matchAll(/E::(\w+)/g)) {
      redacted.push(codeOf.get(variant!) ?? `<no literal code for ${variant}>`);
    }
  }
  return redacted;
}

/**
 * Redacted variants that never travel through a request, so no screen can ever receive them.
 * `money_unit_ambiguous` (hub#1209) is raised by an ops subcommand and by the boot path only.
 */
const REDACTED_BUT_NEVER_ON_A_REQUEST = new Set(['money_unit_ambiguous']);

test('hub#2428: the redacted-code finder reads the Rust shape, and catches a code with no sentence', () => {
  const door = [
    'pub(crate) fn may_reach_the_client(e: &E) -> bool {',
    '    match e {',
    '        // E::Commented(_) => false',
    '        E::Io(_) | E::Wasm(_) | E::Schema { .. } => {',
    '            false',
    '        }',
    '        E::BrandNew { .. } => false,',
    '        E::Domain { .. } | E::Other(_) => true,',
    '    }',
    '}',
    '',
  ].join('\n');
  const registry = [
    'pub fn error_code_of(err: &E) -> Cow<str> {',
    '    Cow::Borrowed(match err {',
    '        E::Io(_) => "io",',
    '        E::Wasm(_) => "wasm",',
    '        E::Schema { .. } => "schema",',
    '        E::BrandNew { .. } => "brand_new",',
    '        E::Other(_) => "other",',
    '    })',
    '}',
    '',
  ].join('\n');
  assert.deepEqual(redactedCodesIn(door, registry), ['io', 'wasm', 'schema', 'brand_new']);
  // POSITIVE CONTROL: the new code the finder surfaces is exactly what the table misses.
  assert.equal(platformFailureMessage({ code: 'brand_new' }, 'es'), null);
});

test('hub#2428: every code the authenticated door redacts has a sentence here, in both languages', () => {
  const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
  const codes = redactedCodesIn(
    read('../../../crates/server/src/dispatch_api.rs'),
    read('../../../crates/runtime/src/error_registry.rs'),
  );
  // The finder must see the positives it exists for, or a green here means nothing.
  for (const known of ['db', 'wasm', 'wasm_budget_exceeded', 'wasm_timeout']) {
    assert.ok(codes.includes(known), `the finder no longer sees "${known}" (found: ${codes.join(', ')})`);
  }
  for (const code of codes.filter((c) => !REDACTED_BUT_NEVER_ON_A_REQUEST.has(c))) {
    for (const locale of ['es', 'en'] as const) {
      assert.ok(
        platformFailureMessage({ code }, locale),
        `the door redacts "${code}" but PLATFORM_FAILURES has no ${locale} sentence for it: the ` +
          'screen would show the English line written for the log',
      );
    }
  }
});

// ── hub#2410: `read_unavailable` says WHY, and the sentence follows it ──────────────────────────
//
// The kernel aborts a command with `read_unavailable` when the app that owns a `required` read is
// not installed, is switched off, or is there and the read itself failed. The envelope only
// carried the query, so every screen said «the app “taxes” is missing, ask an administrator to
// install it from Apps» — also with `taxes` installed and running and the read failing for a
// moment. The runtime now sends `reason` beside the code; these pin the sentence each one gets.

/** The sentence the same app gets under its OWN code — the reference each reason must match. */
function sentenceFor(code: string, module: string, locale: string): string | null {
  return platformFailureMessage({ code, module }, locale);
}

test('hub#2410: a failed read of an installed app is NOT told as a missing app', async () => {
  const transport = transportWith({
    code: 'read_unavailable',
    message: 'a required read (`sales.get`) could not be resolved, so the command was aborted',
    query: 'sales.get',
    reason: 'query_failed',
  });

  await assert.rejects(
    () => transport.command('invoice.create_from_sale', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'read_unavailable', 'the code a module branches on is untouched');
      assert.notEqual(e.message, sentenceFor('module_not_installed', 'sales', 'es'));
      assert.doesNotMatch(e.message, /Apps/, 'the app is installed: sending the owner to Apps is the bug');
      return true;
    },
  );
  for (const locale of ['es', 'en']) {
    const said = platformFailureMessage(
      { code: 'read_unavailable', query: 'sales.get', reason: 'query_failed' },
      locale,
    );
    assert.ok(said, `a sentence in ${locale}`);
    assert.notEqual(said, sentenceFor('module_not_installed', 'sales', locale));
    assert.notEqual(said, sentenceFor('module_inactive', 'sales', locale));
    assert.doesNotMatch(said!, /Apps|`|undefined/);
  }
  assert.notEqual(
    platformFailureMessage({ code: 'read_unavailable', reason: 'query_failed' }, 'es'),
    platformFailureMessage({ code: 'read_unavailable', reason: 'query_failed' }, 'en'),
    'es is a translation, not the English source again',
  );
});

test('hub#2410: an owner that is switched off gets the «switch it back on» sentence, not «install it»', () => {
  for (const locale of ['es', 'en']) {
    assert.equal(
      platformFailureMessage(
        { code: 'read_unavailable', query: 'taxes.rules.list', reason: 'module_inactive' },
        locale,
      ),
      sentenceFor('module_inactive', 'taxes', locale),
    );
  }
});

test('hub#2410: an owner that is not installed keeps the «install it» sentence', () => {
  for (const locale of ['es', 'en']) {
    assert.equal(
      platformFailureMessage(
        { code: 'read_unavailable', query: 'taxes.rules.list', reason: 'module_not_installed' },
        locale,
      ),
      sentenceFor('module_not_installed', 'taxes', locale),
    );
  }
});

test('hub#2410: a runtime that sends no reason (or one this SDK does not know) keeps today’s sentence', () => {
  for (const reason of [undefined, 'something_newer']) {
    for (const locale of ['es', 'en']) {
      assert.equal(
        platformFailureMessage({ code: 'read_unavailable', query: 'taxes.rules.list', reason }, locale),
        sentenceFor('module_not_installed', 'taxes', locale),
        `reason ${String(reason)} (${locale})`,
      );
    }
  }
});

// ── hub#2434: the fiscal precondition says WHAT is missing and WHERE it is filled in ────────────
//
// A business without its legal name and tax id tried to issue an invoice. Refusing is right
// (ADR-0203), but the screen, in Spanish, painted the runtime's log line verbatim: «fiscal
// precondition failed: configure business_legal_name, business_tax_id before issuing fiscal
// documents». The runtime now sends WHAT is missing as data (`missing`, beside the code) and this
// table turns it into the business words and the place to fix it, in the reader's language.

/** The log line the runtime keeps sending as `message` (its `Display`), for older SDKs. */
const FISCAL_LOG_LINE =
  'fiscal precondition failed: configure business_legal_name, business_tax_id before issuing fiscal documents';

/** A precondition refusal as the wire carries it: `missing` is data on the envelope. */
const fiscalRefusal = (missing?: string[]): PlatformFailure =>
  ({ code: 'fiscal_precondition_failed', message: FISCAL_LOG_LINE, ...(missing ? { missing } : {}) }) as PlatformFailure;

/** What an internal name looks like on a screen: never acceptable in front of a person. The
 *  bare key `certificate` is not listed: in English it is also the word a person reads. */
const INTERNAL_WORDS = /business_|fiscal precondition|fiscal documents/;

test('hub#2434: the till reads what is missing in its language, never the log line', async () => {
  const transport = transportWith({
    code: 'fiscal_precondition_failed',
    message: FISCAL_LOG_LINE,
    missing: ['business_legal_name', 'business_tax_id'],
  });

  await assert.rejects(
    () => transport.command('invoice.invoice.create', {}),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'fiscal_precondition_failed', 'the code is what a module branches on');
      assert.notEqual(e.message, FISCAL_LOG_LINE, 'never the English line written for the log');
      assert.doesNotMatch(e.message, INTERNAL_WORDS);
      return true;
    },
  );

  const es = platformFailureMessage(fiscalRefusal(['business_legal_name', 'business_tax_id']), 'es');
  const en = platformFailureMessage(fiscalRefusal(['business_legal_name', 'business_tax_id']), 'en');
  assert.ok(es && en, 'fiscal_precondition_failed has no sentence');
  assert.notEqual(es, en, 'en is the source and es the translation (ADR-0055), not one string');
  for (const sentence of [es, en]) assert.doesNotMatch(sentence, INTERNAL_WORDS);
  // The acceptance of the issue: the Spanish reader learns WHAT is missing, in the words of the
  // Settings form, and WHERE it is filled in.
  assert.match(es, /razón social/i);
  assert.match(es, /NIF/);
  assert.match(es, /Ajustes › Negocio/);
  // rv-2437: the two halves are joined in the reader's language too — «la razón social y el NIF»,
  // never «la razón social and el NIF». A mixed sentence reads as untranslated.
  assert.match(es, /la razón social y el NIF/);
  assert.match(en, /legal name and tax ID/);
});

test('hub#2434: each missing requirement is named — the sentence follows `missing`', () => {
  const cases = [
    ['business_legal_name'],
    ['business_tax_id'],
    ['certificate'],
    ['business_legal_name', 'business_tax_id'],
    ['business_legal_name', 'business_tax_id', 'certificate'],
  ];
  for (const locale of ['es', 'en'] as const) {
    const sentences = cases.map((missing) => platformFailureMessage(fiscalRefusal(missing), locale));
    for (const sentence of sentences) {
      assert.ok(sentence, `${locale}: no sentence`);
      assert.doesNotMatch(sentence, INTERNAL_WORDS);
      if (locale === 'es') assert.doesNotMatch(sentence, /certificate/, 'the key, not the Spanish word');
    }
    assert.equal(new Set(sentences).size, cases.length, `${locale}: two different gaps read the same: ${sentences.join(' | ')}`);
  }
});

test('hub#2434: an older runtime that sends no `missing` still gets a sentence a person can act on', () => {
  for (const missing of [undefined, [], ['something_newer']]) {
    for (const locale of ['es', 'en'] as const) {
      const sentence = platformFailureMessage(fiscalRefusal(missing), locale);
      assert.ok(sentence, `${locale}: no sentence for missing=${JSON.stringify(missing)}`);
      assert.doesNotMatch(sentence, INTERNAL_WORDS);
      assert.doesNotMatch(sentence, /something_newer/);
    }
  }
});

/** The requirements `enforce_fiscal_precondition` can push, read out of the Rust. */
function fiscalRequirementsIn(commandsSource: string): string[] {
  // Not `rustFnBody`: the gate is generic over a lifetime (`fn enforce_fiscal_precondition<'a>(`).
  const start = commandsSource.search(/fn\s+enforce_fiscal_precondition\s*(<[^>]*>)?\s*\(/);
  if (start < 0) return [];
  const end = commandsSource.indexOf('\n}\n', start);
  const gate = commandsSource.slice(start, end < 0 ? undefined : end)
    .split('\n')
    .filter((line) => !line.trim().startsWith('//'))
    .join('\n');
  return [...gate.matchAll(/missing\.push\(\s*"([a-z_]+)"\s*,?\s*\)/g)].map(([, name]) => name!);
}

test('hub#2434: the requirement finder reads the Rust shape, and catches one with no name', () => {
  const source = [
    'fn enforce_fiscal_precondition<\'a>(registry: &Registry) -> Result<()> {',
    '    let mut missing: Vec<&\'static str> = Vec::new();',
    '    if a {',
    '        missing.push("business_tax_id");',
    '    }',
    '    // missing.push("commented")',
    '    missing.push(',
    '        "brand_new",',
    '    );',
    '    Ok(())',
    '}',
    '',
  ].join('\n');
  assert.deepEqual(fiscalRequirementsIn(source), ['business_tax_id', 'brand_new']);
  // POSITIVE CONTROL: a requirement nobody named reads exactly like «the runtime said nothing».
  assert.equal(
    platformFailureMessage(fiscalRefusal(['brand_new']), 'es'),
    platformFailureMessage(fiscalRefusal([]), 'es'),
  );
});

test('hub#2434: every requirement the fiscal gate can refuse on is named here, in both languages', () => {
  const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
  const requirements = fiscalRequirementsIn(read('../../../crates/runtime/src/commands.rs'));
  for (const known of ['business_legal_name', 'business_tax_id', 'certificate']) {
    assert.ok(requirements.includes(known), `the finder no longer sees "${known}" (found: ${requirements.join(', ')})`);
  }
  for (const requirement of requirements) {
    for (const locale of ['es', 'en'] as const) {
      assert.notEqual(
        platformFailureMessage(fiscalRefusal([requirement]), locale),
        platformFailureMessage(fiscalRefusal([]), locale),
        `the fiscal gate refuses on "${requirement}" but the ${locale} sentence does not name it`,
      );
    }
  }
});

// ── hub#2383: a query asked without a value it needs is not «there is nothing» ─────────────────
//
// The runtime refuses it with `missing_required_param` and names the query and the bind as FIELDS.
// That is for whoever fixes the call; the person at the counter gets a sentence in their language
// that says nothing was looked up, without the internal query name or backticks.
test('hub#2383: `missing_required_param` reads as a sentence, never as the query or the bind', () => {
  for (const locale of ['es', 'en'] as const) {
    const message = platformFailureMessage(
      {
        code: 'missing_required_param',
        query: 'appointments.appointments.get',
        message: 'query `appointments.appointments.get` needs the parameter `:appointment_id`',
      } as PlatformFailure,
      locale,
    );
    assert.ok(message, `no sentence for ${locale}`);
    assert.ok(!message.includes('appointments.'), `${locale}: the internal query name leaked: ${message}`);
    assert.ok(!message.includes('`'), `${locale}: backticks reached the screen: ${message}`);
  }
  assert.notEqual(
    platformFailureMessage({ code: 'missing_required_param' }, 'es'),
    platformFailureMessage({ code: 'missing_required_param' }, 'en'),
    'the Spanish sentence is a translation, not the English one',
  );
});
