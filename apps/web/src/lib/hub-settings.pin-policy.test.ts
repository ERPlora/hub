// @vitest-environment happy-dom
// hub#359 — **the dial has two readers and must never have two values.**
//
// The login screen reads it from `GET /api/device/mode`, which takes no session because at that
// point there is none (`device-mode.ts`). Everybody already signed in reads it from
// `GET /api/settings`, along with the currency and the language. Two doors onto the same decision
// is exactly how a value drifts — the settings screen showing «never» while the till still paints a
// pinpad, or worse the other way round — so both publish into the SAME `pinPolicy` ref, and this
// file is what holds that.
//
// The write door is only one: `PUT /api/settings`, behind an admin session in the runtime.
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({ 'X-Hub-Session': 'sess-1' }) }));
vi.mock('./theme', () => ({ setHubPalette: vi.fn() }));

import { getHubSettings, updateHubSettings } from './hub-settings';
import { STRICT_PIN_POLICY, pinPolicy } from './pin-policy';

/** A `fetch` double answering once with `status` + `body`. */
function respondWith(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  pinPolicy.value = STRICT_PIN_POLICY;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('reading the hub settings', () => {
  it('publishes the dial into the same value the login screen reads', async () => {
    respondWith(200, { currency: 'EUR', language: 'es', pin_policy: 'never' });

    const settings = await getHubSettings();

    expect(settings.pin_policy).toBe('never');
    expect(pinPolicy.value).toBe('never');
  });

  it('keeps asking when the answer does not carry a readable dial', async () => {
    // An older runtime, a proxy that dropped the field, a spelling this build does not know. None
    // of them may be read as permission to stop asking who is selling.
    for (const answer of [undefined, null, 'Never', 'off', 0, true]) {
      pinPolicy.value = 'never';
      respondWith(200, { currency: 'EUR', language: 'es', pin_policy: answer });

      const settings = await getHubSettings();

      expect(settings.pin_policy, JSON.stringify(answer)).toBe('per_shift');
      expect(pinPolicy.value).toBe('per_shift');
    }
  });
});

describe('writing the hub settings', () => {
  it('publishes what the SERVER confirmed, not what was asked for', async () => {
    // The runtime answers with the complete settings object after validating. If the client
    // published its own request instead, a refused or normalised value would leave the whole app
    // believing a dial position the hub is not in.
    const fetchMock = respondWith(200, { currency: 'EUR', language: 'es', pin_policy: 'per_shift' });

    const settings = await updateHubSettings({ pin_policy: 'never' });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ pin_policy: 'never' });
    expect(settings.pin_policy).toBe('per_shift');
    expect(pinPolicy.value).toBe('per_shift');
  });

  it('leaves the dial alone when the write is refused', async () => {
    respondWith(401, { ok: false });

    await expect(updateHubSettings({ pin_policy: 'never' })).rejects.toThrow();

    expect(pinPolicy.value).toBe(STRICT_PIN_POLICY);
  });
});
