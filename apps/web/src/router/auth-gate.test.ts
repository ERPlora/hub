// @vitest-environment happy-dom
//
// hub#858 — the reproduction of the double login, at the exact place where it happened.
//
// Someone signs up on the SaaS from the installed app, creates their hub, the app jumps to it…
// and the hub asks for email + password again. The credential was never missing: the SaaS already
// hands a one-time courier in the redirect fragment and the runtime already redeems it. What broke
// is TIMING — `app.use(router)` starts the initial navigation at module evaluation, so the auth
// gate answered "no session → /login" while the exchange that opens the session was still in
// flight. Once it landed, the shell chrome rendered as authenticated around a login form
// (QA evidence: `13-hub-listo.png`).
//
// So the contract under test is about WHEN the gate answers, not about what credential travels:
// while a courier boot is in flight, the gate must not decide.
import { beforeEach, describe, expect, it } from 'vitest';
import type { RouteLocationNormalized } from 'vue-router';

import { armCourierBoot, settleCourierBoot } from '../lib/courier';
import { setUser } from '../lib/session';
import { authGate } from './index';

/** The handful of fields the gate reads off a route. */
function route(partial: Partial<RouteLocationNormalized>): RouteLocationNormalized {
  return {
    name: 'dashboard',
    path: '/dashboard',
    fullPath: '/dashboard',
    hash: '',
    query: {},
    params: {},
    meta: { auth: true },
    ...partial,
  } as unknown as RouteLocationNormalized;
}

const ANA = { id: 'local-1', name: 'Ana', email: 'ana@example.com', role: 'owner', permissions: ['*'] };

describe('auth gate', () => {
  beforeEach(() => {
    settleCourierBoot();
    setUser(null);
    localStorage.clear();
  });

  it('sends an anonymous visitor to /login when no courier is inbound', async () => {
    const decision = await authGate(route({}));
    expect(decision).toEqual({ name: 'login', query: { redirect: '/dashboard' } });
  });

  it('lets a session through', async () => {
    setUser(ANA);
    await expect(authGate(route({}))).resolves.toBe(true);
  });

  it('WAITS for an in-flight courier boot instead of bouncing the shell to /login (hub#858)', async () => {
    armCourierBoot();

    let decided = false;
    const decision = authGate(route({})).then((value) => {
      decided = true;
      return value;
    });

    // The gate must still be undecided: the courier has not landed yet.
    await Promise.resolve();
    await Promise.resolve();
    expect(decided).toBe(false);

    // The exchange lands and opens the local session, exactly as `bootCourier` does.
    setUser(ANA);
    settleCourierBoot();

    // …and now the gate lets the user INTO the hub. No second login, no email code.
    await expect(decision).resolves.toBe(true);
  });

  it('still lands on /login when the courier boot settles WITHOUT a session (expired code)', async () => {
    armCourierBoot();
    const decision = authGate(route({}));
    settleCourierBoot(); // exchange rejected: no session was opened
    await expect(decision).resolves.toEqual({ name: 'login', query: { redirect: '/dashboard' } });
  });

  it('does not strand an authenticated shell on /login once the courier lands', async () => {
    // The other half of the same race: the initial navigation may already BE /login (the guard
    // redirected there before the exchange landed). Reaching /login with a live session belongs
    // inside the hub.
    setUser(ANA);
    await expect(authGate(route({ name: 'login', path: '/login', fullPath: '/login', meta: {} })))
      .resolves.toEqual({ path: '/' });
  });
});
