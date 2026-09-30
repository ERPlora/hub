// hub#2335 — how the editor of flows uploads the PHOTO a WhatsApp template step sends in its header.
//
// A template approved with a photo header sends a photo on every message, and Meta downloads it
// from a link. The owner has the file, not a public link, so the runtime keeps it in the hub's own
// files (`crates/server/src/flows_header_media.rs`) and answers a reference the step stores in
// `vars.header_image`; every send signs it afresh. This is the editor's way in: the file goes as
// the multipart field `file`, the reference comes back.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  ErploraClient,
  ErploraError,
  FLOWS_WHATSAPP_HEADER_IMAGES_PATH,
  HttpWsTransport,
  MODULE_HEADER,
} from './index.ts';

const SESSION = 's3ss10n-of-a-human-admin';
const EDITOR = 'flows';

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

function scoped(status: number, answer: unknown): { client: ErploraClient; calls: Call[] } {
  const calls: Call[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({
      url,
      method: String(init.method),
      headers: init.headers as Record<string, string>,
      body: init.body,
    });
    return { status, headers: { get: () => 'application/json' }, json: async () => answer };
  }) as unknown as typeof fetch;
  const transport = new HttpWsTransport({
    baseUrl: 'http://hub',
    fetchImpl,
    headers: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': SESSION }),
  });
  return { client: new ErploraClient(transport).forModule(EDITOR), calls };
}

const PHOTO = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0xff, 0xd9]);

test('hub#2335: the photo goes up as the form field `file` and its reference comes back', async () => {
  const stored = {
    ref: `whatsapp/headers/${'a'.repeat(64)}.jpg`,
    mime_type: 'image/jpeg',
    size: PHOTO.byteLength,
  };
  const { client, calls } = scoped(201, { ok: true, data: stored });
  const file = new File([PHOTO], 'salon.jpg', { type: 'image/jpeg' });

  const result = await client.flows.uploadWhatsappHeaderImage(file);

  assert.deepEqual(result, stored);
  assert.equal(calls.length, 1);
  const call = calls[0]!;
  assert.equal(call.url, `http://hub${FLOWS_WHATSAPP_HEADER_IMAGES_PATH}`);
  assert.equal(call.method, 'POST');
  assert.equal(call.headers['X-Hub-Session'], SESSION);
  assert.equal(
    call.headers[MODULE_HEADER],
    EDITOR,
    'the call names the module it acts for: that is what the `manage_flows` gate reads',
  );
  assert.equal(
    Object.keys(call.headers).find((h) => h.toLowerCase() === 'content-type'),
    undefined,
    'no Content-Type may be set by hand on a form upload: it would drop the boundary',
  );
  assert.ok(call.body instanceof FormData, 'the file travels as a form, not as JSON');
  const sent = (call.body as FormData).get('file');
  assert.ok(sent instanceof Blob);
  assert.deepEqual(new Uint8Array(await (sent as Blob).arrayBuffer()), PHOTO);
});

test('hub#2335: a refusal arrives with its code, which is what lets the step say WHY', async () => {
  const { client } = scoped(413, {
    ok: false,
    error: { code: 'whatsapp.header_image_too_large', message: '5 MB at most' },
  });

  await assert.rejects(
    () => client.flows.uploadWhatsappHeaderImage(new Blob([PHOTO])),
    (e: unknown) => e instanceof ErploraError && e.code === 'whatsapp.header_image_too_large',
  );
});

// The path is a claim about a route written in Rust: compare it to the router, so a rename on
// either side turns this red instead of shipping a step whose upload is a 404.
test('hub#2335: the upload path is a route the runtime actually serves', () => {
  const routes = readFileSync(
    fileURLToPath(new URL('../../../crates/server/src/routes.rs', import.meta.url)),
    'utf8',
  );
  assert.ok(
    routes.includes(`"${FLOWS_WHATSAPP_HEADER_IMAGES_PATH}"`),
    `crates/server/src/routes.rs does not route ${FLOWS_WHATSAPP_HEADER_IMAGES_PATH}`,
  );
});

// hub#2347 — the VIDEO or the PDF of a header goes up the same way, naming its kind. The kind goes
// BEFORE the file, so the runtime refuses a file of another kind before reading the rest of it.
test('hub#2347: a video or a PDF goes up with its `kind` before the `file`', async () => {
  const PDF = new TextEncoder().encode('%PDF-1.7\n');
  for (const kind of ['video', 'document', 'image'] as const) {
    const stored = {
      ref: `whatsapp/headers/${'b'.repeat(64)}.pdf`,
      mime_type: 'application/pdf',
      size: PDF.byteLength,
    };
    const { client, calls } = scoped(201, { ok: true, data: stored });

    const result = await client.flows.uploadWhatsappHeaderMedia(new File([PDF], 'carta.pdf'), kind);

    assert.deepEqual(result, stored);
    const call = calls[0]!;
    assert.equal(call.url, `http://hub${FLOWS_WHATSAPP_HEADER_IMAGES_PATH}`);
    assert.equal(call.method, 'POST');
    assert.equal(call.headers[MODULE_HEADER], EDITOR);
    assert.equal(
      Object.keys(call.headers).find((h) => h.toLowerCase() === 'content-type'),
      undefined,
    );
    const form = call.body as FormData;
    assert.deepEqual([...form.keys()], ['kind', 'file'], 'the kind travels first');
    assert.equal(form.get('kind'), kind);
    assert.deepEqual(new Uint8Array(await (form.get('file') as Blob).arrayBuffer()), PDF);
  }
});

test('hub#2347: a refused video arrives with the code of its kind', async () => {
  const { client } = scoped(413, {
    ok: false,
    error: { code: 'whatsapp.header_video_too_large', message: '16 MB at most' },
  });
  await assert.rejects(
    () => client.flows.uploadWhatsappHeaderMedia(new Blob([new Uint8Array(12)]), 'video'),
    (e: unknown) => e instanceof ErploraError && e.code === 'whatsapp.header_video_too_large',
  );
});
