// hub#1844 — the DECLARED way a module reads, uploads and removes the business certificate.
//
// hub#1847 put the gate in the runtime: the three doors under `/api/business/certificate` ask a
// caller that names a module for the `certificate` capability granted by the owner
// (`crates/server/tests/certificate_module_gate_hub1844.rs`). What it did NOT do is give module
// code a way in. `coreRequest` is sealed on purpose and the session lives in the shell, so the
// VeriFactu screen reads the session token out of `localStorage` and fetches on its own
// (`ERPlora/verifactu` `ui/lib/core-fetch.ts`) — which breaks the day the session moves to an
// httpOnly cookie, and is the exact seam its own comment says to replace «the day the shell offers
// a real door».
//
// This surface is that door, and these tests are what stop it from becoming a proxy: the method
// list is pinned, every URL it can produce is pinned to one prefix, and the answers are read in the
// envelope the runtime actually writes.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  CERTIFICATE_BASE_PATH,
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  MODULE_HEADER,
  MODULE_SCOPE_REQUIRED,
} from './index.ts';

const SESSION = 's3ss10n-of-a-human-admin';
const VERIFACTU = 'verifactu';

/** What `GET/PUT/DELETE /api/business/certificate` put on the wire: the status, inside `data`. */
const asTheRuntimeAnswers = (status: unknown) => ({ ok: true, data: status });

const NO_CERTIFICATE = {
  present: false,
  slots: { own: { present: false } },
  active: null,
  transmission_route: 'delegated',
};

const UPLOADED = {
  present: true,
  uploaded_at: '2026-09-13T08:00:00Z',
  uploaded_by: 'hub_user:1',
  slots: {
    own: { present: true, uploaded_at: '2026-09-13T08:00:00Z', uploaded_by: 'hub_user:1' },
  },
  active: 'own',
  transmission_route: 'own',
};

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

/** A client scoped to VeriFactu, over a fetch that records every call and answers `answer`. */
function scoped(answer: unknown = asTheRuntimeAnswers(NO_CERTIFICATE)): {
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
    // Exactly what `apps/web/src/lib/runtime.ts` injects: the shell owns the credential.
    headers: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': SESSION }),
  });
  return { client: new ErploraClient(transport).forModule(VERIFACTU), calls };
}

test('hub#1844: reading the certificate carries the shell session — the module never touches the token', async () => {
  const { client, calls } = scoped(asTheRuntimeAnswers(UPLOADED));

  const status = await client.certificate.get();

  assert.deepEqual(status, UPLOADED);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `http://hub${CERTIFICATE_BASE_PATH}`);
  assert.equal(calls[0].method, 'GET');
  assert.equal(
    calls[0].headers['X-Hub-Session'],
    SESSION,
    'the session travels because the SHELL put it there, not because the module read it',
  );
  assert.equal(
    calls[0].headers[MODULE_HEADER],
    VERIFACTU,
    'the call names the module it acts for: that is what the `certificate` capability gate reads',
  );
});

test('hub#1844: an unscoped client has NO certificate surface — naming yourself is not optional', () => {
  const client = new ErploraClient(new HttpWsTransport({ baseUrl: '' }));
  assert.throws(
    () => client.certificate,
    (e: unknown) => e instanceof ErploraError && e.code === MODULE_SCOPE_REQUIRED,
    'the certificate is reachable only through `forModule(<id>)`',
  );
});

test('hub#1844: the surface is THREE methods and nothing else, all under one prefix', async () => {
  const { client, calls } = scoped();
  const certificate = client.certificate;

  // The method LIST is pinned: a `request(path)` or any other escape hatch turns this red.
  const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(certificate))
    .filter((n) => n !== 'constructor')
    .sort();
  assert.deepEqual(methods, ['get', 'put', 'remove']);

  await certificate.get();
  await certificate.put({ pkcs12Base64: 'MIIK', password: 's3cret' });
  await certificate.remove();

  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url.replace('http://hub', '')}`),
    [`GET ${CERTIFICATE_BASE_PATH}`, `PUT ${CERTIFICATE_BASE_PATH}`, `DELETE ${CERTIFICATE_BASE_PATH}`],
  );
  for (const call of calls) {
    assert.equal(call.headers[MODULE_HEADER], VERIFACTU);
  }
});

test('hub#1844: an upload reaches the runtime in the body its door reads — and in nothing else', async () => {
  const { client, calls } = scoped(asTheRuntimeAnswers(UPLOADED));

  const status = await client.certificate.put({ pkcs12Base64: 'MIIK', password: 's3cret' });

  // `put_business_certificate` reads exactly these two keys (`crates/server/src/settings.rs`); a
  // body with any other name arrives as `invalid_field` and the owner's upload is lost.
  assert.deepEqual(calls[0].body, { pkcs12_b64: 'MIIK', password: 's3cret' });
  assert.deepEqual(status, UPLOADED, 'the answer is the state the certificate is left in');
});

test('hub#1844: removing answers the state it leaves — the delegated road the hub falls back to', async () => {
  const { client } = scoped(asTheRuntimeAnswers(NO_CERTIFICATE));

  const status = await client.certificate.remove();

  assert.deepEqual(status, NO_CERTIFICATE);
});

test('hub#1844: a refusal arrives with its code, so the screen can ask for the grant instead of «error»', async () => {
  const fetchImpl = (async () => ({
    status: 403,
    headers: { get: () => 'application/json' },
    json: async () => ({
      ok: false,
      error: {
        code: 'capability_denied',
        module: VERIFACTU,
        message: 'el módulo `verifactu` no tiene la capability `certificate`',
      },
    }),
  })) as unknown as typeof fetch;
  const client = new ErploraClient(
    new HttpWsTransport({ baseUrl: 'http://hub', fetchImpl }),
  ).forModule(VERIFACTU);

  await assert.rejects(
    () => client.certificate.remove(),
    (e: unknown) => e instanceof ErploraError && e.code === 'capability_denied',
  );
});

// Same shape as hub#1530 for the printer: a surface inherited through a re-scope would keep
// stamping the PREVIOUS module's header, and the second module would delete the business
// certificate under the grant the owner gave to the first.
test('hub#1844: a client scoped again acts as the NEW module — the previous grant does not travel', async () => {
  const granted = VERIFACTU;
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    const acting = (init.headers as Record<string, string>)[MODULE_HEADER];
    const ok = acting === granted;
    return {
      status: ok ? 200 : 403,
      headers: { get: () => 'application/json' },
      json: async () =>
        ok
          ? asTheRuntimeAnswers(NO_CERTIFICATE)
          : { ok: false, error: { code: 'capability_denied', module: acting, message: 'denied' } },
    };
  }) as unknown as typeof fetch;

  const base = new ErploraClient(new HttpWsTransport({ baseUrl: 'http://hub', fetchImpl }));
  const verifactu = base.forModule(granted);
  await verifactu.certificate.get();

  const inventory = verifactu.forModule('inventory');
  await assert.rejects(
    () => inventory.certificate.remove(),
    (e: unknown) => e instanceof ErploraError && e.code === 'capability_denied',
    'the module that did NOT get the grant must be refused, whichever scope it was built from',
  );
});

// Every fixture above is a claim about a server written in another language. Compare it: the three
// doors answer through `enveloped`, and the upload reads `pkcs12_b64` and `password`.
test('hub#1844: the envelope and the body these fixtures simulate are the ones `crates/server` writes', () => {
  const rust = readFileSync(
    fileURLToPath(new URL('../../../crates/server/src/settings.rs', import.meta.url)),
    'utf8',
  ).replace(/\s+/g, ' ');

  assert.ok(
    rust.includes('fn enveloped<T: serde::Serialize>(data: T) -> Response { Json(json!({ "ok": true, "data": data })).into_response() }'),
    'the certificate doors no longer answer `{ok, data}`, so these fixtures describe a server that does not exist',
  );
  for (const key of ['.get("pkcs12_b64")', '.get("password")']) {
    assert.ok(rust.includes(key), `the upload door no longer reads \`${key}\``);
  }
  const answers = rust.match(/Ok\(s\) => enveloped\(s\)/g) ?? [];
  assert.ok(
    answers.length >= 3,
    `expected GET, PUT and DELETE to answer through \`enveloped\`, found ${answers.length}`,
  );
});
