// The wire contract of voice→text (hub#629): the drawer's audio goes to the SaaS speech proxy
// (`apps/speech`, Whisper) — the SAME auth plane as billing/marketplace (user JWT + X-Hub-Id,
// `IsHubMember`), never to an external LLM/API. Multipart is fetch's to encode: setting the
// Content-Type by hand would drop the boundary and the SaaS would read an empty form.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { beginRequest, endRequest } = vi.hoisted(() => ({
  beginRequest: vi.fn(),
  endRequest: vi.fn(),
}));
vi.mock('./shell', () => ({ beginRequest, endRequest }));
vi.mock('./device', () => ({
  isTauri: () => false,
  loginHeaders: vi.fn(async () => ({ 'X-Client-Type': 'hub' })),
}));

import { cloudTranscribeSpeech, setTokens } from './cloud';
import { config } from './config';

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, String(value));
    },
  };
}

const originalHubId = config.hubId;
const originalCloudApiUrl = config.cloudApiUrl;
const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal('localStorage', memoryStorage());
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ text: '  dos cafés  ', language: 'es' }), { status: 200 }),
  );
  vi.stubGlobal('fetch', fetchMock);
  config.cloudApiUrl = 'https://cloud.test';
  config.hubId = 'h1';
  setTokens('jwt-user', '');
});

afterEach(() => {
  config.hubId = originalHubId;
  config.cloudApiUrl = originalCloudApiUrl;
  vi.unstubAllGlobals();
});

describe('cloudTranscribeSpeech', () => {
  it('POST multipart al proxy speech del SaaS con JWT + X-Hub-Id, y devuelve el texto limpio', async () => {
    const clip = new Blob(['audio-bytes'], { type: 'audio/webm' });

    const text = await cloudTranscribeSpeech(clip, 'es');

    expect(text).toBe('dos cafés');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://cloud.test/api/v1/hub/device/speech/transcribe/');
    expect(init.method).toBe('POST');
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer jwt-user');
    expect(headers['X-Hub-Id']).toBe('h1');
    // fetch owns the multipart boundary — a hand-set Content-Type would break the form.
    expect(Object.keys(headers).some((h) => h.toLowerCase() === 'content-type')).toBe(false);
    const form = init.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    const audio = form.get('audio');
    expect(audio).toBeInstanceOf(Blob);
    expect(form.get('language')).toBe('es');
  });

  it('un fallo del proxy lanza con su estado (el drawer lo traduce a su mensaje)', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ error: 'Transcription failed' }), { status: 500 }));
    await expect(cloudTranscribeSpeech(new Blob(['x'], { type: 'audio/webm' }))).rejects.toThrow(/500/);
  });
});
