// hub#2256 / hub#2255 — a page load the hub REFUSES must not leave the person on a blank page.
//
// On the night of 26–27/09 the edge in front of the hubs banned the recording machine's address
// (infra#334) and answered every request, page loads included, with `403` and an empty body. The
// service worker's navigation handler was «network first, cached shell only when the network
// FAILS»: a 403 is an answer, not a failure, so it handed the empty 403 to the browser — a blank
// page with no word and no button — and on top of that stored it as the cached shell, so the next
// offline start was blank too.
//
// What it must do instead: keep the cached shell for any page load that does not come back OK, so
// the shell boots and its own boot check says what is going on; and never overwrite the shell with
// a refusal.
//
// The worker runs here for real: `public/sw.js` is evaluated against a fake `self`, `caches` and
// `fetch`, and the test drives its `fetch` listener the way the browser does.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const SW_SOURCE = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8');
const ORIGIN = 'https://demo.a.erplora.com';
const SHELL_HTML = '<!doctype html><div id="app"></div>';

type Listener = (event: unknown) => void;

function fakeCaches() {
  const store = new Map<string, Response>();
  const cache = {
    async put(key: string | Request, res: Response) {
      store.set(typeof key === 'string' ? key : new URL(key.url).pathname, res);
    },
    async add(key: string) {
      store.set(key, new Response(SHELL_HTML, { status: 200 }));
    },
  };
  return {
    store,
    api: {
      open: async () => cache,
      keys: async () => [],
      delete: async () => true,
      match: async (key: string | Request) => {
        const hit = store.get(typeof key === 'string' ? key : new URL(key.url).pathname);
        return hit ? hit.clone() : undefined;
      },
    },
  };
}

function bootWorker(network: () => Promise<Response>) {
  const listeners = new Map<string, Listener>();
  const caches = fakeCaches();
  const self = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, fn: Listener) => listeners.set(type, fn),
    skipWaiting: () => undefined,
    clients: { claim: () => undefined },
  };
  new Function('self', 'caches', 'fetch', SW_SOURCE)(self, caches.api, network);

  /** Drives one page load through the worker; resolves with what the browser would paint. */
  async function navigate(path: string): Promise<Response> {
    let answer: Promise<Response> | null = null;
    listeners.get('fetch')!({
      request: { method: 'GET', mode: 'navigate', url: `${ORIGIN}${path}` },
      respondWith: (p: Promise<Response>) => {
        answer = p;
      },
    });
    expect(answer, `the worker must answer the page load of ${path}`).not.toBeNull();
    return answer!;
  }

  /** Whether the worker takes the page load of `path` at all (a passthrough leaves it to the browser). */
  function intercepts(path: string): boolean {
    let taken = false;
    listeners.get('fetch')!({
      request: { method: 'GET', mode: 'navigate', url: `${ORIGIN}${path}` },
      respondWith: () => {
        taken = true;
      },
    });
    return taken;
  }

  /** Lets the fire-and-forget cache writes of the handler land. */
  const settle = () => new Promise((r) => setTimeout(r, 0));

  return { navigate, intercepts, settle, store: caches.store };
}

const refused = () => Promise.resolve(new Response('', { status: 403 }));
const ok = () => Promise.resolve(new Response(SHELL_HTML, { status: 200 }));

describe('a page load the hub refuses still opens the app (hub#2256, hub#2255)', () => {
  for (const status of [403, 502, 503]) {
    it(`serves the cached shell instead of an empty ${status}`, async () => {
      let answer = ok;
      const sw = bootWorker(() => answer());
      await (await sw.navigate('/dashboard')).text();
      await sw.settle();

      answer = () => Promise.resolve(new Response('', { status }));
      const res = await sw.navigate('/apps');

      expect(res.status).toBe(200);
      expect(await res.text()).toBe(SHELL_HTML);
    });
  }

  it('never stores a refusal as the cached shell', async () => {
    let answer = ok;
    const sw = bootWorker(() => answer());
    await (await sw.navigate('/dashboard')).text();
    await sw.settle();

    answer = refused;
    await sw.navigate('/m/kitchen');
    await sw.settle();

    // Offline next: the shell that comes back is the good one, not the empty 403.
    answer = () => Promise.reject(new TypeError('Failed to fetch'));
    const offline = await sw.navigate('/m/kitchen');
    expect(offline.status).toBe(200);
    expect(await offline.text()).toBe(SHELL_HTML);
  });

  it('passes the refusal through when there is no good shell to fall back on', async () => {
    const sw = bootWorker(() => Promise.resolve(new Response('', { status: 503 })));
    // A cache poisoned by an earlier version of this worker holds an empty 403 as the shell.
    sw.store.set('/', new Response('', { status: 403 }));

    const res = await sw.navigate('/apps');

    // The network's own answer, not the poisoned copy.
    expect(res.status).toBe(503);
  });

  it('offline with only a poisoned shell, it fails the load instead of painting the old empty 403', async () => {
    const sw = bootWorker(() => Promise.reject(new TypeError('Failed to fetch')));
    sw.store.set('/', new Response('', { status: 403 }));

    const res = await sw.navigate('/apps');

    expect(res.type).toBe('error');
  });

  it('a page load that comes back OK is still served from the network and refreshes the shell', async () => {
    const fresh = '<!doctype html><div id="app" data-build="new"></div>';
    const sw = bootWorker(() => Promise.resolve(new Response(fresh, { status: 200 })));

    const res = await sw.navigate('/apps');
    expect(await res.text()).toBe(fresh);
    await sw.settle();

    expect(await sw.store.get('/')!.clone().text()).toBe(fresh);
  });
});

// The ticket page (`/p/:locator`, hub#963) is not the app: the hub renders it for the diner, and its
// 403/404/410/429 pages ARE the answer («already claimed», «not found», «too many tries»). Swapping
// them for the cached shell would paint the back office where that sentence should be, and an OK
// ticket page stored as the shell would open the next offline start on somebody's ticket.
describe('the ticket page is left to the browser (hub#2256 review)', () => {
  for (const status of [200, 403, 404, 410, 429]) {
    it(`does not take a ${status} page load of /p/…`, () => {
      const sw = bootWorker(() => Promise.resolve(new Response('<p>ticket</p>', { status })));

      expect(sw.intercepts('/p/AB12CD')).toBe(false);
    });
  }

  it('still takes the page loads of the app', () => {
    const sw = bootWorker(ok);

    expect(sw.intercepts('/pos')).toBe(true);
    expect(sw.intercepts('/m/sales/pos')).toBe(true);
  });
});
