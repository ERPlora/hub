// The apps a spec file needs, turned on in the business through Apps' own commands and turned off again after it.
import { type BrowserContext, expect } from '@playwright/test';

import { turnOffRecorded, turnOnRecording } from './apps-turned-on';
import { api } from './hub-api';

/** How long the run's worker may take to make an app's tables in a business's own database: its tick, the
 *  migrations of the app and what it needs, and its settle. */
export const APP_SET_UP_MS = 60_000;

/**
 * Turns on `apps` in the business at `origin`, as the person of `context` who runs it, through Apps' own command
 * (`POST /api/apps/enable`, `base.app.enable`): a business is born with every app off.
 * One already on changes nothing. In a business whose own database lacks an app's tables (a demo, a new business)
 * the answer is 202 «creating» and the run's worker makes them: it waits until `base.app.list` says it is on.
 */
export async function turnOn(context: BrowserContext, origin: string, ...apps: string[]): Promise<void> {
  for (const app of apps) {
    const answer = await api<{ state: string }>(context, origin, 'POST', '/apps/enable', { app });
    const said = `turn on ${app}: ${answer.status} ${JSON.stringify(answer.data)}`;
    expect([200, 202], said).toContain(answer.status);
    if (answer.status === 202) {
      expect(answer.data.state, said).toBe('creating');
      await expect
        .poll(
          async () => {
            const listed = await api<{ apps: { id: string; state: string }[] }>(context, origin, 'GET', '/apps');
            return listed.data.apps.find((row) => row.id === app)?.state;
          },
          { message: `${app} set up by the worker`, timeout: APP_SET_UP_MS },
        )
        .toBe('on');
    }
  }
}

/**
 * Turns on, in their order, the apps of `needed` that are off in the business at `origin` (`turnOn`), and appends each
 * to `turnedOn` once it is on: the record a spec file's `afterAll` hands to `turnOffTurnedOn`, so it turns off what
 * this file turned on and nothing else. Called from a `beforeAll`, after whatever may fall first (the check of the
 * SaaS's assistant provider): a file that fell before turning anything on leaves the business as it found it (hub#480).
 */
export async function turnOnMissing(context: BrowserContext, origin: string, needed: readonly string[], turnedOn: string[]): Promise<void> {
  const listed = await api<{ apps: { id: string; state: string }[] }>(context, origin, 'GET', '/apps');
  expect(listed.status, `list the apps: ${JSON.stringify(listed.data)}`).toBe(200);
  const on = new Set(listed.data.apps.filter((app) => app.state === 'on').map((app) => app.id));
  await turnOnRecording(needed, on, (app) => turnOn(context, origin, app), turnedOn);
}

/** Turns off, last first, what `turnOnMissing` recorded in `turnedOn`, through Apps' own command
 *  (`POST /api/apps/disable`, `base.app.disable`): nothing when nothing was turned on (hub#480). */
export async function turnOffTurnedOn(context: BrowserContext, origin: string, turnedOn: string[]): Promise<void> {
  await turnOffRecorded(turnedOn, async (app) => {
    const off = await api(context, origin, 'POST', '/apps/disable', { app });
    expect(off.status, `turn off ${app}: ${JSON.stringify(off.data)}`).toBe(200);
  });
}
