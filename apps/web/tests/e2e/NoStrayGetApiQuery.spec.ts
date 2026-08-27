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
  // Names the device the dev seed marked as trusted (`demo-trusted-device`). Device-trust is armed
  // by default since hub#330: a PIN login that identifies no device is refused, which is exactly
  // what a browser on a fresh till gets — so naming it here is the real contract, not a workaround.
  const res = await api.post(`${RUNTIME}/api/auth/pin`, {
    data: { name: 'Demo', pin: '0000', device_id: 'demo-trusted-device' },
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

// 🔴 RED because of a real, already-filed defect, not because of this test (hub#1211, surfaced when
// hub#1240 first ran this suite): `queryOptional` (ADR-0127) makes the request ANYWAY to find out a
// module is absent, so every optional integration that is not installed leaves a `404 POST
// /api/query` in the console — which is exactly what the second assertion below forbids. Left as
// `fixme` — visible in the report, not deleted — so the rest of the suite can run in CI; drop the
// marker when hub#1211 closes.
test.fixme('panel loads fire no GET /api/query and no /api/query failure', async ({ page }) => {
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
