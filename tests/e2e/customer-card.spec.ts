// The customer card in Ioan's Chrome: a note added in one tab shows in the activity of another tab
// without reloading (CUSTOMER-F05, live); a group and a tag created in their lists are ticked on the
// card and their «Customers» count follows (F06, F27, F28); «Merge with…» folds a duplicate into the
// open card (F13); «Erase personal data» asks first and erases (F16); «Delete» on a row asks first
// and deletes (F07).
import { type BrowserContext, expect, test } from '@playwright/test';

import { cardOf, cleanUp, createCard, customersReady, e2eName, FLOW_VIEWPORTS, inputOf, rowNamed, searchList, spanishMobile } from './customer-helpers';
import { A, api, login, shot, shown } from './helpers';

test.afterAll(() => cleanUp());

test('a note added in one tab shows live in the other tab\'s activity', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('Notes'), phone: spanishMobile() });
  const other = await context.newPage();
  await other.goto(`${A}/customer/customers/${card.id}`);
  await expect(shown(other).locator('[data-testid=customer-activity-empty]')).toBeVisible();

  await page.goto(`/customer/customers/${card.id}`);
  const form = shown(page).locator('[data-testid=customer-note-form]');
  await expect(form.locator('[data-testid=customer-note-add]')).toHaveJSProperty('disabled', true);
  await form.locator('[data-testid=customer-note-text] textarea').fill('Prefers mornings, allergic to latex');
  await form.locator('[data-testid=customer-note-add]').click();
  await expect(page.locator('ion-toast')).toContainText(/Note added|Nota añadida/);
  await expect(form.locator('[data-testid=customer-note-text] textarea')).toHaveValue('');

  // The other tab: same text, no reload.
  const item = shown(other).locator('[data-testid=customer-activity-item]').first();
  await expect(item).toContainText('Prefers mornings, allergic to latex');
  await expect(item).toContainText(/Note added|Nota añadida/);
  await other.screenshot({ path: shot('customer-card-note-live-other-tab') });
  await other.close();
});

// flow: CUSTOMER-F06 — saving the groups refreshes the card live; that refresh must not untick the tag
// ticked right after and not saved yet (hub#114: «Save tags» sent none and the card lost it).
test('a group and a tag made in their lists are assigned on the card; their counts follow', async ({ page, context }) => {
  await login(page, A, '/customer/groups');
  const card = await createCard(context, { name: e2eName('Member') });
  const groupName = e2eName('VIP');
  const tagName = e2eName('Loyal');

  // Groups → «Add» → «New group».
  await shown(page).locator('[data-testid=customer-groups-add]').click();
  const groupForm = page.locator('ion-modal[data-testid=customer-group-form]');
  await inputOf(groupForm, 'customer-group-form-name').fill(groupName);
  await groupForm.locator('[data-testid=customer-group-form-submit]').click();
  await expect(groupForm).toBeHidden();
  await searchList(page, 'customer-groups', groupName);
  await expect(rowNamed(page, 'customer-groups', groupName)).toBeVisible();

  // Tags → «Add» → «New tag» (through the footer tab).
  await shown(page).locator('[data-testid=tab-tags]').click();
  await page.waitForURL(/\/customer\/tags$/);
  await shown(page).locator('[data-testid=customer-tags-add]').click();
  const tagForm = page.locator('ion-modal[data-testid=customer-tag-form]');
  await inputOf(tagForm, 'customer-tag-form-name').fill(tagName);
  await tagForm.locator('[data-testid=customer-tag-form-submit]').click();
  await expect(tagForm).toBeHidden();

  // On the card: tick them and save.
  await page.goto(`/customer/customers/${card.id}`);
  const groups = shown(page).locator('[data-testid=customer-groups]');
  await groups.locator('[data-testid=customer-groups-item-' + (await idOf(context, 'groups', groupName)) + ']').click();
  await groups.locator('[data-testid=customer-groups-save]').click();
  await expect(page.locator('ion-toast').last()).toContainText(/Groups assigned|Grupos asignados/);
  const tags = shown(page).locator('[data-testid=customer-tags]');
  await tags.locator('[data-testid=customer-tags-item-' + (await idOf(context, 'tags', tagName)) + ']').click();
  await tags.locator('[data-testid=customer-tags-save]').click();
  await expect(page.locator('ion-toast').last()).toContainText(/Tags assigned|Etiquetas asignadas/);
  await expect.poll(async () => (await cardOf(context, card.id)).data.group_ids.length).toBe(1);
  await expect.poll(async () => (await cardOf(context, card.id)).data.tag_ids.length).toBe(1);
  await page.screenshot({ path: shot('customer-card-groups-tags') });

  // The lists count the card.
  await page.goto('/customer/groups');
  await searchList(page, 'customer-groups', groupName);
  await expect(rowNamed(page, 'customer-groups', groupName)).toContainText('1');
});

// flow: CUSTOMER-F06 — the other way round: a tag saved first, then a group ticked; the card changes
// meanwhile (someone renames it) and its live result arrives before «Save groups»: the tick stays, the
// card keeps both, and both stay ticked at every size.
test('a tag saved first, a group ticked while the card changes, then saved: the card keeps both', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('Both') });
  const tag = await api<{ id: string }>(context, A, 'POST', '/customer/tags', { name: e2eName('Regular') });
  const group = await api<{ id: string }>(context, A, 'POST', '/customer/groups', { name: e2eName('Gold') });
  expect([tag.status, group.status]).toEqual([201, 201]);

  await page.goto(`/customer/customers/${card.id}`);
  const tags = shown(page).locator('[data-testid=customer-tags]');
  const groups = shown(page).locator('[data-testid=customer-groups]');
  await tags.locator(`[data-testid=customer-tags-item-${tag.data.id}]`).click();
  await tags.locator('[data-testid=customer-tags-save]').click();
  await expect(page.locator('ion-toast').last()).toContainText(/Tags assigned|Etiquetas asignadas/);
  const groupBox = groups.locator(`[data-testid=customer-groups-item-${group.data.id}]`);
  await groupBox.click();
  await expect(groupBox).toHaveJSProperty('checked', true);
  const renamed = e2eName('Both renamed');
  expect((await api(context, A, 'POST', '/customer/customers/update', { id: card.id, name: renamed })).status).toBe(200);
  await expect(shown(page).locator('ion-title')).toContainText(renamed);
  await expect(groupBox).toHaveJSProperty('checked', true);
  await groups.locator('[data-testid=customer-groups-save]').click();
  await expect(page.locator('ion-toast').last()).toContainText(/Groups assigned|Grupos asignados/);
  await expect
    .poll(async () => {
      const { data } = await cardOf(context, card.id);
      return [data.group_ids, data.tag_ids];
    })
    .toEqual([[group.data.id], [tag.data.id]]);

  for (const vp of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`/customer/customers/${card.id}`);
    const box = (kind: 'groups' | 'tags', id: string) => shown(page).locator(`[data-testid=customer-${kind}-item-${id}]`);
    await expect(box('groups', group.data.id)).toHaveJSProperty('checked', true);
    await expect(box('tags', tag.data.id)).toHaveJSProperty('checked', true);
    await box('tags', tag.data.id).scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot(`FIX-CUSTOMER-CARD-GROUP-LOST-AFTER-TAG-${vp.label}`) });
  }
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
});

/** The id of an `e2e.` group or tag by its name (setup evidence, through the API). */
async function idOf(context: BrowserContext, kind: 'groups' | 'tags', name: string): Promise<string> {
  const res = await api<{ rows: { id: string; name: string }[] }>(context, A, 'GET', `/customer/${kind}?search=${encodeURIComponent(name)}`);
  const found = res.data.rows.find((r) => r.name === name);
  if (!found) throw new Error(`no ${kind} ${name}`);
  return found.id;
}

test('«Merge with…» folds a duplicate into the open card', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const stays = await createCard(context, { name: e2eName('Laura Pérez'), email: 'laura.e2e@example.com' });
  const duplicate = await createCard(context, { name: e2eName('Laura P.'), phone: spanishMobile() });

  await page.goto(`/customer/customers/${stays.id}`);
  await shown(page).locator('[data-testid=customer-detail-merge]').click();
  const panel = shown(page).locator('[data-testid=customer-merge]');
  await expect(panel).toContainText(/Merge a duplicate customer|Fusionar una ficha duplicada/);
  await panel.locator('[data-testid=customer-picker-search] input').fill(duplicate.name);
  await panel.locator(`[data-testid=customer-picker-result-${duplicate.id}]`).click();
  await expect(panel.locator('[data-testid=customer-merge-confirm]')).toContainText(duplicate.name);
  await page.screenshot({ path: shot('customer-card-merge-confirm') });
  await panel.locator('[data-testid=customer-merge-submit]').click();
  await expect(page.locator('ion-toast').last()).toContainText(duplicate.name);

  // The survivor gained the phone and the activity says so; the duplicate is gone.
  await expect(shown(page).locator('[data-fact=phone] dd')).not.toHaveText('—');
  await expect(shown(page).locator('[data-testid=customer-activity-item][data-kind=merged]')).toBeVisible();
  expect((await cardOf(context, duplicate.id)).status).toBe(404);
  await page.goto('/customer/customers');
  await customersReady(page);
  await searchList(page, 'customer-list', duplicate.name);
  await expect(shown(page).locator('[data-testid=customer-list-empty]')).toBeVisible();
});

test('«Erase personal data» asks first, then erases and goes back to the list', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('Erase me'), phone: spanishMobile(), email: 'erase.e2e@example.com' });
  await page.goto(`/customer/customers/${card.id}`);
  await shown(page).locator('[data-testid=customer-detail-erase]').click();
  const panel = shown(page).locator('[data-testid=customer-erase]');
  await expect(panel).toContainText(/cannot be undone|no se puede deshacer/);
  await inputOf(panel, 'customer-erase-reason').fill('Asked by email (e2e)');
  await page.screenshot({ path: shot('customer-card-erase-confirm') });
  // Nothing is erased until the danger button.
  expect((await cardOf(context, card.id)).status).toBe(200);
  await panel.locator('[data-testid=customer-erase-submit]').click();
  await page.waitForURL(/\/customer\/customers$/);
  await expect(page.locator('ion-toast').last()).toContainText(/Personal data erased|Datos personales borrados/);
  expect((await cardOf(context, card.id)).status).toBe(404);
});

test('«Delete» on a row asks in a dialog, then deletes', async ({ page, context }) => {
  await login(page, A, '/customer/customers');
  const card = await createCard(context, { name: e2eName('Delete me') });
  await page.goto('/customer/customers');
  await customersReady(page);
  await searchList(page, 'customer-list', card.name);
  await shown(page).locator(`[data-testid=customer-list-row-${card.id}-delete]`).click();
  const dialog = page.locator('ion-modal[data-testid=customer-delete-confirm]');
  await expect(dialog).toContainText(card.name);
  await page.screenshot({ path: shot('customer-list-delete-confirm') });
  await dialog.locator('[data-testid=customer-delete-confirm-submit]').click();
  await expect(dialog).toBeHidden();
  await expect(shown(page).locator('[data-testid=customer-list-empty]')).toBeVisible();
  expect((await cardOf(context, card.id)).status).toBe(404);
});
