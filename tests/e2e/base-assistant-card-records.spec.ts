// How the card of the Hub's assistant names the records a write sends by their id, in Spanish, set up as in
// base-assistant.spec.ts: as their own screens name them, never by the id.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { thisDeviceNamed } from './assistant-card-helpers';
import { askForACard, cancelAtComputerSize, captureConfirmation, captureStill, card, leave, openPanelAtTheDesk, openPanelInSpanish, ownerIn, signedInWith } from './assistant-panel';
import { A, api, login, THREE_SIZES as VIEWPORTS, turnOnMissing } from './helpers';
import { panelSpec } from './provider-helpers';

panelSpec();

/** The words the record at `path` is named by, as its read by id answers them in the person's language: `<name> · …`,
 *  with no date as the database keeps it. */
async function labelRead(context: BrowserContext, path: string, name: string): Promise<string> {
  const read = await api<{ label: string }>(context, A, 'GET', path);
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  const label = read.data.label;
  expect(label.startsWith(`${name} · `), label).toBe(true);
  expect(label, label).not.toMatch(/\d{4}-\d{2}-\d{2}/);
  return label;
}

/** A business is born with every app off: Appointments and the apps it needs, off again at the end if they were. */
const CITAS = ['customer', 'service', 'staff', 'schedule', 'appointment'];
/** A customer, a service and a professional by ids that name nothing in this business: the card leaves them out. */
const [CUSTOMER_ID, SERVICE_ID, MEMBER_ID] = [
  '0192f0b2-1111-7000-8000-000000000001',
  '0192f0b2-2222-7000-8000-000000000002',
  '0192f0b2-3333-7000-8000-000000000003',
];

/** Asks for a booking of `services` on 2 Nov 2026 at 10:00 through the front desk, its customer and professional by
 *  `CUSTOMER_ID` and `MEMBER_ID`, and checks at each size that its card says `line` and none of `never`, saved as `key`. */
async function bookingCardSays(page: Page, services: unknown[], line: string, never: readonly string[], key: string): Promise<void> {
  const booking = { customer_id: CUSTOMER_ID, services, staff_id: MEMBER_ID, start: '2026-11-02T10:00:00+01:00', source: 'counter' };
  await askForACard(page, `E2E-ASK appointment__appointment__create ${JSON.stringify(booking)}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(line);
    for (const raw of never) await expect(card(page)).not.toContainText(raw);
    await captureStill(page, `${key}-${vp.label}`);
  }
}

// flow: assistant-card (BASE-F97)
// A booking's card says its day and time as the person's language writes them, at the business's hour, its channel by
// the label Appointments gives it, and nobody by an id. Cancelled: nothing is booked.
test('assistant-card — in Spanish a booking says its day and time and its channel in words, and nobody by an id', async ({ browser }) => {
  const { context, page, turnedOn } = await signedInWith(browser, CITAS);
  await openPanelInSpanish(page);
  const raw = ['2026-11-02', '+01:00', 'counter', CUSTOMER_ID, SERVICE_ID, MEMBER_ID];
  const line = 'Crear en Citas: 2 nov 2026, 10:00 · Servicios: 1 elemento · Reservada por: Mostrador';
  await bookingCardSays(page, [{ service_id: SERVICE_ID }], line, raw, 'FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-RAW-VALUES');
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

// flow: assistant-card (BASE-F97)
// hub#860: with no id, the assistant sends a booking's service as a person says it («Tinte») and the card said «1
// elemento»: now it says the service by that name, with the day, the time and the channel in words. Cancelled: nothing
// is booked.
test('assistant-card — in Spanish a booking whose service comes by its name says that name, never how many', async ({ browser }) => {
  const { context, page, turnedOn } = await signedInWith(browser, CITAS);
  await openPanelInSpanish(page);
  const line = 'Crear en Citas: 2 nov 2026, 10:00 · Servicios: Tinte · Reservada por: Mostrador';
  await bookingCardSays(page, [{ service: 'Tinte' }], line, ['elemento', CUSTOMER_ID, MEMBER_ID], 'hub-860-service-by-name');
  await cancelAtComputerSize(page);
  await leave(context, turnedOn);
});

// flow: assistant-card (BASE-F97)
// A write of the platform that names its record by an id says which one as its screen does: a device by its name or,
// with none, by what it is, as Settings › Devices. Revoking an API key names its key the same way, covered in
// base/tests. Cancelled: the device stays.
test('assistant-card — in Spanish removing a device names it as Settings › Devices does, never by its id', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-RAW-VALUES-device';
  const [context, page] = await ownerIn(browser, 'es');
  // Named as the business names it in Settings › Devices (headless Chromium says no browser it knows, so it has nothing
  // else to be said by), and given its name back at the end.
  const { device, stays } = await thisDeviceNamed(context, 'Barra');
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-ASK base__device__remove {"id":"${device!.id}"}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Quitar en Ajustes. Revisa cada dato antes de seguir.');
    // The record by the title its schema gives it, never «Registro».
    await expect(card(page)).toContainText('Dispositivo: Barra');
    await expect(card(page)).not.toContainText(device!.id);
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await stays();
  await context.close();
});

// flow: RESERVATION-F06 RESERVATION-F08 (the card: BASE-F97)
// Every record a write of Reservations names by its id goes by the name its screen gives it, read as the person:
// booking says the customer by the name of their card (and the day and the time: a normal card's line carries its first
// three data); moving a reservation to another table says which reservation, as the book's own dialog does (its guest,
// its day and its time), and the table by its number. Cancelled: nothing is booked nor moved. What the test made is
// deleted at the end.
test('RESERVATION-F06 — booking a table, the card names the customer; moving a reservation, the reservation and its new table; never by an id', async ({ browser }) => {
  const KEY = 'FIX-HUB-RESERVATION-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const needed = ['customer', 'table', 'schedule', 'reservation'];
  const turnedOn: string[] = [];
  await turnOnMissing(context, A, needed, turnedOn);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const made = async <T>(path: string, body: unknown): Promise<T> => {
    const answer = await api<T>(context, A, 'POST', path, body);
    expect(answer.status, `${path}: ${JSON.stringify(answer.data)}`).toBe(201);
    return answer.data;
  };
  // A week from today, on the business's calendar (Madrid), at 21:30: always ahead, whenever the suite runs.
  const ahead = new Date(Date.now() + 7 * 24 * 3600 * 1000);
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Madrid' }).format(ahead);
  const weekday = (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
  const stamp = String(Date.now() % 100_000_000).padStart(8, '0');
  const name = `Ana García ${stamp.slice(-4)}`;
  const phone = `+346${stamp}`;
  const customer = await made<{ id: string }>('/customer/customers', { name, phone });
  const zone = await made<{ id: string }>('/table/zones', { name: `E2E Card ${stamp}` });
  const table = await made<{ id: string; number: string }>('/table/tables', { zone_id: zone.id, number: '7', capacity: 4 });
  // The book takes reservations in a slot; one of the stack's own already covering that evening serves as well.
  const slot = await api<{ id: string }>(context, A, 'POST', '/reservation/time_slots', {
    day_of_week: weekday, start_time: '21:00', end_time: '23:30', max_reservations: 10,
  });
  expect([201, 409], JSON.stringify(slot.data)).toContain(slot.status);
  const booked = await made<{ id: string }>('/reservation/reservations', {
    customer_id: customer.id, guest_phone: phone, date, time: '21:30', party_size: 2, source: 'in_person',
  });
  // The words the book names it by, as its read by id answers them in the person's language («Ana García 1234 · 6 nov
  // 2026 · 21:30»): what the card must say of it.
  const label = await labelRead(context, `/reservation/reservations/detail?id=${booked.id}`, name);
  const ids = [customer.id, table.id, booked.id];
  // A new booking's card says the same three, its day and time by their names: «Ana García 1234 · Fecha: 6 nov 2026 ·
  // Hora: 21:30».
  const [who, day, hour] = label.split(' · ');
  const created = `Crear en Reservas: ${who} · Fecha: ${day} · Hora: ${hour}`;

  await openPanelAtTheDesk(page);
  // Booking: for whom (the customer's card by its name), the day and the time; the table goes among its data, with its
  // zone (hub#550).
  const booking = { customer_id: customer.id, date, time: '21:30:00', party_size: 2, table_id: table.id, source: 'in_person' };
  await askForACard(page, `E2E-ASK reservation__reservation__create ${JSON.stringify(booking)}`);
  await expect(card(page)).toContainText(created);
  for (const raw of [date, 'in_person', ...ids]) await expect(card(page)).not.toContainText(raw);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(created);
    await captureStill(page, `${KEY}-create-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  // The customer said by her name, with the same guest name and her phone: the name once, then the day and the time
  // (hub#2169: «Ana García · Ana García · <phone>»).
  const said = { customer: name, guest_name: name, guest_phone: phone, date, time: '21:30', party_size: 2, source: 'phone' };
  await askForACard(page, `E2E-ASK reservation__reservation__create ${JSON.stringify(said)}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(created);
    await captureStill(page, `${KEY}-create-said-${vp.label}`);
  }
  await cancelAtComputerSize(page);

  // Moving it to table 7: which reservation, as the book's dialog says it, and the new table with its zone, as Tables
  // names it («7 (E2E Card …)»: the number repeats across zones, hub#550).
  await askForACard(page, `E2E-ASK reservation__reservation__update ${JSON.stringify({ id: booked.id, table_id: table.id })}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Cambiar en Reservas: ${label} · Mesa: 7 (E2E Card ${stamp})`);
    for (const raw of [date, ...ids]) await expect(card(page)).not.toContainText(raw);
    await captureStill(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  const after = await api<{ table_id: string | null }>(context, A, 'GET', `/reservation/reservations/detail?id=${booked.id}`);
  expect(after.data.table_id).toBeNull();

  // What the test made, deleted; and the apps it turned on, off again.
  const gone = async (path: string, id: string) => {
    const answer = await api(context, A, 'POST', path, { id });
    expect(answer.status, `${path}: ${JSON.stringify(answer.data)}`).toBe(200);
  };
  await gone('/reservation/reservations/delete', booked.id);
  if (slot.status === 201) await gone('/reservation/time_slots/delete', slot.data.id);
  await gone('/table/tables/delete', table.id);
  await gone('/table/zones/delete', zone.id);
  await gone('/customer/customers/delete', customer.id);
  await leave(context, turnedOn);
});

// flow: FLOW-F03 FLOW-F24 (the card: BASE-F97)
// Every record a write of Automations names by its id (automation, draft, run, question) goes by the name its screen
// gives it, read as the person: pausing an automation says it by its name; resuming a run that stopped by an error says
// it as the History does, with its automation in front («Bienvenida 1234 · 6 nov 2026, 21:30»). Both are dangerous: the
// card lists each datum and asks to type. Cancelled: nothing is paused nor resumed. What the test made is deleted at
// the end.
test('FLOW-F03 — pausing an automation, the card names it; resuming a run, its automation and when; never by an id', async ({ browser }) => {
  const KEY = 'FIX-HUB-FLOW-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const needed = ['task', 'flow'];
  const turnedOn: string[] = [];
  await turnOnMissing(context, A, needed, turnedOn);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const stamp = String(Date.now() % 10_000).padStart(4, '0');
  const name = `Bienvenida ${stamp}`;
  // On by hand, one step that creates a task and no permission granted: run now, it stops by an error at that step.
  const created = await api<{ id: string }>(context, A, 'POST', '/flow/flows', {
    name,
    trigger: { kind: 'manual' },
    steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: `E2E ${stamp}` } }],
  });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  const flow = created.data;
  const on = await api(context, A, 'POST', '/flow/flows/set_enabled', { id: flow.id, enabled: true });
  expect(on.status, JSON.stringify(on.data)).toBe(200);
  const ran = await api<{ id: string; status: string }>(context, A, 'POST', '/flow/flows/run', { id: flow.id });
  expect(ran.status, JSON.stringify(ran.data)).toBe(200);
  expect(ran.data.status).toBe('failed');
  // The words the History names the run by, as its read by id answers them in the person's language: what the card says.
  const label = await labelRead(context, `/flow/runs/detail?id=${ran.data.id}`, name);

  await openPanelAtTheDesk(page);
  // Pausing it: which automation, by its name.
  await askForACard(page, `E2E-ASK flow__flow__set_enabled ${JSON.stringify({ id: flow.id, enabled: false })}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Cambiar en Automatizaciones. Revisa cada dato antes de seguir.');
    await expect(card(page)).toContainText(`Automatización: ${name}`);
    await expect(card(page)).toContainText('Encendida: No');
    await expect(card(page)).not.toContainText(flow.id);
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);

  // Resuming the run: which one, as the History says it, with its automation in front.
  await askForACard(page, `E2E-ASK flow__run__retry ${JSON.stringify({ id: ran.data.id })}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Reintentar en Automatizaciones. Revisa cada dato antes de seguir.');
    await expect(card(page)).toContainText(`Ejecución: ${label}`);
    await expect(card(page)).not.toContainText(ran.data.id);
    await captureConfirmation(page, `${KEY}-run-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  const after = await api<{ enabled: boolean }>(context, A, 'GET', `/flow/flows/detail?id=${flow.id}`);
  expect(after.data.enabled).toBe(true);
  const still = await api<{ status: string }>(context, A, 'GET', `/flow/runs/detail?id=${ran.data.id}`);
  expect(still.data.status).toBe('failed');

  // What the test made, deleted (its history stays, as Automations keeps it); and the apps it turned on, off again.
  const gone = await api(context, A, 'POST', '/flow/flows/delete', { id: flow.id });
  expect(gone.status, JSON.stringify(gone.data)).toBe(200);
  await leave(context, turnedOn);
});
