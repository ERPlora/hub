// The card of the Hub's assistant end to end, set up as in base-assistant.spec.ts: a write waits on it, a dangerous one
// asks to type its word and says what will happen, and what the person may not do is refused.
import { expect, test } from '@playwright/test';

import { answers, ask, askForACard, cancelAtComputerSize, captureConfirmation, card, confirmationReady, confirmationSettled, decide, freshPage, lastAnswer, lastAnswerAtEachSize, openPanelAtTheDesk, panel, panelAtTheDesk, shots } from './assistant-panel';
import { DONE, NOT_DONE, STEPS_SAID } from './assistant-provider';
import { A, api, EMPLOYEE, login, THREE_SIZES as VIEWPORTS } from './helpers';
import { panelSpec } from './provider-helpers';

const provider = panelSpec();

test('a write waits on its card: «Run it» runs it as the person; «Cancel» runs nothing', async ({ page, context }) => {
  await panelAtTheDesk(page);
  const name = `Mesa asistente ${Date.now().toString(36)}`;
  await askForACard(page, `E2E-CREATE ${name}`);
  await expect(card(page)).toContainText('Run this action?');
  await expect(card(page)).toContainText(`Create in Demo: ${name}`);
  await shots(page, 'BASE-G115', () => expect(card(page)).toBeVisible());
  await page.setViewportSize({ width: 1440, height: 900 });
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText(DONE.en);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Done: Create in Demo');
  const made = await api<{ rows: { name: string }[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`);
  expect(made.data.rows.map((row) => row.name)).toEqual([name]);

  const other = `${name} no`;
  await askForACard(page, `E2E-CREATE ${other}`);
  await decide(page, 'cancel');
  await expect(lastAnswer(page)).toContainText(NOT_DONE.en);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Not done, cancelled: Create in Demo');
  const none = await api<{ rows: unknown[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(other)}`);
  expect(none.data.rows).toEqual([]);
});

test('several things in a row: the read runs by itself, the write waits on its card', async ({ page, context }) => {
  await panelAtTheDesk(page);
  const name = `Mesa cadena ${Date.now().toString(36)}`;
  await askForACard(page, `E2E-CHAIN ${name}`);
  await expect(card(page)).toContainText(`Create in Demo: ${name}`);
  await decide(page, 'submit');
  await expect(lastAnswer(page)).toContainText(DONE.en);
  // The read went to the model with its result, without a card; one message spent for the whole turn.
  const chats = provider().seen.filter((s) => s.path === '/v1/chat/completions').slice(-3);
  expect(JSON.stringify(chats[1].body)).toContain('"role":"tool"');
  const made = await api<{ rows: { name: string }[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`);
  expect(made.data.rows.map((row) => row.name)).toEqual([name]);
  await shots(page, 'BASE-G119');
});

// flow: BASE-F101 (asking for several things in a row)
test('BASE-F101 — several things in a row: what each round says is its own paragraph of the one bubble, never glued to the previous one', async ({ page }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-ROUNDS-TEXT-RUN-TOGETHER';
  await panelAtTheDesk(page);
  await askForACard(page, `E2E-STEPS Mesa pasos ${Date.now().toString(36)}`);
  await decide(page, 'cancel');
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: 30_000 });
  // Three rounds (before the read, before the write, after the card), one bubble, one paragraph each.
  await expect(answers(page)).toHaveCount(1);
  await expect(lastAnswer(page).locator('.assistant-md > p')).toHaveText([...STEPS_SAID.en, NOT_DONE.en]);
  await lastAnswerAtEachSize(page, KEY);
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
});

test('a dangerous write lists its data and runs only after typing the word', async ({ page, context }) => {
  await login(page, A, '/');
  const item = await api<{ id: string }>(context, A, 'POST', '/demo/items', { name: `Para borrar ${Date.now().toString(36)}` });
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-DELETE ${item.data.id}`);
  await expect(card(page)).toContainText('Delete in Demo. Check each detail before you continue.');
  // A record is never shown by its id; Demo marks no read that names it.
  await expect(card(page)).not.toContainText(item.data.id);
  // The native button inside `ion-button` (its host carries no role for `aria-disabled` to count).
  const submit = card(page).locator('[data-testid="assistant-confirm-submit"] button');
  await expect(submit).toBeDisabled();
  await shots(page, 'BASE-G116', () => confirmationReady(page), () => confirmationSettled(page));
  await page.setViewportSize({ width: 1440, height: 900 });
  const typing = card(page).locator('[data-testid="assistant-confirm-input"] input');
  // Typed wrong: «Run it» stays off and nothing is deleted.
  await typing.fill('confirmed');
  await expect(submit).toBeDisabled();
  expect((await api(context, A, 'GET', `/demo/items/detail?id=${item.data.id}`)).status).toBe(200);
  // Typed right, in its own way: what goes to the Hub is what was typed, which the server checks again (rv-hub-247).
  await typing.fill('  Confirm ');
  await expect(submit).toBeEnabled();
  const sent = page.waitForRequest((request) => request.url().endsWith('/api/assistant/turn') && Boolean(request.postDataJSON()?.decision));
  await decide(page, 'submit');
  expect((await sent).postDataJSON().decision).toMatchObject({ accepted: true, typed: '  Confirm ' });
  await expect(lastAnswer(page)).toContainText(DONE.en);
  const gone = await api(context, A, 'GET', `/demo/items/detail?id=${item.data.id}`);
  expect(gone.status).toBe(404);
});

// flow: BASE-F98 (dangerous actions: type to confirm) and BASE-F97 (the card)
// A dangerous write's card shows what it will do, not only what it sends: Base's «Remove the PIN» names whose PIN goes,
// as its read (`base.person.detail`) answers it to who asks. One whose preview cannot be read shows no card: nothing to
// confirm blind. Cancelled, and the second refused: nothing changes.
test('BASE-F98 — a dangerous card shows what will happen, as its app reads it for the person; one whose preview cannot be read shows no card', async ({ browser }) => {
  const KEY = 'FIX-HUB-BASE-ASSISTANT-HIGH-RISK-CARD-NO-OPERATION-PREVIEW';
  // The employee enters once, as on their first day: a fresh database knows only who has entered.
  await (await freshPage(browser, EMPLOYEE)).context().close();
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  const people = await api<{ people: { id: string; name: string; email: string }[] }>(context, A, 'GET', '/people');
  expect(people.status, JSON.stringify(people.data)).toBe(200);
  const employee = people.data.people.find((person) => person.email === EMPLOYEE.email);
  expect(employee, JSON.stringify(people.data.people)).toBeDefined();
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-ASK base__person__pin_remove {"person":"${employee!.id}"}`);
  const preview = card(page).locator('[data-testid="assistant-confirm-preview"]');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText('Quitar en Empleados. Revisa cada dato antes de seguir.');
    await expect(preview).toContainText('Lo que va a pasar');
    await expect(preview.locator('li')).toHaveText([`Nombre: ${employee!.name}`, `Correo: ${EMPLOYEE.email}`]);
    // The person by their name, as Employees reads it, never by the id sent.
    await expect(card(page)).toContainText(`Persona: ${employee!.name}`);
    await expect(card(page)).not.toContainText(employee!.id);
    await captureConfirmation(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toHaveText('No se hizo, cancelado: Quitar en Empleados');
  // A person this business does not have: the preview cannot be read, so no card; the receipt says it failed and why.
  await ask(page, 'E2E-ASK base__person__pin_remove {"person":"saas:0"}');
  await expect(card(page)).toBeHidden();
  await expect(lastAnswer(page)).toContainText('No lo he hecho.');
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toHaveText(
    'No se hizo, falló: Quitar en Empleados. Esa persona no está en este negocio.',
  );
  await lastAnswerAtEachSize(page, 'FIX-HUB-BASE-ASSISTANT-FAILED-RECEIPT-REASON');
  await context.close();
});

test('what the assistant can do is what the person can: a write the employee may not make is refused', async ({ browser, context }) => {
  const page = await freshPage(browser);
  await openPanelAtTheDesk(page);
  const name = `Mesa empleado ${Date.now().toString(36)}`;
  await ask(page, `E2E-CREATE ${name}`);
  await expect(card(page)).toBeHidden();
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Not done, not allowed: Create in Demo');
  await expect(lastAnswer(page)).toContainText(NOT_DONE.en);
  // The tools offered to the model were only what this person may use.
  const tools = JSON.stringify((provider().seen.filter((s) => s.path === '/v1/chat/completions').at(-2)?.body as { tools?: unknown })?.tools);
  expect(tools).not.toContain('demo__item__create');
  await shots(page, 'BASE-G118');
  await page.context().close();
  const none = await api<{ rows: unknown[] }>(context, A, 'GET', `/demo/items?search=${encodeURIComponent(name)}`).catch(() => null);
  expect(none?.data.rows ?? []).toEqual([]);
});
