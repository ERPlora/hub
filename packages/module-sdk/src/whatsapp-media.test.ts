// hub#2114 — the DECLARED way a module downloads a WhatsApp attachment.
//
// A customer sends a photo, a voice note, a video or a document; Meta hands the business an asset
// id, never the file. The runtime proxies the SaaS that swaps the id for the bytes
// (`crates/server/src/whatsapp_media.rs`), with the machine credential the browser never holds
// (ADR-0003). This surface is how module code reaches that door — and these tests are what keep it
// from becoming a proxy: ONE method, ONE prefix, and an id that is not a Meta id never becomes a
// request.
//
// The shape is the one the inbox already calls (whatsapp_inbox#205, in `main`):
// `erplora.forModule('whatsapp_inbox').whatsappMedia.get(mediaId) → Promise<Blob>`. Renaming it
// here leaves every inbox saying «this attachment can't be shown here» with every test green.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  INVALID_ARGUMENT,
  MODULE_HEADER,
  MODULE_SCOPE_REQUIRED,
  SERVER_UNAVAILABLE,
  WHATSAPP_MEDIA_BASE_PATH,
} from './index.ts';

const SESSION = 's3ss10n-of-a-human';
const WHATSAPP = 'whatsapp_inbox';
const PHOTO = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46]);

interface Call {
  url: string;
  init: RequestInit;
}

/** What the runtime answers: bytes on `200`, the envelope on a refusal (`whatsapp_media.rs`). */
type Answer =
  | { kind: 'bytes'; type: string; bytes: Uint8Array }
  | { kind: 'json'; status: number; body: unknown }
  | { kind: 'page'; status: number }
  | { kind: 'throw' };

function scoped(answer: Answer): { client: ErploraClient; calls: Call[] } {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    switch (answer.kind) {
      case 'throw':
        throw new TypeError('Failed to fetch http://10.0.0.7:8000/secret-internal');
      case 'bytes':
        return new Response(answer.bytes, {
          status: 200,
          headers: { 'content-type': answer.type },
        });
      case 'json':
        return new Response(JSON.stringify(answer.body), {
          status: answer.status,
          headers: { 'content-type': 'application/json' },
        });
      case 'page':
        return new Response('<html>502 Bad Gateway</html>', {
          status: answer.status,
          headers: { 'content-type': 'text/html' },
        });
    }
  }) as unknown as typeof fetch;
  const transport = new HttpWsTransport({
    baseUrl: 'http://hub',
    fetchImpl,
    // Exactly what `apps/web/src/lib/runtime.ts` injects: the shell owns the credential.
    headers: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': SESSION }),
  });
  return { client: new ErploraClient(transport).forModule(WHATSAPP), calls };
}

const refusal = (status: number, code: string) =>
  ({ kind: 'json', status, body: { ok: false, error: { code, message: code } } }) as const;

async function rejectsWith(p: Promise<unknown>, code: string): Promise<ErploraError> {
  try {
    await p;
  } catch (e) {
    assert.ok(e instanceof ErploraError, `expected an ErploraError, got ${String(e)}`);
    assert.equal(e.code, code);
    return e;
  }
  assert.fail(`expected a rejection with \`${code}\``);
}

test('hub#2114: the customer’s photo arrives as a Blob with its type, fetched with the shell session', async () => {
  const { client, calls } = scoped({ kind: 'bytes', type: 'image/jpeg', bytes: PHOTO });
  const blob = await client.whatsappMedia.get('1234567890');
  assert.ok(blob instanceof Blob);
  assert.equal(blob.type, 'image/jpeg');
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), PHOTO);

  assert.equal(calls.length, 1);
  const [{ url, init }] = calls;
  assert.equal(url, 'http://hub/api/hub/whatsapp/media/1234567890');
  assert.equal(init.method, 'GET');
  const headers = init.headers as Record<string, string>;
  assert.equal(headers['X-Hub-Session'], SESSION);
  assert.equal(headers[MODULE_HEADER], WHATSAPP, 'the runtime gates on WHICH module asked');
  assert.equal(init.body, undefined);
  // Never follow a 30x: `fetch` could carry the session to another origin.
  assert.equal(init.redirect, 'error');
});

test('hub#2114: an id that is not a Meta id never becomes a request', async () => {
  const { client, calls } = scoped({ kind: 'bytes', type: 'image/jpeg', bytes: PHOTO });
  for (const hostile of ['', 'abc', '12a', '..', '../templates', '1/2', '1?x=2', '9'.repeat(33)]) {
    await rejectsWith(client.whatsappMedia.get(hostile), INVALID_ARGUMENT);
  }
  await rejectsWith(client.whatsappMedia.get(42 as unknown as string), INVALID_ARGUMENT);
  assert.equal(calls.length, 0);
});

test('hub#2114: every refusal reaches the module with its own code', async () => {
  for (const [status, code] of [
    [404, 'media_not_found'],
    [403, 'meta_permission_denied'],
    [409, 'no_whatsapp_number'],
    [424, 'media_unavailable'],
    [403, 'capability_denied'],
    [400, 'invalid_media_id'],
  ] as const) {
    const { client } = scoped(refusal(status, code));
    await rejectsWith(client.whatsappMedia.get('42'), code);
  }
});

test('hub#2114: a page from the proxy and a dead network are `server_unavailable`, with nothing of theirs', async () => {
  const page = scoped({ kind: 'page', status: 502 });
  const e1 = await rejectsWith(page.client.whatsappMedia.get('42'), SERVER_UNAVAILABLE);
  assert.ok(!e1.message.includes('<html>'), e1.message);

  const dead = scoped({ kind: 'throw' });
  const e2 = await rejectsWith(dead.client.whatsappMedia.get('42'), SERVER_UNAVAILABLE);
  assert.ok(!e2.message.includes('10.0.0.7'), e2.message);
});

test('hub#2114: an unscoped client has NO media surface — naming yourself is not optional', () => {
  const transport = new HttpWsTransport({ baseUrl: 'http://hub', headers: () => ({}) });
  assert.throws(
    () => new ErploraClient(transport).whatsappMedia,
    (e: unknown) => e instanceof ErploraError && e.code === MODULE_SCOPE_REQUIRED,
  );
});

// The inbox reads `forModule('whatsapp_inbox')?.whatsappMedia` on EVERY render of the thread
// (reviewer of whatsapp_inbox#205). A getter that throws there takes the whole conversation down
// instead of one attachment: on a transport that cannot fetch bytes, the refusal belongs to `get`.
test('hub#2114: on a transport that cannot fetch bytes, READING the surface never throws — `get` refuses', async () => {
  const bare = {
    query: async () => ({}),
    command: async () => ({}),
    subscribe: () => () => undefined,
  };
  const client = new ErploraClient(bare).forModule(WHATSAPP);
  const surface = client.whatsappMedia;
  assert.equal(typeof surface.get, 'function');
  await rejectsWith(surface.get('42'), SERVER_UNAVAILABLE);
});

test('hub#2114: the surface is ONE method under ONE prefix, and the prefix is the runtime’s route', () => {
  const { client } = scoped({ kind: 'bytes', type: 'image/jpeg', bytes: PHOTO });
  const proto = Object.getPrototypeOf(client.whatsappMedia);
  assert.deepEqual(
    Object.getOwnPropertyNames(proto).sort(),
    ['constructor', 'get'],
    'a new method here widens what every installed module can reach',
  );
  assert.equal(WHATSAPP_MEDIA_BASE_PATH, '/api/hub/whatsapp/media');
  const routes = readFileSync(
    join(fileURLToPath(import.meta.url), '../../../../crates/server/src/routes.rs'),
    'utf8',
  );
  assert.ok(
    routes.includes(`"${WHATSAPP_MEDIA_BASE_PATH}/:media_id"`),
    'the SDK builds a path the runtime does not serve',
  );
});
