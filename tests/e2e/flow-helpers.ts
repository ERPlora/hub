// What the specs of Automations share (apps/flow): a signed-in context in a size, picking in an `IonSelect`
// popover, confirming a dialog, the id of the automation the editor shows, and the API setup of an
// automation (the screens under test build their own steps; the API only sets the stage).
import { execFileSync } from 'node:child_process';

import { type Browser, type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, type Credentials, HUB_DIR, login, OWNER, psql, shown } from './helpers';
import { OUTBOUND_AT_ONCE } from './whatsapp-helpers';

export async function signedIn(
  browser: Browser,
  next: string,
  viewport: { width: number; height: number },
  credentials: Credentials = OWNER,
) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

/** Picks `text` in the popover of the `IonSelect` `testid` of the page shown. */
export async function choose(page: Page, testid: string, text: string): Promise<void> {
  await shown(page).locator(`[data-testid="${testid}"]`).click();
  const popover = page.locator('ion-popover.select-popover:not(.overlay-hidden)');
  await popover.locator('ion-radio', { hasText: text }).first().click();
  await expect(popover).toHaveCount(0);
}

/** Confirms the dialog titled `title` with its main button. */
export async function confirmDialog(page: Page, title: string, beforeConfirm?: () => Promise<void>): Promise<void> {
  const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: title });
  await expect(dialog.locator('.ep-form-modal__submit')).toBeInViewport();
  if (beforeConfirm) await beforeConfirm();
  await dialog.locator('.ep-form-modal__submit').click();
  await expect(dialog).toBeHidden();
}

export const idFromUrl = (page: Page): string => new URL(page.url()).pathname.split('/').at(-1)!;

/** An automation that starts by hand, made through the API with `steps` and `grants`, switched on. */
export async function manualFlow(context: BrowserContext, name: string, steps: unknown[], grants: string[]): Promise<string> {
  const created = await api<{ id: string }>(context, A, 'POST', '/flow/flows', { name, trigger: { kind: 'manual' }, steps });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  const id = created.data.id;
  if (grants.length) expect((await api(context, A, 'POST', '/flow/flows/grant', { id, operations: grants })).status).toBe(200);
  expect((await api(context, A, 'POST', '/flow/flows/set_enabled', { id, enabled: true })).status).toBe(200);
  return id;
}

/** Python for a one-shot `manage.py shell` playing the worker's relay to flow (in `a`'s database; the stack's worker relays too): the
 *  outbox event `FLOW_EVENT`, handed to flow's reaction as the relay does on every tick. What that reaction leaves
 *  for after its COMMIT (the call of FLOW-F27, the question to the assistant of FLOW-F38) goes to `base.outbound`'s
 *  threads, which would die with this process before making it: `OUTBOUND_AT_ONCE` makes it at once
 *  (FIX-HUB-FLOW-E2E-WORKER-CALLS-DIE-WITH-ONE-SHOT-SHELL). */
export const RELAY = `${OUTBOUND_AT_ONCE}
import os
from django.db import transaction
from live.models import OutboxEvent
from base import relay
event = OutboxEvent.objects.get(pk=os.environ["FLOW_EVENT"])
with transaction.atomic():
    relay.deliver("flow", event)
`;

/** The newest `flow.run.parked` of the automation `flowId` in the outbox: what the worker hands flow's reaction. */
export function parkedEvent(flowId: string): string {
  const event = psql(
    `select id from live_outboxevent where name = 'flow.run.parked' and payload->>'flow_id' = '${flowId}' order by created_at desc, id desc limit 1`,
  );
  expect(event, `flow.run.parked of ${flowId} in the outbox`).not.toBe('');
  return event;
}

/** The worker's part of a call (FLOW-F27): the newest `flow.run.parked` of the automation `flowId`, handed to
 *  flow's reaction as the outbox relay does on every tick (`RELAY`); the call goes out after that COMMIT, never
 *  from the request that parked it. */
export function workerCalls(flowId: string): void {
  execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', RELAY], {
    cwd: HUB_DIR,
    encoding: 'utf8',
    env: { ...process.env, FLOW_EVENT: parkedEvent(flowId) },
  });
}
