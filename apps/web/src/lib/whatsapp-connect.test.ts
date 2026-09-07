// «Connect WhatsApp» from the hub (hub#1600, ADR-0452) — the browser half, without a browser.
//
// What only fails on a customer's laptop otherwise, pinned here with fakes for the three things
// the code touches (the document, the window, Meta's SDK):
//   - the SDK is asked for by locale, initialised with OUR app id and Graph version, and the popup
//     is opened with the configuration id, `response_type: 'code'` and the WhatsApp-Business-app
//     feature (the QR flow);
//   - the ids Meta posts as a `message` event are believed only from *.facebook.com and travel with
//     the code to the runtime — which is where the machine credential lives, so the request carries
//     the hub session and nothing else;
//   - CANCEL rejects with its own code, and a refusal from the runtime keeps the SaaS's code.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({ 'X-Hub-Session': 'session-123', 'X-Hub-Id': 'hub-wa' }),
}));

import {
  BUSINESS_APP_FEATURE,
  WhatsAppConnectError,
  connectWhatsApp,
  disconnectWhatsApp,
  fetchWhatsAppConfig,
  fetchWhatsAppNumbers,
  isMetaOrigin,
  loadMetaSdk,
  openEmbeddedSignup,
  sdkScriptUrl,
} from './whatsapp-connect';

type Listener = (event: { origin: string; data: unknown }) => void;

function fakeWindow() {
  const listeners = new Set<Listener>();
  return {
    listeners,
    addEventListener: (type: string, fn: Listener) => {
      if (type === 'message') listeners.add(fn);
    },
    removeEventListener: (type: string, fn: Listener) => {
      if (type === 'message') listeners.delete(fn);
    },
    post: (origin: string, payload: unknown) => {
      for (const fn of listeners) fn({ origin, data: JSON.stringify(payload) });
    },
  };
}

describe('the SDK', () => {
  it('is asked for by locale', () => {
    expect(sdkScriptUrl('es')).toBe('https://connect.facebook.net/es_ES/sdk.js');
    expect(sdkScriptUrl('es-ES')).toBe('https://connect.facebook.net/es_ES/sdk.js');
    expect(sdkScriptUrl('en')).toBe('https://connect.facebook.net/en_US/sdk.js');
    expect(sdkScriptUrl('fr')).toBe('https://connect.facebook.net/en_US/sdk.js');
  });

  it('is loaded once, initialised with our app id and Graph version, and reused afterwards', async () => {
    const appended: Array<{ src: string }> = [];
    const FB = { init: vi.fn(), login: vi.fn() };
    const win: Record<string, unknown> = {};
    const doc = {
      createElement: () => ({}) as { src: string },
      head: {
        appendChild: (script: { src: string }) => {
          appended.push(script);
          win.FB = FB;
          (win.fbAsyncInit as () => void)();
        },
      },
    };

    const first = await loadMetaSdk({ appId: '1534856651538860', graphVersion: 'v25.0', locale: 'es' }, win, doc);
    const second = await loadMetaSdk({ appId: '1534856651538860', graphVersion: 'v25.0', locale: 'es' }, win, doc);

    expect(first).toBe(FB);
    expect(second).toBe(FB);
    expect(appended.map((s) => s.src)).toEqual(['https://connect.facebook.net/es_ES/sdk.js']);
    expect(FB.init).toHaveBeenCalledWith({ appId: '1534856651538860', autoLogAppEvents: true, xfbml: false, version: 'v25.0' });
  });
});

describe('the popup', () => {
  it('opens with the configuration id, a code, and the WhatsApp Business app feature (the QR)', async () => {
    const win = fakeWindow();
    const FB = {
      init: vi.fn(),
      login: vi.fn((cb: (r: unknown) => void) => {
        win.post('https://www.facebook.com', {
          type: 'WA_EMBEDDED_SIGNUP',
          event: 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING',
          data: { waba_id: 'waba_123', phone_number_id: 'phone_123', business_id: 'biz_123' },
        });
        cb({ authResponse: { code: 'oauth-code' } });
      }),
    };

    const result = await openEmbeddedSignup(FB, 'cfg_987', win);

    const [, opts] = FB.login.mock.calls[0] as unknown as [unknown, Record<string, unknown>];
    expect(opts.config_id).toBe('cfg_987');
    expect(opts.response_type).toBe('code');
    expect(opts.override_default_response_type).toBe(true);
    expect((opts.extras as Record<string, unknown>).featureType).toBe(BUSINESS_APP_FEATURE);
    expect((opts.extras as Record<string, unknown>).sessionInfoVersion).toBe('3');
    expect(result).toEqual({
      code: 'oauth-code',
      event: 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING',
      waba_id: 'waba_123',
      phone_number_id: 'phone_123',
      business_id: 'biz_123',
    });
    expect(win.listeners.size).toBe(0);
  });

  it('believes the ids only when they come from facebook.com', async () => {
    expect(isMetaOrigin('https://www.facebook.com')).toBe(true);
    expect(isMetaOrigin('https://business.facebook.com')).toBe(true);
    expect(isMetaOrigin('https://facebook.com.evil.example')).toBe(false);
    expect(isMetaOrigin('https://evilfacebook.com')).toBe(false);
    expect(isMetaOrigin('not a url')).toBe(false);

    const win = fakeWindow();
    const FB = {
      init: vi.fn(),
      login: vi.fn((cb: (r: unknown) => void) => {
        win.post('https://facebook.com.evil.example', {
          type: 'WA_EMBEDDED_SIGNUP',
          event: 'FINISH',
          data: { waba_id: 'forged', phone_number_id: 'forged' },
        });
        cb({ authResponse: { code: 'oauth-code' } });
      }),
    };

    const result = await openEmbeddedSignup(FB, 'cfg_987', win);

    expect(result.waba_id).toBe('');
    expect(result.phone_number_id).toBe('');
    expect(result.event).toBe('FINISH');
  });

  it('rejects with its own code when the person closes the popup', async () => {
    const win = fakeWindow();
    const FB = {
      init: vi.fn(),
      login: vi.fn((cb: (r: unknown) => void) => {
        win.post('https://www.facebook.com', { type: 'WA_EMBEDDED_SIGNUP', event: 'CANCEL', data: { current_step: 'PHONE' } });
        cb({ authResponse: null });
      }),
    };

    await expect(openEmbeddedSignup(FB, 'cfg_987', win)).rejects.toMatchObject({ code: 'cancelled' });
    expect(win.listeners.size).toBe(0);
  });
});

describe('the runtime doors', () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  function answer(status: number, body: unknown) {
    fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
  }

  it('reads the configuration and the numbers with the hub session', async () => {
    answer(200, { configured: true, app_id: '1534856651538860', config_id: 'cfg_987', graph_version: 'v25.0' });
    answer(200, { numbers: [{ phone_number_id: 'phone_123', display_phone: '+34 612 345 678', is_active: true }] });

    const config = await fetchWhatsAppConfig();
    const numbers = await fetchWhatsAppNumbers();

    expect(config.config_id).toBe('cfg_987');
    expect(numbers[0].display_phone).toBe('+34 612 345 678');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/hub/whatsapp/config');
    expect((init.headers as Record<string, string>)['X-Hub-Session']).toBe('session-123');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/hub/whatsapp/numbers');
  });

  it('carries the flag that says the channel died on its own', async () => {
    // The runtime hands the front the SaaS's JSON verbatim (`cloud_proxy::cloud_json_passthrough`),
    // so `needs_reconnect` only had to be READ — and it was not, which is how a dead channel kept
    // showing up as connected (hub#1626). A number an older SaaS answers about carries no field at
    // all, and that has to stay `undefined`, never `false` invented here.
    answer(200, {
      numbers: [
        { phone_number_id: 'down', display_phone: '+34 600 000 001', is_active: true, needs_reconnect: true, token_expires_at: '2026-05-25T10:00:00Z' },
        { phone_number_id: 'old', display_phone: '+34 600 000 002', is_active: true },
      ],
    });

    const numbers = await fetchWhatsAppNumbers();

    expect(numbers[0].needs_reconnect).toBe(true);
    expect(numbers[1].needs_reconnect).toBeUndefined();
  });

  it('posts the popup result verbatim and never a bearer of its own', async () => {
    answer(200, { phone_number_id: 'phone_123', display_phone: '+34 612 345 678', is_on_biz_app: true });
    const popup = { code: 'oauth-code', event: 'FINISH', waba_id: 'w', phone_number_id: 'p', business_id: 'b' };

    const connected = await connectWhatsApp(popup);

    expect(connected.display_phone).toBe('+34 612 345 678');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/hub/whatsapp/connect');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual(popup);
    const headers = init.headers as Record<string, string>;
    expect(headers['X-Hub-Session']).toBe('session-123');
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers.Authorization).toBeUndefined();
  });

  it("keeps the SaaS's error code so the page can name it", async () => {
    answer(404, { error: 'no_phone_number' });

    await expect(connectWhatsApp({ code: 'c', event: 'FINISH_ONLY_WABA', waba_id: 'w', phone_number_id: '', business_id: '' })).rejects.toMatchObject({
      code: 'no_phone_number',
      status: 404,
    });
    expect(new WhatsAppConnectError('x', 502).code).toBe('x');
  });

  const POPUP = { code: 'c', event: 'FINISH_ONLY_WABA', waba_id: 'w', phone_number_id: '', business_id: '' };

  it("reads the SaaS's `code` when the view sends one next to its prose", async () => {
    answer(404, { error: 'No phone numbers found in WhatsApp Business Account', code: 'no_phone_number' });

    await expect(connectWhatsApp(POPUP)).rejects.toMatchObject({ code: 'no_phone_number', status: 404 });
  });

  it('does not take a sentence for a code: the connect door\u2019s 404 without one means no phone number', async () => {
    // What saas#1886 actually answers today: prose in `error`, no code. The only 404 that view
    // returns is «no phone numbers in the WABA», so the page may name it; any other prose is the
    // generic sentence — never a catalogue key made out of the prose.
    answer(404, { error: 'No phone numbers found in WhatsApp Business Account' });
    await expect(connectWhatsApp(POPUP)).rejects.toMatchObject({ code: 'no_phone_number', status: 404 });

    answer(502, { error: 'Could not identify WhatsApp Business Account' });
    await expect(connectWhatsApp(POPUP)).rejects.toMatchObject({ code: 'default', status: 502 });
  });

  it("lands the runtime's own refusal, prose too, on `forbidden`", async () => {
    answer(403, { ok: false, error: 'se requiere rol owner/admin para gestionar el Hub (rol actual: employee)' });

    await expect(fetchWhatsAppConfig()).rejects.toMatchObject({ code: 'forbidden', status: 403 });
  });

  it('disconnects by posting to the number', async () => {
    answer(200, { success: true });

    await disconnectWhatsApp('phone_123');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/hub/whatsapp/disconnect/phone_123');
    expect(init.method).toBe('POST');
  });
});
