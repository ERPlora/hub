// What the e2e of the assistant's confirmation card shares (BASE-F97): the hooks of a spec that asks for a write through
// the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`; the SaaS seeded with it, README «El asistente»),
// around the spec's own cleaning and the apps it needs, and the data its card names, never by an id. The panel and the
// card as a person drives them are in assistant-panel.ts.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import type { Provider } from './assistant-provider';
import { ask, card, confirmedCard, type SentCard } from './assistant-panel';
import { emptyMonth } from './assistant-real';
import { A, api, login, turnOffTurnedOn, turnOnMissing } from './helpers';
import { seededProvider } from './provider-helpers';

/** An id as a schema's `format: uuid` takes it: never on a card. */
export const AN_ID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
export const VIEWPORTS = [
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1440x900', width: 1440, height: 900 },
];
/** How long the first turn of a stack that just started may take. */
const FIRST_TURN_MS = 120_000;

/** Registers the hooks of a spec of the card: the provider, the apps `needed` turned on (a business is born with every
 *  app off) and off again after, only those it turned on, and `cleanUp` before each test and after the last. */
export function cardSpec(needed: string[], cleanUp: () => void): void {
  let provider: Provider | undefined;
  const turnedOn: string[] = [];
  test.beforeAll(async ({ browser }) => {
    provider = await seededProvider();
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page, A, '/');
    await turnOnMissing(context, A, needed, turnedOn);
    // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    await context.close();
  });
  test.beforeEach(() => {
    emptyMonth();
    cleanUp();
  });
  test.afterAll(async ({ browser }) => {
    cleanUp();
    const context = await browser.newContext();
    const page = await context.newPage();
    await login(page, A, '/');
    await turnOffTurnedOn(context, A, turnedOn);
    await context.close();
    await provider?.close();
  });
}

/** Asks for the write `tool` and returns what its card sends, never saying an id on the way. */
export async function fieldsOf(page: Page, tool: string, data: Record<string, unknown>): Promise<SentCard['fields']> {
  const answer = page.waitForResponse(
    async (response) => response.url().endsWith('/api/assistant/turn') && confirmedCard(await response.text()) !== undefined,
    { timeout: FIRST_TURN_MS },
  );
  await ask(page, `E2E-ASK ${tool} ${JSON.stringify(data)}`, { settle: false });
  // The card comes with the answer of the turn, which waits for the gateway: seconds on a stack that just started.
  const { fields } = confirmedCard(await (await answer).text())!;
  await expect(card(page)).toBeVisible();
  expect(JSON.stringify(fields)).not.toMatch(AN_ID);
  await expect(card(page)).not.toContainText(AN_ID);
  return fields;
}

/** The datum `name` of the card of `tool`. */
export async function datumOf(
  page: Page,
  tool: string,
  data: Record<string, unknown>,
  name = 'id',
): Promise<SentCard['fields'][number]> {
  const fields = await fieldsOf(page, tool, data);
  const field = fields.find((one) => one.name === name);
  expect(field, `the card of ${tool} names no ${name}: ${JSON.stringify(fields)}`).toBeDefined();
  return field!;
}

/** A device of `a`, as Settings › Devices lists it. */
export type Device = { id: string; name: string; agent: string; current: boolean };

/** The device `id` named `name`, as the business names it in Settings › Devices. */
async function renameDevice(context: BrowserContext, id: string, name: string): Promise<void> {
  const renamed = await api(context, A, 'POST', '/devices/rename', { id, name });
  expect(renamed.status, JSON.stringify(renamed.data)).toBe(200);
}

/** The device of this session (or the first one) named `name`, as the business names it in Settings › Devices;
 *  `stays` checks it is still among the devices and gives it its name back. */
export async function thisDeviceNamed(context: BrowserContext, name: string): Promise<{ device: Device; stays: () => Promise<void> }> {
  const listed = await api<{ devices: Device[] }>(context, A, 'GET', '/devices');
  expect(listed.status, JSON.stringify(listed.data)).toBe(200);
  const device = listed.data.devices.find((row) => row.current) ?? listed.data.devices[0];
  expect(device, JSON.stringify(listed.data.devices)).toBeDefined();
  await renameDevice(context, device.id, name);
  const stays = async (): Promise<void> => {
    const after = await api<{ devices: Device[] }>(context, A, 'GET', '/devices');
    expect(after.data.devices.map((row) => row.id)).toContain(device.id);
    await renameDevice(context, device.id, device.name);
  };
  return { device, stays };
}
