import assert from 'node:assert/strict';
import test from 'node:test';

import { ErploraClient, HttpWsTransport, type ErploraTransport } from './index.ts';

function transportWith(fetchImpl: typeof fetch): HttpWsTransport {
  return new HttpWsTransport({
    baseUrl: 'https://hub.example',
    headers: () => ({ 'X-Hub-Session': 'session-secret' }),
    fetchImpl,
  });
}

test('media: downloads a portable raw reference with the session only in the header', async () => {
  let request: { url: string; init?: RequestInit } | undefined;
  const fetchImpl = (async (input: string | URL | Request, init?: RequestInit) => {
    request = { url: String(input), init };
    return new Response('webp', { status: 200, headers: { 'Content-Type': 'image/webp' } });
  }) as typeof fetch;

  const signal = new AbortController().signal;
  const blob = await new ErploraClient(transportWith(fetchImpl)).fetchMediaBlob(
    '/api/media/raw?path=hospitality%2Fpizza_margarita.webp',
    { signal },
  );

  assert.equal(blob?.type, 'image/webp');
  assert.equal(request?.url, 'https://hub.example/api/media/raw?path=hospitality%2Fpizza_margarita.webp');
  assert.deepEqual(request?.init?.headers, { 'X-Hub-Session': 'session-secret' });
  assert.equal(request?.init?.signal, signal);
  assert.equal(request?.init?.redirect, 'error');
  assert.equal(request?.url.includes('session-secret'), false);
});

test('media: accepts a bare path but never becomes a generic authenticated fetch', async () => {
  const urls: string[] = [];
  const fetchImpl = (async (input: string | URL | Request) => {
    urls.push(String(input));
    return new Response('ok', { status: 200, headers: { 'Content-Type': 'image/webp' } });
  }) as typeof fetch;
  const client = new ErploraClient(transportWith(fetchImpl));

  assert.ok(await client.fetchMediaBlob('beauty_hair/champu profesional.webp'));
  for (const ref of [
    'https://attacker.example/a.webp',
    '//attacker.example/a.webp',
    '../private.env',
    'hospitality/../private.env',
    '/api/settings',
    '/api/media/raw?path=x.webp&next=/api/settings',
    '/api/media/raw?path=x.webp&path=y.webp',
  ]) assert.equal(await client.fetchMediaBlob(ref), null, ref);

  assert.deepEqual(urls, [
    'https://hub.example/api/media/raw?path=beauty_hair%2Fchampu%20profesional.webp',
  ]);
});

test('media: missing files, aborts and transports without the capability degrade to null', async () => {
  const missing = transportWith((async () => new Response('', { status: 404 })) as typeof fetch);
  assert.equal(await new ErploraClient(missing).fetchMediaBlob('hospitality/missing.webp'), null);

  const aborted = transportWith((async (_input, init) => {
    assert.equal(init?.signal?.aborted, true);
    throw new DOMException('aborted', 'AbortError');
  }) as typeof fetch);
  const controller = new AbortController();
  controller.abort();
  assert.equal(
    await new ErploraClient(aborted).fetchMediaBlob('hospitality/a.webp', { signal: controller.signal }),
    null,
  );

  const legacy: ErploraTransport = {
    query: async () => [],
    command: async () => ({}),
    subscribe: () => () => undefined,
  };
  assert.equal(await new ErploraClient(legacy).fetchMediaBlob('hospitality/a.webp'), null);
});

test('media: the module-facing capability refuses non-image media', async () => {
  const document = transportWith((async () => new Response('private', {
    status: 200,
    headers: { 'Content-Type': 'application/pdf' },
  })) as typeof fetch);
  assert.equal(await new ErploraClient(document).fetchMediaBlob('documents/private.pdf'), null);
});
