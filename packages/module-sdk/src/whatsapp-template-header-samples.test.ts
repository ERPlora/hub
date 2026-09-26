// hub#2232 — how a module sends the SAMPLE of a template's photo, video or PDF header to Meta.
//
// Meta registers a template whose header is a file only with an example of that file already
// uploaded to it, named by a `header_handle` (saas#2377). The upload needs the business's Meta
// token, which only the SaaS holds, and the SaaS door opens with the hub's machine credential, which
// never reaches the browser. So the runtime relays the form (`crates/server/src/
// whatsapp_header_samples.rs`) and this is the module's way in: the file goes as the multipart
// field `file`, the handle comes back, and the tab sends it with `header_format` when it registers
// the template.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  ErploraClient,
  ErploraError,
  HttpWsTransport,
  MODULE_HEADER,
  WHATSAPP_TEMPLATE_HEADER_SAMPLES_PATH,
} from './index.ts';

const SESSION = 's3ss10n-of-a-human-admin';
const WHATSAPP = 'whatsapp_inbox';

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
  return { client: new ErploraClient(transport).forModule(WHATSAPP), calls };
}

const PHOTO = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0xff, 0xd9]);

test('hub#2232: the sample goes up as the form field `file` and the handle comes back', async () => {
  const sample = {
    header_handle: '4::aW1hZ2UvanBlZw==:ARb-sample',
    format: 'IMAGE',
    mime_type: 'image/jpeg',
    size: PHOTO.byteLength,
  };
  const { client, calls } = scoped(201, { ok: true, data: sample });
  const file = new File([PHOTO], 'cabecera.jpg', { type: 'image/jpeg' });

  const result = await client.whatsappTemplates.uploadHeaderSample(file);

  assert.deepEqual(result, sample);
  assert.equal(calls.length, 1);
  const call = calls[0]!;
  assert.equal(call.url, `http://hub${WHATSAPP_TEMPLATE_HEADER_SAMPLES_PATH}`);
  assert.equal(call.method, 'POST');
  assert.equal(call.headers['X-Hub-Session'], SESSION);
  assert.equal(
    call.headers[MODULE_HEADER],
    WHATSAPP,
    'the call names the module it acts for: that is what the `notify` capability gate reads',
  );
  // The browser writes the multipart `Content-Type` WITH its boundary. A `Content-Type` set here —
  // the JSON one of every other call, or a bare `multipart/form-data` — would drop the boundary,
  // and neither the runtime nor the SaaS could find the file.
  assert.equal(
    Object.keys(call.headers).find((h) => h.toLowerCase() === 'content-type'),
    undefined,
    'no Content-Type may be set by hand on a form upload',
  );
  assert.ok(call.body instanceof FormData, 'the file travels as a form, not as JSON');
  const sent = (call.body as FormData).get('file');
  assert.ok(sent instanceof Blob);
  assert.equal((sent as File).name, 'cabecera.jpg');
  assert.deepEqual(new Uint8Array(await (sent as Blob).arrayBuffer()), PHOTO);
});

test('hub#2232: a bare Blob (no file name) still goes up, under a name', async () => {
  const { client, calls } = scoped(201, { ok: true, data: {} });

  await client.whatsappTemplates.uploadHeaderSample(new Blob([PHOTO], { type: 'image/jpeg' }));

  const sent = (calls[0]!.body as FormData).get('file') as File;
  assert.ok(sent.name.length > 0, 'a multipart part without a filename is not a file to the SaaS');
  assert.deepEqual(new Uint8Array(await sent.arrayBuffer()), PHOTO);
});

test('hub#2232: a refusal arrives with its code, which is what lets the tab say WHY', async () => {
  const { client } = scoped(400, {
    ok: false,
    error: { code: 'unsupported_header_sample', message: 'not a JPEG, PNG, MP4 or PDF' },
  });

  await assert.rejects(
    () => client.whatsappTemplates.uploadHeaderSample(new Blob([PHOTO])),
    (e: unknown) => e instanceof ErploraError && e.code === 'unsupported_header_sample',
  );
});

// The path is a claim about a route written in Rust. Compare it to the router, so a rename on
// either side turns this red instead of shipping a tab whose upload is a 404.
test('hub#2232: the upload path is a route the runtime actually serves', () => {
  const routes = readFileSync(
    fileURLToPath(new URL('../../../crates/server/src/routes.rs', import.meta.url)),
    'utf8',
  );
  assert.ok(
    routes.includes(`"${WHATSAPP_TEMPLATE_HEADER_SAMPLES_PATH}"`),
    `crates/server/src/routes.rs does not route ${WHATSAPP_TEMPLATE_HEADER_SAMPLES_PATH}`,
  );
});
