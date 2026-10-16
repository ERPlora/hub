// Every flow of Customers with a screen, one test each (its key in the title and in `// flow:`), done
// end to end on the real stack and seen at 390×844, 834×1112 and 1440×900: `threeShots` resizes, brings
// what the flow shows into sight, checks nothing scrolls sideways and saves
// `.artifacts/APP-CUSTOMER-<key>-<width>.png`. The deeper cases of each flow live in the other
// customer-*.spec.ts and in the app's pytest and Vitest suites; CUSTOMER-F25 is seen in
// appointment-agenda.spec.ts (the agenda is the appointment app's screen).
import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import {
  cardOf,
  cleanUp,
  createCard,
  createdIds,
  customersReady,
  e2eName,
  FLOW_VIEWPORTS,
  horizontalOverflow,
  inputOf,
  rowNamed,
  searchList,
  spanishMobile,
} from './customer-helpers';
import { A, api, login, psql, shot, shown } from './helpers';

test.afterAll(() => cleanUp());

/** At each of the three sizes: `target` in sight, no sideways scroll, and the screenshot. */
async function threeShots(page: Page, key: string, target: () => Locator): Promise<void> {
  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    const seen = target();
    // A list turns its rows into cards on a phone: what was there is painted again, so it retries.
    await expect(async () => {
      await seen.scrollIntoViewIfNeeded({ timeout: 2000 });
      await expect(seen).toBeInViewport({ timeout: 1000 });
    }, `${key} at ${vp.label}`).toPass();
    await expect.poll(() => horizontalOverflow(page), `${key} at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`APP-CUSTOMER-${key}-${vp.label}`) });
  }
}

const toast = (page: Page): Locator => page.locator('ion-toast').last();

async function openCard(page: Page, id: string): Promise<Locator> {
  await page.goto(`/customer/customers/${id}`);
  const facts = shown(page).locator('[data-testid=customer-facts]');
  await expect(facts).toBeVisible();
  return facts;
}

async function createNamed(context: BrowserContext, kind: 'groups' | 'tags', name: string): Promise<string> {
  const res = await api<{ id: string }>(context, A, 'POST', `/customer/${kind}`, { name });
  expect(res.status, `create ${kind} ${name}`).toBe(201);
  return res.data.id;
}

// flow: CUSTOMER-F01 · gh:pm#478, gh:pm#513 — a refused save is told under its field and in sight, also on a phone
test('CUSTOMER-F01: «Add» creates a card from its name; a refused phone is told under its field at every width', async ({ page }) => {
  await login(page, A, '/customer/customers');
  await customersReady(page);
  await shown(page).locator('[data-testid=customer-list-add]').click();
  const dialog = page.locator('ion-modal[data-testid=customer-create]');
  await expect(dialog.locator('[data-testid=customer-create-submit]')).toHaveJSProperty('disabled', true);
  const name = e2eName('F01 Ana');
  await inputOf(dialog, 'customer-form-name').fill(name);
  await inputOf(dialog, 'customer-form-phone').fill('600111');
  await dialog.locator('[data-testid=customer-create-submit]').click();
  const phone = dialog.locator('[data-testid=customer-form-phone]');
  await expect(phone).toHaveClass(/ion-invalid/);
  await threeShots(page, 'CUSTOMER-F01', () => phone);
  await inputOf(dialog, 'customer-form-phone').fill('');
  await dialog.locator('[data-testid=customer-create-submit]').click();
  await expect(dialog).toBeHidden();
  await searchList(page, 'customer-list', name);
  await expect(rowNamed(page, 'customer-list', name)).toBeVisible();
});

// flow: CUSTOMER-F02 · gh:customers#95 — on a phone the card names the row once
test('CUSTOMER-F02: the search finds a card by its phone however it is typed; the phone card names it once', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const phone = spanishMobile();
  const card = await createCard(context, { name: e2eName('F02 Search'), phone, email: 'f02.e2e@example.com' });
  await customersReady(page);
  await searchList(page, 'customer-list', `0034 ${phone.slice(0, 3)}-${phone.slice(3)}`);
  const row = rowNamed(page, 'customer-list', card.name);
  await expect(row).toHaveCount(1);
  await threeShots(page, 'CUSTOMER-F02', () => rowNamed(page, 'customer-list', card.name));
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(rowNamed(page, 'customer-list', card.name).getByText(card.name, { exact: true })).toHaveCount(1);
});

// flow: CUSTOMER-F03
test('CUSTOMER-F03: a row opens the whole card and Back returns', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F03 Card'), phone: spanishMobile(), notes: 'Prefers mornings', birthday: '1990-05-04' });
  await customersReady(page);
  await searchList(page, 'customer-list', card.name);
  await rowNamed(page, 'customer-list', card.name).click();
  await page.waitForURL(new RegExp(`/customer/customers/${card.id}$`));
  const facts = shown(page).locator('[data-testid=customer-facts]');
  await expect(facts).toContainText('Prefers mornings');
  await threeShots(page, 'CUSTOMER-F03', () => shown(page).locator('[data-testid=customer-facts]'));
  await shown(page).locator('[data-testid=topbar-back]').click();
  await page.waitForURL(/\/customer\/customers$/);
});

// flow: CUSTOMER-F04
test('CUSTOMER-F04: «Edit» turns the data into the form; «Save» says «Customer updated»', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F04 Edit') });
  await openCard(page, card.id);
  await shown(page).locator('[data-testid=customer-detail-edit]').click();
  const form = shown(page).locator('[data-testid=customer-edit-form]');
  await inputOf(form, 'customer-form-city').fill('Sevilla');
  await threeShots(page, 'CUSTOMER-F04', () => shown(page).locator('[data-testid=customer-edit-save]'));
  await shown(page).locator('[data-testid=customer-edit-save]').click();
  await expect(toast(page)).toContainText(/Customer updated|Cliente actualizado/);
  await expect.poll(async () => (await cardOf(context, card.id)).data).toMatchObject({ id: card.id });
  expect(((await cardOf(context, card.id)).data as unknown as { city: string }).city).toBe('Sevilla');
});

// flow: CUSTOMER-F05
test('CUSTOMER-F05: a note goes on top of the activity, with who and when', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F05 Note') });
  await openCard(page, card.id);
  const form = shown(page).locator('[data-testid=customer-note-form]');
  await form.locator('[data-testid=customer-note-text] textarea').fill('Allergic to latex gloves');
  await form.locator('[data-testid=customer-note-add]').click();
  await expect(toast(page)).toContainText(/Note added|Nota añadida/);
  const item = shown(page).locator('[data-testid=customer-activity-item]').first();
  await expect(item).toContainText('Allergic to latex gloves');
  await threeShots(page, 'CUSTOMER-F05', () => shown(page).locator('[data-testid=customer-activity-item]').first());
});

// flow: CUSTOMER-F06
test('CUSTOMER-F06: groups and tags are ticked on the card and saved', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F06 Member') });
  const group = await createNamed(context, 'groups', e2eName('F06 VIP'));
  const tag = await createNamed(context, 'tags', e2eName('F06 Loyal'));
  await openCard(page, card.id);
  const groups = shown(page).locator('[data-testid=customer-groups]');
  await groups.locator(`[data-testid=customer-groups-item-${group}]`).click();
  await groups.locator('[data-testid=customer-groups-save]').click();
  await expect(toast(page)).toContainText(/Groups assigned|Grupos asignados/);
  const tags = shown(page).locator('[data-testid=customer-tags]');
  await tags.locator(`[data-testid=customer-tags-item-${tag}]`).click();
  await tags.locator('[data-testid=customer-tags-save]').click();
  await expect(toast(page)).toContainText(/Tags assigned|Etiquetas asignadas/);
  await expect.poll(async () => (await cardOf(context, card.id)).data.group_ids).toEqual([group]);
  await threeShots(page, 'CUSTOMER-F06', () => shown(page).locator('[data-testid=customer-groups]'));
});

// flow: CUSTOMER-F07
test('CUSTOMER-F07: «Delete» asks in a dialog what it means; confirmed, the card is gone', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F07 Delete') });
  await openCard(page, card.id);
  await shown(page).locator('[data-testid=customer-detail-delete]').click();
  const dialog = page.locator('ion-modal[data-testid=customer-delete-confirm]');
  await expect(dialog).toContainText(card.name);
  await threeShots(page, 'CUSTOMER-F07', () => page.locator('[data-testid=customer-delete-confirm-submit]'));
  await dialog.locator('[data-testid=customer-delete-confirm-submit]').click();
  await page.waitForURL(/\/customer\/customers$/);
  expect((await cardOf(context, card.id)).status).toBe(404);
});

// flow: CUSTOMER-F08 · gh:services#152, gh:customers#15 — importing the same file again does not duplicate
test('CUSTOMER-F08: «Import CSV» reports what it created and skipped; the same file again creates nothing', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  await customersReady(page);
  const marker = e2eName('F08 Import');
  const csv = join(tmpdir(), `customers-f08-${Date.now()}.csv`);
  writeFileSync(csv, ['Nombre;Teléfono;Email', `${marker} Ana;${spanishMobile()};ana.f08@example.com`, `;${spanishMobile()};`].join('\n'));
  const file = shown(page).locator('[data-testid=customer-import] ~ input[type=file]');
  const report = shown(page).locator('[data-testid=customer-import-report]');
  await file.setInputFiles(csv);
  await expect(report.locator('[data-testid=customer-import-summary]')).toHaveText(/2 rows — 1 created, 1 skipped|2 filas — 1 creadas, 1 omitidas/);
  await report.locator('[data-testid=customer-import-close]').click();
  await file.setInputFiles(csv);
  await expect(report.locator('[data-testid=customer-import-summary]')).toHaveText(/2 rows — 0 created, 2 skipped|2 filas — 0 creadas, 2 omitidas/);
  await expect(report.locator('[data-testid=customer-import-skipped] li').first()).toContainText(/already a card|Ya hay una ficha/);
  await threeShots(page, 'CUSTOMER-F08', () => shown(page).locator('[data-testid=customer-import-summary]'));
  const found = await api<{ total: number; rows: { id: string }[] }>(context, A, 'GET', `/customer/customers?search=${encodeURIComponent(marker)}`);
  expect(found.data.total).toBe(1);
  found.data.rows.forEach((row) => createdIds.add(row.id));
});

// flow: CUSTOMER-F09
test('CUSTOMER-F09: «Export CSV» downloads every card of the search', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const marker = e2eName('F09 Export');
  await createCard(context, { name: `${marker} one` });
  await createCard(context, { name: `${marker} two` });
  await customersReady(page);
  await searchList(page, 'customer-list', marker);
  await expect(shown(page).locator('[data-testid=customer-list-row]')).toHaveCount(2);
  await threeShots(page, 'CUSTOMER-F09', () => shown(page).locator('[data-testid=customer-export]'));
  const download = page.waitForEvent('download');
  await shown(page).locator('[data-testid=customer-export]').click();
  const text = readFileSync((await (await download).path()) as string, 'utf8');
  expect(text.trim().split('\n')).toHaveLength(3);
});

// flow: CUSTOMER-F11
test('CUSTOMER-F11: a phone typed with 0034 and spaces is kept in E.164 and shown grouped', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F11 Phone') });
  const phone = spanishMobile();
  await openCard(page, card.id);
  await shown(page).locator('[data-testid=customer-detail-edit]').click();
  await inputOf(shown(page), 'customer-form-phone').fill(`0034 ${phone.slice(0, 3)} ${phone.slice(3, 6)} ${phone.slice(6)}`);
  await shown(page).locator('[data-testid=customer-edit-save]').click();
  await expect(toast(page)).toContainText(/Customer updated|Cliente actualizado/);
  expect((await cardOf(context, card.id)).data.phone).toBe(`+34${phone}`);
  const shownPhone = shown(page).locator('[data-fact=phone] dd');
  await expect(shownPhone).toHaveText(`+34 ${phone.slice(0, 3)} ${phone.slice(3, 6)} ${phone.slice(6)}`);
  await threeShots(page, 'CUSTOMER-F11', () => shown(page).locator('[data-fact=phone]'));
});

// flow: CUSTOMER-F12, CUSTOMER-F18
test('CUSTOMER-F12 and F18: the till\'s quick add shows the card that has the phone and asks before assigning', async ({ page, context }) => {
  await login(page, A, '/customer/preview/customer-search');
  const phone = spanishMobile();
  const card = await createCard(context, { name: e2eName('F12 Mother'), phone });
  const preview = shown(page);
  await preview.locator('[data-testid=customer-search-trigger]').click();
  const modal = page.locator('ion-modal[data-testid=customer-search-modal]');
  await modal.locator('[data-testid=customer-picker-search] input').fill(e2eName('F18 New'));
  await expect(modal.locator('[data-testid=customer-picker-empty]')).toBeVisible();
  await modal.locator('[data-testid=customer-search-quick-add]').click();
  await inputOf(modal, 'customer-search-quick-phone').fill(phone);
  await threeShots(page, 'CUSTOMER-F18', () => modal.locator('[data-testid=customer-search-quick-submit]'));
  await modal.locator('[data-testid=customer-search-quick-submit]').click();
  const taken = modal.locator('[data-testid=customer-search-phone-taken]');
  await expect(taken).toContainText(card.name);
  await threeShots(page, 'CUSTOMER-F12', () => modal.locator('[data-testid=customer-search-phone-taken]'));
  await taken.locator(`[data-testid=customer-search-use-${card.id}]`).click();
  await expect(modal).toBeHidden();
  await expect(preview.locator('[data-testid=customer-preview-snapshot]')).toContainText(card.name);
});

// flow: CUSTOMER-F13
test('CUSTOMER-F13: «Merge with…» says what will happen; merged, the duplicate is gone', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const stays = await createCard(context, { name: e2eName('F13 Laura'), email: 'f13.e2e@example.com' });
  const duplicate = await createCard(context, { name: e2eName('F13 Laura P.'), phone: spanishMobile() });
  await openCard(page, stays.id);
  await shown(page).locator('[data-testid=customer-detail-merge]').click();
  const panel = shown(page).locator('[data-testid=customer-merge]');
  await panel.locator('[data-testid=customer-picker-search] input').fill(duplicate.name);
  await panel.locator(`[data-testid=customer-picker-result-${duplicate.id}]`).click();
  await expect(panel.locator('[data-testid=customer-merge-confirm]')).toContainText(duplicate.name);
  await threeShots(page, 'CUSTOMER-F13', () => shown(page).locator('[data-testid=customer-merge-submit]'));
  await panel.locator('[data-testid=customer-merge-submit]').click();
  await expect(toast(page)).toContainText(duplicate.name);
  expect((await cardOf(context, duplicate.id)).status).toBe(404);
});

// flow: CUSTOMER-F14, CUSTOMER-F15
test('CUSTOMER-F14 and F15: consent is recorded with the words read out, and withdrawn in one tap', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F14 Consent'), phone: spanishMobile() });
  await openCard(page, card.id);
  await shown(page).locator('[data-testid=customer-consent-whatsapp-grant]').click();
  const ask = shown(page).locator('[data-testid=customer-consent-whatsapp-ask]');
  await expect(ask).toContainText(/I want to receive offers|Quiero recibir ofertas/);
  await threeShots(page, 'CUSTOMER-F14', () => shown(page).locator('[data-testid=customer-consent-whatsapp-confirm]'));
  await shown(page).locator('[data-testid=customer-consent-whatsapp-confirm]').click();
  await expect(toast(page)).toContainText(/Consent recorded|Consentimiento registrado/);
  await shown(page).locator('[data-testid=customer-consent-whatsapp-withdraw]').click();
  await expect(toast(page)).toContainText(/Consent withdrawn|Consentimiento retirado/);
  await expect(shown(page).locator('[data-testid=customer-consent-whatsapp] .customer-consent__state')).toHaveText(/Withdrawn|Retirado/);
  await threeShots(page, 'CUSTOMER-F15', () => shown(page).locator('[data-testid=customer-consent-whatsapp]'));
});

// flow: CUSTOMER-F16
test('CUSTOMER-F16: «Erase personal data» asks with the reason; erased, back to the list', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F16 Erase'), phone: spanishMobile() });
  await openCard(page, card.id);
  await shown(page).locator('[data-testid=customer-detail-erase]').click();
  const panel = shown(page).locator('[data-testid=customer-erase]');
  await inputOf(panel, 'customer-erase-reason').fill('Asked at the counter (e2e)');
  await threeShots(page, 'CUSTOMER-F16', () => shown(page).locator('[data-testid=customer-erase-submit]'));
  await panel.locator('[data-testid=customer-erase-submit]').click();
  await page.waitForURL(/\/customer\/customers$/);
  expect((await cardOf(context, card.id)).status).toBe(404);
});

// flow: CUSTOMER-F17
test('CUSTOMER-F17: the till\'s search assigns a card with its tax copy', async ({ page, context }) => {
  await login(page, A, '/customer/preview/customer-search');
  const card = await createCard(context, { name: e2eName('F17 Till'), tax_id: '12345678Z', address: 'Calle Mayor 1', city: 'Madrid', postal_code: '28001', country: 'ES' });
  const preview = shown(page);
  await preview.locator('[data-testid=customer-search-trigger]').click();
  const modal = page.locator('ion-modal[data-testid=customer-search-modal]');
  await modal.locator('[data-testid=customer-picker-search] input').fill(card.name);
  await modal.locator(`[data-testid=customer-picker-result-${card.id}]`).click();
  await expect(modal).toBeHidden();
  await expect(preview.locator('[data-testid=customer-preview-snapshot]')).toContainText('12345678Z');
  await threeShots(page, 'CUSTOMER-F17', () => shown(page).locator('[data-testid=customer-preview-snapshot]'));
});

// flow: CUSTOMER-F23
test('CUSTOMER-F23: «Purchases» lists each sale, void and refund of the card', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F23 Buyer') });
  // Sales reach a card through the sale app's notices (the relay, phase 2): the rows are set up here.
  const sale = crypto.randomUUID();
  psql(
    `insert into customer_purchase (id, customer_id, sale_id, refund_id, amount, currency, status, recorded_at, void_reason) values ` +
      `(gen_random_uuid(), '${card.id}', '${sale}', null, 2500, 'EUR', 'confirmed', now() - interval '2 days', ''), ` +
      `(gen_random_uuid(), '${card.id}', '${sale}', '${crypto.randomUUID()}', -500, 'EUR', 'refunded', now() - interval '1 day', ''), ` +
      `(gen_random_uuid(), '${card.id}', '${crypto.randomUUID()}', null, 1200, 'EUR', 'voided', now(), 'Wrong item')`,
  );
  await openCard(page, card.id);
  const purchases = shown(page).locator('[data-testid=customer-purchases]');
  await expect(purchases.locator('[data-testid=customer-purchase]')).toHaveCount(3);
  await threeShots(page, 'CUSTOMER-F23', () => shown(page).locator('[data-testid=customer-purchases]'));
});

// flow: CUSTOMER-F24
test('CUSTOMER-F24: the card ends with the blocks of the other apps (the appointments\' visit history)', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F24 Blocks') });
  await openCard(page, card.id);
  const blocks = shown(page).locator('[data-testid=customer-card-blocks] [data-testid=customer-card-block]');
  await expect(blocks.first()).toBeVisible();
  await threeShots(page, 'CUSTOMER-F24', () => shown(page).locator('[data-testid=customer-card-blocks] [data-testid=customer-card-block]').first());
});

// flow: CUSTOMER-F27
test('CUSTOMER-F27: a group is created in «New group» and listed', async ({ page }) => {
  await login(page, A, '/customer/groups');
  const name = e2eName('F27 Group');
  await shown(page).locator('[data-testid=customer-groups-add]').click();
  const form = page.locator('ion-modal[data-testid=customer-group-form]');
  await inputOf(form, 'customer-group-form-name').fill(name);
  await threeShots(page, 'CUSTOMER-F27', () => page.locator('[data-testid=customer-group-form-submit]'));
  await form.locator('[data-testid=customer-group-form-submit]').click();
  await expect(form).toBeHidden();
  await searchList(page, 'customer-groups', name);
  await expect(rowNamed(page, 'customer-groups', name)).toBeVisible();
});

// flow: CUSTOMER-F28
test('CUSTOMER-F28: a tag is created in «New tag» and listed', async ({ page }) => {
  await login(page, A, '/customer/tags');
  const name = e2eName('F28 Tag');
  await shown(page).locator('[data-testid=customer-tags-add]').click();
  const form = page.locator('ion-modal[data-testid=customer-tag-form]');
  await inputOf(form, 'customer-tag-form-name').fill(name);
  await threeShots(page, 'CUSTOMER-F28', () => page.locator('[data-testid=customer-tag-form-submit]'));
  await form.locator('[data-testid=customer-tag-form-submit]').click();
  await expect(form).toBeHidden();
  await searchList(page, 'customer-tags', name);
  await expect(rowNamed(page, 'customer-tags', name)).toBeVisible();
});

// flow: CUSTOMER-F29
test('CUSTOMER-F29: a custom field is created and shows on every card', async ({ page, context }) => {
  await login(page, A, '/customer/fields');
  const name = e2eName('F29 Field');
  await shown(page).locator('[data-testid=customer-fields-add]').click();
  const form = page.locator('ion-modal[data-testid=customer-field-form]');
  await inputOf(form, 'customer-field-form-name').fill(name);
  await threeShots(page, 'CUSTOMER-F29', () => page.locator('[data-testid=customer-field-form-submit]'));
  await form.locator('[data-testid=customer-field-form-submit]').click();
  await expect(form).toBeHidden();
  const card = await createCard(context, { name: e2eName('F29 Card') });
  await openCard(page, card.id);
  await expect(shown(page).locator('[data-testid=customer-facts-custom]')).toContainText(name);
});

// flow: CUSTOMER-F31
test('CUSTOMER-F31: the four figures above the list follow a new card without reloading', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  await customersReady(page);
  const total = shown(page).locator('[data-testid=customer-stats-total]');
  const before = Number(await total.getAttribute('data-value'));
  await createCard(context, { name: e2eName('F31 Counted') });
  await expect.poll(async () => Number(await total.getAttribute('data-value'))).toBe(before + 1);
  await threeShots(page, 'CUSTOMER-F31', () => shown(page).locator('[data-testid=customer-stats]'));
});

// flow: CUSTOMER-F32
test('CUSTOMER-F32: allergies are kept only after the permission; withdrawing it erases them', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('F32 Health') });
  await openCard(page, card.id);
  const health = shown(page).locator('[data-testid=customer-health]');
  await expect(health.locator('[data-testid=customer-health-intro]')).toBeVisible();
  await health.locator('[data-testid=customer-health-ask]').click();
  await expect(health.locator('[data-testid=customer-health-asking]')).toContainText(/I give my permission|Doy mi permiso/);
  await health.locator('[data-testid=customer-health-confirm]').click();
  await expect(toast(page)).toContainText(/Permission recorded|Permiso registrado/);
  await health.locator('[data-testid=customer-health-edit]').click();
  await health.locator('[data-testid=customer-health-allergies-input] textarea').fill('PPD (hair dye)');
  await health.locator('[data-testid=customer-health-save]').click();
  await expect(toast(page)).toContainText(/Health data saved|Datos de salud guardados/);
  const allergies = health.locator('[data-testid=customer-health-allergies]');
  await expect(allergies).toHaveClass(/customer-health__alert/);
  await expect(allergies).toContainText('PPD (hair dye)');
  const block = await api<{ consent: string; allergies: string }>(context, A, 'GET', `/customer/health?customer_id=${card.id}`);
  expect(block.data).toMatchObject({ consent: 'granted', allergies: 'PPD (hair dye)' });
  // The card other apps read does not carry it.
  expect(JSON.stringify((await cardOf(context, card.id)).data)).not.toContain('PPD');
  await threeShots(page, 'CUSTOMER-F32', () => shown(page).locator('[data-testid=customer-health]'));

  await health.locator('[data-testid=customer-health-withdraw]').click();
  const dialog = page.locator('ion-modal[data-testid=customer-health-withdraw-dialog]');
  await expect(dialog).toContainText(/erased|se borran/);
  await page.screenshot({ path: shot('APP-CUSTOMER-CUSTOMER-F32-withdraw-1440') });
  await dialog.locator('[data-testid=customer-health-withdraw-dialog-submit]').click();
  await expect(toast(page)).toContainText(/Permission withdrawn|Permiso retirado/);
  await expect(health.locator('[data-testid=customer-health-intro]')).toBeVisible();
  const after = await api<{ consent: string; allergies: string }>(context, A, 'GET', `/customer/health?customer_id=${card.id}`);
  expect(after.data).toMatchObject({ consent: 'withdrawn', allergies: '' });
});
