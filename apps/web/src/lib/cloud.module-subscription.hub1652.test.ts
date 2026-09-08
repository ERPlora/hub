// @vitest-environment happy-dom
// The Cloud answers WHICH plan the hub is on, not only whether it bought one — ERPlora/saas#1921.
//
// `status` describes the *subscription*, and a hub is on a plan without ever having bought one:
// every premium module we publish ships a tier at 0 €, and ADR-0032 makes that tier installable
// with no purchase, so the endpoint answers `status: "none"` to the majority of customers. On its
// own that reads as «no plan», which is the sentence hub#1652 is about. The endpoint therefore
// sends a second, independent answer: `tier`, the slug of the `ModuleTier` in force — the bought
// tier while its subscription is current, else an in-window no-card trial, else the module's free
// tier.
//
// The slug is the one from `billing.tiers[].slug` of the manifest (the SaaS creates the
// `ModuleTier` by that slug), so the screen can match it against the cards it already paints.
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

/** Stubs the endpoint with `body` and hands back the fetch mock, to read the URL it asked for. */
function servesSubscription(body: Record<string, unknown>): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  localStorage.setItem('hub.cloud.access', 'jwt-access');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  localStorage.clear();
});

describe('cloudModuleSubscription — which plan, not only whether you bought one (hub#1652)', () => {
  it('carries the tier slug through', async () => {
    servesSubscription({ status: 'active', tier: 'business', period_end: '2026-10-07T00:00:00Z' });

    await expect(cloudModuleSubscription('whatsapp_inbox')).resolves.toMatchObject({
      status: 'active',
      tier: 'business',
      periodEnd: '2026-10-07T00:00:00Z',
    });
  });

  it('reads the free plan as its own answer: no subscription AND a tier', async () => {
    // The two keys are deliberately independent. Folding them into one — «none means no tier» —
    // is exactly the reading that put «No plan» in front of every free-tier customer.
    servesSubscription({ status: 'none', trial_end: null, period_end: null, tier: 'free' });

    await expect(cloudModuleSubscription('whatsapp_inbox')).resolves.toEqual({
      status: 'none',
      trialEnd: null,
      periodEnd: null,
      tier: 'free',
    });
  });

  it('says null when an older SaaS leaves the key out', async () => {
    // Additive contract: a hub pointing at a SaaS from before saas#1921 gets no `tier` at all, and
    // that has to arrive as a plain "I don't know" rather than as `undefined` leaking into the UI.
    servesSubscription({ status: 'none' });

    await expect(cloudModuleSubscription('whatsapp_inbox')).resolves.toEqual({
      status: 'none',
      trialEnd: null,
      periodEnd: null,
      tier: null,
    });
  });

  it('treats an empty tier as no answer, not as a plan called ""', async () => {
    servesSubscription({ status: 'none', tier: '' });

    await expect(cloudModuleSubscription('whatsapp_inbox')).resolves.toMatchObject({ tier: null });
  });

  it('asks for the module it was given, url-encoded', async () => {
    const fetchMock = servesSubscription({ status: 'none', tier: 'free' });

    await cloudModuleSubscription('whatsapp inbox');

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      '/api/v1/hub/device/module-subscription/?module=whatsapp%20inbox',
    );
  });
});
