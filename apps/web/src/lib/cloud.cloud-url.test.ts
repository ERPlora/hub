// The web app learns WHICH Cloud it talks to from the runtime, not from the build (hub#1164).
//
// One image serves pre and prod. The runtime knows its Cloud (`HUB_CLOUD_API_URL`) and publishes
// it as `cloud_base_url` in `GET /api/hub/context`; `VITE_CLOUD_API_URL` is only the fallback for
// a dev/local build whose runtime has no Cloud configured. A login fired before the context has
// answered must WAIT for it — never race ahead to the build-time (prod) URL.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { beginRequest, endRequest } = vi.hoisted(() => ({
  beginRequest: vi.fn(),
  endRequest: vi.fn(),
}));

vi.mock('./shell', () => ({ beginRequest, endRequest }));
vi.mock('./device', () => ({
  isTauri: () => false,
  loginHeaders: vi.fn(async () => ({ 'X-Client-Type': 'hub' })),
  setRuntimeClientKind: vi.fn(),
}));

/** Where each request went, in order. */
let requested: string[] = [];

/** A pending `/api/hub/context` answer the test releases by hand. */
type Deferred = { resolve: () => void };

function fetchStub(context: Record<string, unknown> | null, hold?: Deferred) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    requested.push(url);
    if (url.endsWith('/api/hub/context')) {
      if (hold) await new Promise<void>((resolve) => { hold.resolve = resolve; });
      if (!context) return new Response(null, { status: 503 });
      return new Response(JSON.stringify(context), { status: 200 });
    }
    if (url.includes('/api/v1/auth/login/')) {
      return new Response(JSON.stringify({ access: 'a', refresh: 'r' }), { status: 200 });
    }
    if (url.includes('/api/v1/auth/me/')) {
      return new Response(JSON.stringify({ id: 'u1', name: 'Ana', email: 'ana@test' }), { status: 200 });
    }
    return new Response(null, { status: 404 });
  });
}

async function freshModules() {
  vi.resetModules();
  const runtime = await import('./runtime');
  const cloud = await import('./cloud');
  const { config } = await import('./config');
  return { ...runtime, ...cloud, config };
}

describe('cloudApiUrl is resolved from /api/hub/context at boot', () => {
  beforeEach(() => {
    requested = [];
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', new Map() as unknown as Storage);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the login to the Cloud the context names (pre), not to the build-time default', async () => {
    vi.stubGlobal(
      'fetch',
      fetchStub({ hub_id: 'hub-pre', machine_registered: true, cloud_base_url: 'https://pre.erplora.com' }),
    );
    const { bootHubContext, cloudLogin, config } = await freshModules();
    await bootHubContext();

    await cloudLogin('ana@test', 'secret');

    expect(config.cloudApiUrl).toBe('https://pre.erplora.com');
    expect(requested).toContain('https://pre.erplora.com/api/v1/auth/login/');
    expect(requested.some((u) => u.startsWith('https://erplora.com/'))).toBe(false);
  });

  it('keeps the build-time fallback when the context carries no cloud_base_url', async () => {
    vi.stubGlobal('fetch', fetchStub({ hub_id: 'hub-dev', machine_registered: false }));
    const { bootHubContext, cloudLogin, config } = await freshModules();
    const fallback = config.cloudApiUrl;
    await bootHubContext();

    await cloudLogin('ana@test', 'secret');

    expect(config.cloudApiUrl).toBe(fallback);
    expect(requested).toContain(`${fallback}/api/v1/auth/login/`);
  });

  it('keeps the build-time fallback when the context is empty or the runtime does not answer', async () => {
    vi.stubGlobal('fetch', fetchStub({ hub_id: 'hub-dev', cloud_base_url: '   ' }));
    const empty = await freshModules();
    const fallback = empty.config.cloudApiUrl;
    await empty.bootHubContext();
    expect(empty.config.cloudApiUrl).toBe(fallback);

    vi.stubGlobal('fetch', fetchStub(null));
    const down = await freshModules();
    await down.bootHubContext();
    await down.cloudLogin('ana@test', 'secret');
    expect(down.config.cloudApiUrl).toBe(fallback);
    expect(requested).toContain(`${fallback}/api/v1/auth/login/`);
  });

  it('a login fired before the context answers waits for it and uses the context URL', async () => {
    const hold: Deferred = { resolve: () => {} };
    vi.stubGlobal(
      'fetch',
      fetchStub({ hub_id: 'hub-pre', machine_registered: true, cloud_base_url: 'https://pre.erplora.com' }, hold),
    );
    const { bootHubContext, cloudLogin } = await freshModules();
    const boot = bootHubContext(); // in flight, context not answered yet
    const login = cloudLogin('ana@test', 'secret');

    // Give the login every chance to race ahead: it must not have hit any Cloud yet.
    await new Promise((r) => setTimeout(r, 20));
    expect(requested.filter((u) => u.includes('/api/v1/auth/login/'))).toEqual([]);

    hold.resolve();
    await boot;
    await login;

    expect(requested).toContain('https://pre.erplora.com/api/v1/auth/login/');
    expect(requested.some((u) => u.startsWith('https://erplora.com/'))).toBe(false);
  });
});
