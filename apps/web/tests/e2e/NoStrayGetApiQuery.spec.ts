// hub#332 — a production hub's console showed `GET /api/query → 404` repeated on every panel
// load. The query endpoint is POST-only (`crates/server/src/lib.rs`), and no GET caller exists
// anywhere in the shell, the module SDK, any module bundle, or their git histories. This spec
// pins the contract from the browser side: loading the core panels (and any installed module
// panel) fires NO GET against /api/query, and no /api/query request surfaces a 4xx/5xx in the
// console. If this ever goes red, DevTools' initiator column on the recorded request names the
// culprit — remove the caller (or make it POST), never register a GET route to hush the 404.
//
// Runs against the same real stack as the other specs (runtime :8787 + web :5173, no mocks):
// green on an empty hub (no module fires queries) and green on a dev hub with modules installed
// (widgets/panels fire POSTs that must all succeed).

import { test, expect, request as pwRequest, type Page } from '@playwright/test';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

interface Session {
  token: string;
  user: unknown;
}

/** Real runtime session via `/api/auth/pin` (Demo user / PIN 0000 from the dev seed). */
async function loginByPin(): Promise<Session> {
  const api = await pwRequest.newContext();
  // The device identifies itself, exactly as the browser of a real till does (hub#330: a PIN login
  // that identifies no device is refused). The bank disarms the trust gate with
  // `HUB_DEVICE_TRUST=off` (see `playwright.config.ts`) because the id a browser mints is random
  // and there is nothing to pre-trust in an ephemeral bank — it used to buy that with `HUB_DEMO=1`,
  // which turned the whole hub into a demo and broke the export round trip (hub#1249).
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '0000', device_id: 'e2e-browser-device' },
  });
  expect(res.ok(), `PIN login failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  expect(body.token, 'the runtime returned no session token').toBeTruthy();
  await api.dispose();
  return { token: body.token, user: body.user };
}

/** Injects the session already issued by the runtime (same keys as `lib/session.ts`). */
async function withSession(page: Page, s: Session): Promise<void> {
  await page.addInitScript(
    ([token, user]) => {
      localStorage.setItem('erplora.hub_session', token as string);
      localStorage.setItem('erplora.session', JSON.stringify(user));
    },
    [s.token, s.user] as const,
  );
}

// hub#1211 fixed the real defect this pinned as `fixme` (surfaced when hub#1240 first ran this
// suite): `queryOptional`/`queryAllOptional` no longer make the request to find out a module is
// absent — the shell's `installedModules` (module-sdk) short-circuits from the live ACTIVE module
// set, so an optional integration that is not installed leaves no `POST /api/query` at all.
test('panel loads fire no GET /api/query and no /api/query failure', async ({ page }) => {
  const session = await loginByPin();
  await withSession(page, session);

  const strayGets: string[] = [];
  const failedQueries: string[] = [];
  let legitimatePosts = 0;
  page.on('request', (r) => {
    if (new URL(r.url()).pathname !== '/api/query') return;
    if (r.method() !== 'POST') {
      strayGets.push(`${r.method()} ${r.url()}`);
    } else {
      legitimatePosts += 1;
    }
  });
  page.on('response', (r) => {
    if (new URL(r.url()).pathname === '/api/query' && r.status() >= 400) {
      failedQueries.push(`${r.status()} ${r.request().method()} ${r.url()}`);
    }
  });

  // Core panels (always present, module-independent).
  for (const route of ['/dashboard', '/apps', '/settings', '/employees', '/system']) {
    await page.goto(route);
    await page.waitForLoadState('networkidle');
  }

  // Installed-module panels, when there are any (dev stack); an empty hub yields none.
  const nav = await page.evaluate(async () => {
    const res = await fetch('/api/navigation', {
      headers: { 'X-Hub-Session': localStorage.getItem('erplora.hub_session') ?? '' },
    });
    if (!res.ok) return [];
    const body = await res.json();
    const items: Array<{ module_id?: string }> = Array.isArray(body) ? body : (body.data ?? []);
    return items.map((n) => n.module_id).filter((id): id is string => Boolean(id));
  });
  const modulePanels = [...new Set(nav)].slice(0, 4);
  for (const moduleId of modulePanels) {
    await page.goto(`/m/${moduleId}`);
    await page.waitForLoadState('networkidle');
  }

  expect(strayGets, 'nothing may request /api/query with a method other than POST').toEqual([]);
  expect(failedQueries, 'no /api/query call on a panel load may fail (console noise)').toEqual([]);
  if (modulePanels.length > 0) {
    // Guard against a vacuous green: with module panels visited, real query traffic must have
    // flowed through the observed endpoint (otherwise the session/router broke and we saw nothing).
    expect(legitimatePosts, 'module panels must fire POST /api/query').toBeGreaterThan(0);
  }
});
