// @vitest-environment happy-dom
// Where the module's level COMES FROM — hub#1686, contract of ERPlora/saas#1952.
//
// ADR-0474 (revised 09/09): for ERPlora's own modules the hub's plan gives the level, and that level
// is not sold separately. The endpoint then answers `source: "plan" | "purchase" | "trial" | "free"`
// so the screen can say «Included in your plan» instead of painting a price. `plan_name` is the
// hub plan's display name, the same key the SaaS already uses for the hub subscription list.
//
// Both keys are ADDITIVE: a SaaS older than saas#1952 leaves them out and the hub must read that as
// "I don't know" (null), which keeps today's screen exactly as it is.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./config', () => ({
  cloudApiUrlReady: vi.fn(async () => {}),
  config: { cloudApiUrl: 'https://erplora.com', hubId: 'hub-1234' },
  isLocalHub: () => false,
}));
vi.mock('./device', () => ({
  loginHeaders: vi.fn(async () => ({})),
  resolveDeviceId: vi.fn(async () => null),
  isTauri: () => false,
}));
vi.mock('./shell', () => ({ beginRequest: vi.fn(), endRequest: vi.fn() }));
vi.mock('../i18n', () => ({ getLocale: () => 'es' }));
vi.mock('./session', () => ({ getHubSession: () => null }));

import { cloudModuleSubscription } from './cloud';

/** Stubs the endpoint with `body`. */
function servesSubscription(body: Record<string, unknown>): void {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(body) }));
}

beforeEach(() => {
  localStorage.setItem('hub.cloud.access', 'jwt-access');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
});

describe('cloudModuleSubscription — where the level comes from (hub#1686)', () => {
  it('carries `source` and the hub plan name through', async () => {
    servesSubscription({ status: 'none', tier: 'basic', source: 'plan', plan_name: 'Standard' });

    await expect(cloudModuleSubscription('whatsapp_inbox')).resolves.toMatchObject({
      tier: 'basic',
      source: 'plan',
      planName: 'Standard',
    });
  });

  it.each(['purchase', 'trial', 'free'])('keeps the other known source %s', async (source) => {
    servesSubscription({ status: 'active', tier: 'pro', source });

    await expect(cloudModuleSubscription('whatsapp_inbox')).resolves.toMatchObject({ source });
  });

  it('says null when an older SaaS leaves both keys out', async () => {
    servesSubscription({ status: 'none', tier: 'free' });

    await expect(cloudModuleSubscription('whatsapp_inbox')).resolves.toMatchObject({
      source: null,
      planName: null,
    });
  });

  it('does not invent a source it does not know', async () => {
    // An unknown value must not light up «Included in your plan»: only `plan` does, and only when
    // the SaaS says it literally.
    servesSubscription({ status: 'none', tier: 'free', source: 'gift', plan_name: '' });

    await expect(cloudModuleSubscription('whatsapp_inbox')).resolves.toMatchObject({
      source: null,
      planName: null,
    });
  });
});
