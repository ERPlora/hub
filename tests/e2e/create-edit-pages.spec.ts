// DEMO-F01 and DEMO-F02 as pages (second pass): «New item» is `/demo/items/new` and «Edit» is
// `/demo/items/:id/edit`. Saving goes back where the person came from and the live list/detail
// paint the result by themselves (no reload, no refetch); a 422 leaves the page open with the
// message under its field; an edit sends only what changed.
import { type Page, expect, test } from '@playwright/test';

import {
  A,
  api,
  createItem,
  createViaPage,
  itemDetail,
  listReady,
  login,
  record,
  row,
  rowNames,
  rowOf,
  shot,
  shown,
  uniqueName,
} from './helpers';

const sameDocument = async (page: Page) =>
  (await page.evaluate(() => (window as unknown as { __doc?: string }).__doc)) === 'original';
const markDocument = (page: Page) => page.evaluate(() => ((window as unknown as { __doc: string }).__doc = 'original'));

/** The message Ionic paints under an `ion-input`/`ion-textarea` marked invalid ('' if none). */
async function fieldError(page: Page, testid: string): Promise<{ invalid: boolean; text: string }> {
  const field = shown(page).locator(`[data-testid=${testid}]`);
  const invalid = await field.evaluate((el) => el.classList.contains('ion-invalid') && el.classList.contains('ion-touched'));
  const error = field.locator('.error-text');
  const text = (await error.count()) && (await error.isVisible()) ? (await error.innerText()).trim() : '';
  return { invalid, text };
}

test('create on /demo/items/new → back to the list, which shows it live and first, with 0 lines', async ({ page, context }) => {
  await login(page, A);
  await listReady(page);
  await markDocument(page);
  const name = uniqueName('Created on its page');

  await shown(page).locator('[data-testid=demo-items-add]').click();
  await expect(page).toHaveURL(/\/demo\/items\/new$/);
  const form = shown(page).locator('[data-testid=demo-form]');
  await form.locator('[data-testid=demo-form-name] input').fill(name);
  await form.locator('[data-testid=demo-form-note] textarea').fill('Written on the create page');
  await page.screenshot({ path: shot('create-edit-pages--create-filled') });
  const created = page.waitForResponse((r) => r.url().endsWith('/api/demo/items') && r.request().method() === 'POST');
  const t0 = Date.now();
  await form.locator('[data-testid=demo-form-save]').click();
  const status = (await created).status();
  await expect(page).toHaveURL(/\/demo\/items$/);
  await expect(row(page, name)).toBeVisible({ timeout: 5000 });
  const backWithRowMs = Date.now() - t0;
  await page.screenshot({ path: shot('create-edit-pages--create-back-on-list') });

  const names = await rowNames(page);
  const newRow = row(page, name);
  const lines = (await newRow.locator('[data-testid=demo-item-lines]').innerText()).trim();
  const listed = await api<{ rows: { id: string; name: string; note: string; status: string; line_count: number }[] }>(
    context,
    A,
    'GET',
    `/demo/items?search=${encodeURIComponent(name)}`,
  );
  record('create-edit-pages--create', { status, backWithRowMs, firstRow: names[0], lines, server: listed.data.rows });

  expect(status).toBe(201);
  expect(await sameDocument(page)).toBe(true);
  expect(names[0]).toBe(name);
  expect(lines).toBe('no lines'); // `demo.items.lineCount`, zero form of the en catalogue
  expect(listed.data.rows).toHaveLength(1);
  expect(listed.data.rows[0]).toMatchObject({ name, status: 'open', note: 'Written on the create page', line_count: 0 });
});

test('edit from the detail on /demo/items/:id/edit → back to the detail with the new values; only changes are sent', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('To edit'));
  await api(context, A, 'POST', '/demo/items/update', { id: item.id, note: 'Note before the edit' });
  await page.goto('/demo/items');
  await listReady(page);
  await markDocument(page);

  await rowOf(page, item.id).click();
  await expect(page).toHaveURL(new RegExp(`/demo/items/${item.id}$`));
  await shown(page).locator('[data-testid=demo-detail-edit]').click();
  await expect(page).toHaveURL(new RegExp(`/demo/items/${item.id}/edit$`));
  const form = shown(page).locator('[data-testid=demo-form]');
  const nameInput = form.locator('[data-testid=demo-form-name] input');
  // The form starts from the item as saved.
  await expect(nameInput).toHaveValue(item.name);
  await expect(form.locator('[data-testid=demo-form-note] textarea')).toHaveValue('Note before the edit');

  const newName = uniqueName('Edited');
  await nameInput.fill(newName);
  await form.locator('[data-testid=demo-form-status]').click();
  await page.locator('ion-popover ion-radio, ion-alert button.alert-radio-button, ion-action-sheet button').filter({ hasText: /^\s*Done\s*$/ }).first().click();
  await expect(form.locator('[data-testid=demo-form-status]')).toHaveJSProperty('value', 'done');
  await page.screenshot({ path: shot('create-edit-pages--edit-filled') });
  const sent = page.waitForRequest((r) => r.url().endsWith('/api/demo/items/update') && r.method() === 'POST');
  await form.locator('[data-testid=demo-form-save]').click();
  const body = (await sent).postDataJSON() as Record<string, unknown>;

  await expect(page).toHaveURL(new RegExp(`/demo/items/${item.id}$`));
  await expect(shown(page).locator('[data-testid=demo-detail-status]')).toHaveText(/Done/);
  await expect(shown(page).locator('ion-title')).toContainText(newName);
  await expect(shown(page).locator('[data-testid=demo-note] textarea')).toHaveValue('Note before the edit');
  await page.screenshot({ path: shot('create-edit-pages--edit-back-on-detail') });
  const server = await itemDetail(context, A, item.id);

  // The list shows the new values and the edited item goes first.
  await shown(page).locator('[data-testid=topbar-back]').click();
  await expect(page).toHaveURL(/\/demo\/items$/);
  await expect(rowOf(page, item.id).locator('[data-testid=demo-item-name]')).toHaveText(newName);
  const firstOnList = (await rowNames(page))[0];

  record('create-edit-pages--edit', { sentBody: body, server: { name: server.name, status: server.status, note: server.note }, firstOnList });
  expect(body).toEqual({ id: item.id, name: newName, status: 'done' });
  expect(server).toMatchObject({ name: newName, status: 'done', note: 'Note before the edit' });
  expect(firstOnList).toBe(newName);
  expect(await sameDocument(page)).toBe(true);
});

test('422: a blank name stays on the page with the message under the field; nothing is saved', async ({ page, context }) => {
  await login(page, A);
  const before = await api<{ total: number }>(context, A, 'GET', '/demo/items?limit=1');

  // Create: only spaces.
  await page.goto('/demo/items/new');
  const form = shown(page).locator('[data-testid=demo-form]');
  await form.locator('[data-testid=demo-form-name] input').fill('   ');
  const refused = page.waitForResponse((r) => r.url().endsWith('/api/demo/items') && r.request().method() === 'POST');
  await form.locator('[data-testid=demo-form-save]').click();
  const createStatus = (await refused).status();
  await expect.poll(async () => (await fieldError(page, 'demo-form-name')).text).not.toBe('');
  const onCreate = await fieldError(page, 'demo-form-name');
  await page.screenshot({ path: shot('create-edit-pages--create-422') });
  const failureBanner = await shown(page).locator('[data-testid=demo-form-failure]').count();
  await expect(page).toHaveURL(/\/demo\/items\/new$/);
  const after = await api<{ total: number }>(context, A, 'GET', '/demo/items?limit=1');

  // Edit: the name emptied.
  const item = await createItem(context, A, uniqueName('Edit 422'));
  await page.goto(`/demo/items/${item.id}/edit`);
  const editForm = shown(page).locator('[data-testid=demo-form]');
  await expect(editForm.locator('[data-testid=demo-form-name] input')).toHaveValue(item.name);
  await editForm.locator('[data-testid=demo-form-name] input').fill('');
  const editRefused = page.waitForResponse((r) => r.url().endsWith('/api/demo/items/update'));
  await editForm.locator('[data-testid=demo-form-save]').click();
  const editStatus = (await editRefused).status();
  await expect.poll(async () => (await fieldError(page, 'demo-form-name')).text).not.toBe('');
  const onEdit = await fieldError(page, 'demo-form-name');
  await page.screenshot({ path: shot('create-edit-pages--edit-422') });
  await expect(page).toHaveURL(new RegExp(`/demo/items/${item.id}/edit$`));
  const server = await itemDetail(context, A, item.id);

  record('create-edit-pages--422', { createStatus, onCreate, failureBanner, totalBefore: before.data.total, totalAfter: after.data.total, editStatus, onEdit, serverName: server.name });
  expect(createStatus).toBe(422);
  expect(onCreate.invalid).toBe(true);
  expect(failureBanner).toBe(0);
  expect(after.data.total).toBe(before.data.total);
  expect(editStatus).toBe(422);
  expect(onEdit.invalid).toBe(true);
  expect(server.name).toBe(item.name);
});

test('edit page of an item deleted elsewhere says «This item no longer exists»', async ({ page, context }) => {
  await login(page, A);
  const item = await createItem(context, A, uniqueName('Deleted while editing'));
  await page.goto(`/demo/items/${item.id}/edit`);
  await expect(shown(page).locator('[data-testid=demo-form-name] input')).toHaveValue(item.name);
  await api(context, A, 'POST', '/demo/items/delete', { id: item.id });
  const message = shown(page).locator('[data-testid=demo-edit-error], [data-testid=demo-form-failure]');
  await expect(message).toContainText('This item no longer exists', { timeout: 5000 });
  await page.screenshot({ path: shot('create-edit-pages--edit-deleted-elsewhere') });
  record('create-edit-pages--deleted', { shown: await message.getAttribute('data-testid'), text: (await message.innerText()).trim() });
});

test('createViaPage helper lands back on the list (used by the other specs)', async ({ page }) => {
  await login(page, A);
  await listReady(page);
  const name = uniqueName('Via helper');
  await createViaPage(page, name);
  await expect(row(page, name)).toBeVisible();
});
