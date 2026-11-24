// The assistant's card for a write of Time clock (BASE-F97): the person a clocking acts on and the working day a
// correction rewrites, by the name the screens give them, never by the id the model sent, and never left out for
// whoever may read them. End to end
// with the stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be
// seeded with it (README of this folder, «El asistente»). The owner, in Spanish, asks to clock someone of the team in
// (ATTENDANCE-F12) and to correct that person's day (ATTENDANCE-F08, dangerous): each card names her; cancelled, nothing
// changes. What this file creates carries `E2EAac` and goes away; the apps it turns on are turned off again.
// A break said with the person's first name says it is a break and names the person the clocking finds (hub#2297).
// flow: attendance-assistant-card
// flow: ATTENDANCE-F12 ATTENDANCE-F08 ATTENDANCE-F02 BASE-F97

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { cardSpec } from './assistant-card-helpers';
import { askForACard, cancelAtComputerSize, captureConfirmation, card, openPanelAtTheDesk } from './assistant-panel';
import { A, api, capture, login, psql, THREE_SIZES as VIEWPORTS, untilStill } from './helpers';

const KEY = 'FIX-HUB-ATTENDANCE-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS';
const TAG = 'E2EAac';
/** The apps a clocking needs: a business is born with every app off. */
const NEEDED = ['staff', 'attendance'];
const RECORDS = `select id from attendance_record where member_id in (select id from staff_member where first_name like '${TAG}%')`;

type Day = { id: string; status: string; clock_in_at: string; clock_out_at: string | null; correction_count: number };
type Detail = Day & { name: string };


function cleanup(): void {
  psql(
    [
      `delete from attendance_correction where record_id in (${RECORDS})`,
      `delete from attendance_break where record_id in (${RECORDS})`,
      `delete from attendance_record where id in (${RECORDS})`,
      `delete from staff_member where first_name like '${TAG}%'`,
    ].join('; '),
  );
}

cardSpec(NEEDED, cleanup);

/** The owner, in Spanish, with a person of the team made through Staff's API: `[context, page, her id, her name]`. */
async function ownerWithBea(browser: import('@playwright/test').Browser): Promise<[BrowserContext, Page, string, string]> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const created = await api<{ id: string }>(context, A, 'POST', '/staff/members', { first_name: `${TAG}Bea`, last_name: 'Ruiz' });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  return [context, page, created.data.id, `${TAG}Bea Ruiz`];
}

async function daysOf(context: BrowserContext, memberId: string): Promise<Day[]> {
  const page = await api<{ rows: Day[] }>(context, A, 'GET', `/attendance/records?member_id=${memberId}`);
  expect(page.status, JSON.stringify(page.data)).toBe(200);
  return page.data.rows;
}

test('attendance-assistant-card — in Spanish clocking someone else in names them on the card, never by their id', async ({ browser }) => {
  const [context, page, bea, name] = await ownerWithBea(browser);
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-ASK attendance__record__clock_in ${JSON.stringify({ member_id: bea })}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Fichar la entrada en Control horario: ${name}`);
    await expect(card(page)).not.toContainText(bea);
    await untilStill(page);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  expect(await daysOf(context, bea)).toEqual([]);
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

test('attendance-assistant-card — in Spanish correcting a working day names it by its person and its day, never by its id', async ({ browser }) => {
  const [context, page, bea, name] = await ownerWithBea(browser);
  for (const write of ['/attendance/clock_in', '/attendance/clock_out']) {
    const done = await api(context, A, 'POST', write, { member_id: bea });
    expect(done.status, `${write}: ${JSON.stringify(done.data)}`).toBe(200);
  }
  const [day] = await daysOf(context, bea);
  // Named as «Correct working day» names it, in the reader's language: read through the API in Spanish.
  const detail = await api<Detail>(context, A, 'GET', `/attendance/records/detail?id=${day.id}`);
  expect(detail.status, JSON.stringify(detail.data)).toBe(200);
  expect(detail.data.name).toMatch(new RegExp(`^${name} · \\d{1,2} [a-z]{3,4} \\d{4}$`));
  await openPanelAtTheDesk(page);
  const correction = { record_id: day.id, clock_in_at: day.clock_in_at, clock_out_at: day.clock_out_at, reason: 'Olvidó fichar' };
  await askForACard(page, `E2E-ASK attendance__record__correct ${JSON.stringify(correction)}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Jornada: ${detail.data.name}`);
    await expect(card(page)).not.toContainText(day.id);
    await captureConfirmation(page, `${KEY}-correct-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  const [after] = await daysOf(context, bea);
  expect([after.clock_in_at, after.correction_count]).toEqual([day.clock_in_at, 0]);
  await context.close();
});

test('attendance-assistant-card — a break asked for by the first name says it is a break and whose', async ({ browser }) => {
  const [context, page, bea, name] = await ownerWithBea(browser);
  const clockedIn = await api(context, A, 'POST', '/attendance/clock_in', { member_id: bea });
  expect(clockedIn.status, JSON.stringify(clockedIn.data)).toBe(200);
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-ASK attendance__break__start ${JSON.stringify({ member: `${TAG.toLowerCase()}bea` })}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Empezar la pausa en Control horario: ${name}`);
    await untilStill(page);
    await capture(page, `${KEY}-break-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  expect(psql(`select count(*) from attendance_break where record_id in (${RECORDS})`).trim()).toBe('0');
  await context.close();
});
