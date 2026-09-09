// hub#1682 — the DECLARED way a module registers, lists and deletes the templates its business
// promises Meta.
//
// hub#1610 put the three doors in the runtime (`crates/server/src/whatsapp_templates.rs`): the hub
// proxies them to the SaaS with the machine credential, because the Meta token never leaves the
// SaaS (ADR-0012) and the credential that opens that door never reaches the browser (ADR-0003).
// What it did NOT do is give module code a way in — and there was none by accident either:
// `coreRequest` is sealed on purpose (`index.ts`, «it is not reachable from module code»), and the
// session travels in `X-Hub-Session`, which the shell holds. So the WhatsApp module's «Plantillas»
// tab could save a template and nothing else: Meta never saw it, never approved it, and the
// business could not send a single reminder outside the 24 h window.
//
// This surface is the transport, and these tests are what stop it from becoming a proxy: the
// method list is pinned, every URL it can produce is pinned to one prefix, and a template name
// that would climb out of that prefix is refused before a request exists.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  MODULE_HEADER,
  MODULE_SCOPE_REQUIRED,
  WHATSAPP_TEMPLATES_BASE_PATH,
} from './index.ts';

const SESSION = 's3ss10n-of-a-human-admin';
const WHATSAPP = 'whatsapp_inbox';

// ── What the RUNTIME puts on the wire (hub#1688) ───────────────────────────────────────────────
//
// These two helpers are the whole reason this file can be trusted. Until hub#1688 the fixtures
// here were `{ ok: true, data: … }` written by hand, and the runtime answered the SaaS's PLAIN
// body — so every test was green while every real call threw `unknown error`. A test that
// simulates a server nobody wrote proves the client talks to itself.
//
// The runtime now wraps these three doors like every other door module code reaches
// (`cloud_proxy::cloud_envelope_passthrough`), and the shape below is copied FROM it — with the
// guard at the bottom of this file comparing the copy against the Rust, the same mechanism
// `platform-failure.test.ts` uses for the redaction line.

/** The SaaS's payload, as the runtime hands it to a module: whole, inside `data`. */
const asTheRuntimeAnswers = (saasBody: unknown) => ({ ok: true, data: saasBody });

/** A refusal, as the runtime hands it over: the SaaS's own `code`, never flattened to prose. */
const asTheRuntimeRefuses = (code: string, message: string) => ({
  ok: false,
  error: { code, message },
});

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

/** A client scoped to the WhatsApp module, over a fetch that records and always says `ok`. */
function scoped(answer: unknown = asTheRuntimeAnswers({})): {
  client: ErploraClient;
  calls: Call[];
} {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({
      url,
      method: String(init.method),
      headers: init.headers as Record<string, string>,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    });
    return { status: 200, headers: { get: () => 'application/json' }, json: async () => answer };
  }) as unknown as typeof fetch;
  const transport = new HttpWsTransport({
    baseUrl: 'http://hub',
    fetchImpl,
    // Exactly what `apps/web/src/lib/runtime.ts` injects: the shell owns the credential and the
    // module never sees it. That is the entire point of routing through the SDK.
    headers: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': SESSION }),
  });
  return { client: new ErploraClient(transport).forModule(WHATSAPP), calls };
}

test('hub#1682: the template surface carries the shell session — the module never touches the token', async () => {
  const { client, calls } = scoped(
    asTheRuntimeAnswers({ templates: [{ name: 'table_ready', status: 'PENDING' }], stale: false }),
  );

  const result = await client.whatsappTemplates.list();

  assert.deepEqual(result, { templates: [{ name: 'table_ready', status: 'PENDING' }], stale: false });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `http://hub${WHATSAPP_TEMPLATES_BASE_PATH}`);
  assert.equal(calls[0].method, 'GET');
  assert.equal(
    calls[0].headers['X-Hub-Session'],
    SESSION,
    'the session travels because the SHELL put it there, not because the module read it',
  );
  assert.equal(
    calls[0].headers[MODULE_HEADER],
    WHATSAPP,
    'the call names the module it acts for: that is what the `notify` capability gate reads',
  );
});

test('hub#1682: an unscoped client has NO template surface — naming yourself is not optional', () => {
  const client = new ErploraClient(new HttpWsTransport({ baseUrl: '' }));
  assert.throws(
    () => client.whatsappTemplates,
    (e: unknown) => e instanceof ErploraError && e.code === MODULE_SCOPE_REQUIRED,
    'the templates are reachable only through `forModule(<id>)`',
  );
});

test('hub#1682: the surface is THREE methods and nothing else', async () => {
  const { client, calls } = scoped();
  const templates = client.whatsappTemplates;

  // 1. The method LIST is pinned. Adding `request(path)`, `fetch(url)` or any other escape hatch
  //    turns this red — the only mechanical way to keep the surface from silently becoming a
  //    generic proxy to the core.
  const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(templates))
    .filter((n) => n !== 'constructor')
    .sort();
  assert.deepEqual(methods, ['list', 'register', 'remove']);

  // 2. Every URL the surface can produce lands under ONE prefix.
  await templates.list();
  await templates.register({ name: 'table_ready', language: 'es', category: 'UTILITY' });
  await templates.remove('table_ready');

  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url.replace('http://hub', '')}`),
    [
      `GET ${WHATSAPP_TEMPLATES_BASE_PATH}`,
      `POST ${WHATSAPP_TEMPLATES_BASE_PATH}`,
      `DELETE ${WHATSAPP_TEMPLATES_BASE_PATH}/table_ready`,
    ],
  );
  for (const call of calls) {
    assert.ok(
      call.url.startsWith(`http://hub${WHATSAPP_TEMPLATES_BASE_PATH}`),
      `the surface must never leave its prefix: ${call.url}`,
    );
    assert.equal(call.headers[MODULE_HEADER], WHATSAPP);
  }

  // 3. The template the business wrote reaches the SaaS VERBATIM: every rule about what Meta will
  //    accept lives there (`crates/server/src/whatsapp_templates.rs`), so a surface that reshaped
  //    the body would refuse templates Meta would have taken.
  assert.deepEqual(calls[1].body, {
    name: 'table_ready',
    language: 'es',
    category: 'UTILITY',
  });
});

test('hub#1682: a template name that would climb out of the prefix never leaves the process', async () => {
  const { client, calls } = scoped();
  const templates = client.whatsappTemplates;

  // `fetch` NORMALISES the URL: `/api/hub/whatsapp/templates/../../settings` is sent as
  // `/api/hub/settings`. So a name pasted into a path is not a cosmetic problem — it is the generic
  // proxy, arriving by the back door. The runtime refuses these too (`template_name_is_safe`,
  // hub#1610), and that stays the door that counts; this is the half that never builds the URL.
  const escapes = [
    '..',
    '../numbers',
    'a/b',
    '%2e%2e%2f',
    'table_ready?x=1',
    'table_ready#frag',
    '',
    ' ',
    'Table_Ready',
    'table-ready',
    'table.ready',
    'a'.repeat(513),
  ];
  for (const bad of escapes) {
    await assert.rejects(
      () => templates.remove(bad),
      (e: unknown) => e instanceof ErploraError && e.code === 'invalid_argument',
      `\`${bad}\` must be refused as a template name`,
    );
  }
  assert.equal(calls.length, 0, 'not one of them may reach `fetch`');
});

// ── The 204 the delete answers with ────────────────────────────────────────────────────────────
//
// A body-less success needs no envelope and gets none: `cloud_envelope_passthrough` returns the
// status alone when the SaaS answered empty, and the SaaS answers a delete `204 No Content`:
// empty body, NO `content-type`. `HttpWsTransport.send` used to
// call `res.json()` on everything, so a delete that WORKED came back as
// `server_unavailable: invalid JSON body` — the tab would tell the owner the hub did not answer
// while Meta had already dropped the template. This is the failure that surface would ship with,
// so it is asserted here and not left to the module to discover.
test('hub#1682: a delete that answers 204 resolves — a body-less success is not a failure', async () => {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({
      url,
      method: String(init.method),
      headers: init.headers as Record<string, string>,
      body: undefined,
    });
    return {
      status: 204,
      // No `content-type` at all, which is what a 204 carries.
      headers: { get: () => null },
      json: async () => {
        throw new SyntaxError('Unexpected end of JSON input');
      },
    };
  }) as unknown as typeof fetch;
  const client = new ErploraClient(
    new HttpWsTransport({
      baseUrl: 'http://hub',
      fetchImpl,
      headers: () => ({ 'X-Hub-Session': SESSION }),
    }),
  ).forModule(WHATSAPP);

  const result = await client.whatsappTemplates.remove('table_ready');

  assert.equal(result, undefined, 'a 204 says «done», and there is nothing else to say');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'DELETE');
});

// ── The grant belongs to the module that MAKES the request ─────────────────────────────────────
//
// Same shape as hub#1530 for the printer: `forModule` builds the scope with `Object.create(this)`,
// so a client scoped again inherits every memoised surface of the scope it came from — and each
// surface captured its module's header when it was built. A surface inherited that way would keep
// stamping the PREVIOUS module, and the second module would act under the grant the owner gave to
// the first. Here that would mean one module deleting the business's approved templates under
// another's `notify`.
test('hub#1682: a client scoped again acts as the NEW module — the previous grant does not travel', async () => {
  const granted = WHATSAPP;
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    const headers = init.headers as Record<string, string>;
    calls.push({ url, method: String(init.method), headers, body: undefined });
    const acting = headers[MODULE_HEADER];
    const ok = acting === granted;
    return {
      status: ok ? 200 : 403,
      headers: { get: () => 'application/json' },
      json: async () =>
        ok
          ? asTheRuntimeAnswers({ templates: [], stale: false })
          : {
              // The runtime's OWN refusal — same envelope, plus the `module` the kernel names.
              ok: false,
              error: {
                code: 'capability_denied',
                module: acting,
                message: `el módulo \`${acting}\` no tiene la capability \`notify\``,
              },
            },
    };
  }) as unknown as typeof fetch;

  const base = new ErploraClient(new HttpWsTransport({ baseUrl: 'http://hub', fetchImpl }));
  const whatsapp = base.forModule(granted);
  await whatsapp.whatsappTemplates.list();

  const inventory = whatsapp.forModule('inventory');
  await assert.rejects(
    () => inventory.whatsappTemplates.list(),
    (e: unknown) => e instanceof ErploraError && e.code === 'capability_denied',
    'the module that did NOT get the grant must be refused, whichever scope it was built from',
  );
});

// ── The refusal reaches the module WITH ITS CODE (hub#1688) ────────────────────────────────────
//
// The other half of the failure. When Meta says no, the SaaS says WHY as a `code` — `invalid_name`,
// `missing_example`, `meta_rate_limited` — never as prose, precisely so the module can put the
// sentence in the owner's language (ADR-0055, saas#1902). Handed the SaaS's plain
// `{"error": "invalid_name"}`, `unwrap` found no `ok` and threw `error: unknown error`: the owner
// was told «error desconocido» about a name they could have fixed in two seconds.
test('hub#1688: a refusal from Meta arrives with its code, which is what lets the tab say WHY', async () => {
  const refusal = asTheRuntimeRefuses('invalid_name', 'lowercase letters, digits and underscores only');
  const fetchImpl = (async () => ({
    status: 400,
    headers: { get: () => 'application/json' },
    json: async () => refusal,
  })) as unknown as typeof fetch;
  const client = new ErploraClient(
    new HttpWsTransport({ baseUrl: 'http://hub', fetchImpl }),
  ).forModule(WHATSAPP);

  await assert.rejects(
    () =>
      client.whatsappTemplates.register({
        name: 'Table Ready',
        language: 'es',
        category: 'UTILITY',
      }),
    (e: unknown) => {
      assert.ok(e instanceof ErploraError);
      assert.equal(e.code, 'invalid_name', 'the code is the contract, not the sentence');
      assert.equal(e.message, 'lowercase letters, digits and underscores only');
      return true;
    },
  );
});

test('hub#1688: a template Meta ACCEPTED resolves — the answer is not an error', async () => {
  // The symptom the business saw: saving worked, Meta had it, and the tab said «error».
  const { client } = scoped(
    asTheRuntimeAnswers({ name: 'table_ready', language: 'es', status: 'PENDING' }),
  );

  const saved = await client.whatsappTemplates.register({
    name: 'table_ready',
    language: 'es',
    category: 'UTILITY',
  });

  assert.deepEqual(saved, { name: 'table_ready', language: 'es', status: 'PENDING' });
});

// ── The guard that would have caught hub#1682 ──────────────────────────────────────────────────
//
// Every fixture above is a claim about a server written in another language, and the whole reason
// this file could be green while nothing worked is that nobody compared the claim to the server.
// So compare it. Same mechanism as `platform-failure.test.ts` for the redaction line, and the same
// rule: the source file is FOUND, never pinned, because a hard-coded path turns a guard into a red
// that rides on every push instead of a check that reads the code.
test('hub#1688: the envelope these fixtures simulate is the one `crates/server` actually writes', () => {
  const srcRoot = fileURLToPath(new URL('../../../crates/server/src/', import.meta.url));
  const declaring = readdirSync(srcRoot, { recursive: true, encoding: 'utf8' })
    .filter((entry) => typeof entry === 'string' && entry.endsWith('.rs'))
    .sort()
    .map((entry) => ({ file: entry, text: readFileSync(join(srcRoot, entry), 'utf8') }))
    // The `(` is load-bearing: without it a rename to `cloud_envelope_passthrough_renamed`
    // still matches by prefix and this guard passes over a server that no longer exists
    // (measured — that mutant survived until the paren went in).
    .filter(({ text }) => text.includes('fn cloud_envelope_passthrough('));

  assert.equal(
    declaring.length,
    1,
    'expected exactly ONE `cloud_envelope_passthrough` under `crates/server/src/`, found ' +
      `${declaring.length} (${declaring.map((d) => d.file).join(', ') || 'none'}): it is the ` +
      'function that decides what these three doors put on the wire',
  );

  // Whitespace-insensitive: `cargo fmt` reflows arguments and that is not a contract change.
  const rust = declaring[0]!.text.replace(/\s+/g, ' ');
  for (const written of [
    'json!({ "ok": true, "data": data })',
    'json!({ "ok": false, "error": { "code": code, "message": message } })',
  ]) {
    assert.ok(
      rust.includes(written),
      `the runtime no longer writes \`${written}\`, so the fixtures in this file describe a ` +
        'server that does not exist — which is exactly how hub#1682 shipped three doors that ' +
        'threw `unknown error` on every call with the suite green',
    );
  }
});
