// hub#2281 — a failure with nothing to say must still say something a person can act on.
//
// The incident: in Kitchen › Stations, creating a station with the session running out left the
// list on «No stations.» and a red banner reading, literally, «unknown error» — English, on a
// Spanish hub, and silent about what to do next. That phrase was `unwrap`'s last resort, and every
// module that shows `e.message` (nearly all of them) could print it.
//
// The cause was one door away: `/api/query` and `/api/command` refuse a dead session with
// `401 {"ok": false, "error": "no autenticado: …"}` (`dispatch_api::unauthorized`) — the error is
// a bare STRING, so there was no `code` to branch on and no `message` to keep. Two rules now hold:
//
//   1. a 401 that is about the session (no code, or the runtime's own `unauthorized`) is told as
//      what it is — the session ended, sign in again — under the stable code `unauthorized`;
//   2. when nothing better is known, the sentence is the translated platform one («could not be
//      completed, try again…»), never a raw phrase.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ErploraError, HttpWsTransport, platformFailureMessage } from './index.ts';

/** The runtime's answer, with the status it really travels with. */
function answering(status: number, body: unknown): typeof fetch {
  return (async () => ({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
  })) as unknown as typeof fetch;
}

function transport(status: number, body: unknown): HttpWsTransport {
  return new HttpWsTransport({ baseUrl: 'http://h', fetchImpl: answering(status, body) });
}

/** Run `fn` with the shell's locale set to `lang`, the way the shell stores it. */
async function inLocale<T>(lang: string, fn: () => Promise<T>): Promise<T> {
  const g = globalThis as { localStorage?: unknown };
  const prev = g.localStorage;
  g.localStorage = { getItem: (k: string) => (k === 'erplora.locale' ? lang : null) };
  try {
    return await fn();
  } finally {
    if (prev === undefined) delete g.localStorage;
    else g.localStorage = prev;
  }
}

/** What `/api/command` and `/api/query` answer today for a dead session (`dispatch_api::unauthorized`). */
const DEAD_SESSION = { ok: false, error: 'no autenticado: sesión cerrada' };

async function refusal(p: Promise<unknown>): Promise<ErploraError> {
  try {
    await p;
  } catch (e) {
    assert.ok(e instanceof ErploraError, 'every refusal is an ErploraError a module can branch on');
    return e;
  }
  assert.fail('expected a refusal');
}

test('hub#2281: a command refused for a dead session says so, in the hub language, with the way out', async () => {
  const e = await inLocale('es', () => refusal(transport(401, DEAD_SESSION).command('kitchen.station_create', {})));

  assert.equal(e.code, 'unauthorized', 'the stable code the runtime uses for «sign in again» (AuthError::code)');
  assert.notEqual(e.message, 'unknown error');
  assert.doesNotMatch(e.message, /no autenticado/, 'the runtime\'s log prose never reaches a counter');
  assert.match(e.message, /Vuelve a entrar/, 'it says what to do');
});

test('hub#2281: the same refusal on a query, in English when the hub runs in English', async () => {
  const e = await inLocale('en', () => refusal(transport(401, DEAD_SESSION).query('kitchen.stations.list', {})));

  assert.equal(e.code, 'unauthorized');
  assert.match(e.message, /sign in again/i);
});

test('hub#2281: the coded 401 of the newer doors (`auth_rejected`) reads the same way', async () => {
  const e = await inLocale('es', () =>
    refusal(
      transport(401, {
        ok: false,
        error: { code: 'unauthorized', message: 'no autenticado: token caducado' },
      }).query('kitchen.stations.list', {}),
    ),
  );

  assert.equal(e.code, 'unauthorized');
  assert.doesNotMatch(e.message, /token caducado/);
  assert.match(e.message, /Vuelve a entrar/);
});

test('hub#2281: a 401 that carries a code of its OWN is not a session that ended', async () => {
  // `hub_not_enrolled` (cloud_proxy): the hub has no machine credential. Signing in again would
  // not fix it, so it must not be told to — the code and its sentence pass through untouched.
  const e = await inLocale('es', () =>
    refusal(
      transport(401, {
        ok: false,
        error: { code: 'hub_not_enrolled', message: 'this hub has no machine credential for erplora.com' },
      }).query('whatsapp_inbox.templates.list', {}),
    ),
  );

  assert.equal(e.code, 'hub_not_enrolled');
  assert.equal(e.message, 'this hub has no machine credential for erplora.com');
});

test('hub#2281: `platformFailureMessage` stays silent on `unauthorized` — the shell\'s own screens say it', () => {
  // Settings › Roles (hub#1705) and its siblings run the SAME function over their own refusals and
  // fall back to their catalogue (`employeeForm.errors.unauthorized`) only when it answers `null`.
  // The session sentence belongs to the module transport (`unwrap`), not to this public table.
  assert.equal(platformFailureMessage({ code: 'unauthorized' }, 'es'), null);
  assert.equal(platformFailureMessage({ code: 'unauthorized' }, 'en'), null);
});

test('hub#2281: the session sentence is a translation, not a copy of the source', async () => {
  const es = await inLocale('es', () => refusal(transport(401, DEAD_SESSION).query('kitchen.stations.list', {})));
  const en = await inLocale('en', () => refusal(transport(401, DEAD_SESSION).query('kitchen.stations.list', {})));

  assert.notEqual(es.message, en.message);
});

test('hub#2281: a refusal with neither code nor message gets the translated sentence, never «unknown error»', async () => {
  const es = await inLocale('es', () => refusal(transport(500, { ok: false }).command('kitchen.station_create', {})));
  const en = await inLocale('en', () => refusal(transport(500, { ok: false }).command('kitchen.station_create', {})));

  assert.equal(es.message, platformFailureMessage({ code: 'error' }, 'es'));
  assert.equal(en.message, platformFailureMessage({ code: 'error' }, 'en'));
  assert.notEqual(es.message, en.message);
});

test('hub#2281: an error object whose message is blank is a refusal with nothing to say', async () => {
  const e = await inLocale('es', () =>
    refusal(transport(409, { ok: false, error: { message: '   ' } }).query('kitchen.stations.list', {})),
  );

  assert.equal(e.message, platformFailureMessage({ code: 'error' }, 'es'));
});

test('hub#2281: a bare-string error that is NOT a 401 is log prose — the person reads the translated sentence', async () => {
  const e = await inLocale('es', () =>
    refusal(
      transport(502, { ok: false, error: 'hub sin credencial (ni token de máquina ni Authorization: Bearer)' })
        .query('kitchen.stations.list', {}),
    ),
  );

  assert.equal(e.code, 'error');
  assert.equal(e.message, platformFailureMessage({ code: 'error' }, 'es'));
});

test('hub#2281: a message the runtime authored still wins over the generic sentence (hub#1102 rule 2)', async () => {
  const e = await inLocale('es', () =>
    refusal(
      transport(409, { ok: false, error: { code: 'kitchen.station_exists', message: 'Ya hay una estación «Barra».' } })
        .command('kitchen.station_create', {}),
    ),
  );

  assert.equal(e.code, 'kitchen.station_exists');
  assert.equal(e.message, 'Ya hay una estación «Barra».');
});

test('hub#2281: the file door (`coreBlobRequest`) tells a dead session the same way', async () => {
  const e = await inLocale('es', () => refusal(transport(401, DEAD_SESSION).coreBlobRequest('/api/hub/export')));

  assert.equal(e.code, 'unauthorized');
  assert.match(e.message, /Vuelve a entrar/);
});
