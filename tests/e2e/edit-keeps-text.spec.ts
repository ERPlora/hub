// PoC §8.3 and DEMO-F02: the note of the detail has local state. While tab 1 writes (unsaved), tab 2
// adds a line (tab 1 shows it and keeps its text and focus) and then saves another note: tab 1 still
// keeps its text and focus and warns «Updated elsewhere».
import { expect, test } from '@playwright/test';

import { A, createItem, itemDetail, login, record, shot, uniqueName } from './helpers';

test('typing in the note survives a line and a note saved elsewhere; «Updated elsewhere» shows', async ({ context }) => {
  const tab1 = await context.newPage();
  await login(tab1, A);
  const item = await createItem(context, A, uniqueName('Note'));
  await tab1.goto(`/demo/items/${item.id}`);
  const tab2 = await context.newPage();
  await tab2.goto(`/demo/items/${item.id}`);
  await expect(tab1.locator('[data-testid=demo-detail-status]')).toBeVisible();
  await expect(tab2.locator('[data-testid=demo-detail-status]')).toBeVisible();

  const draft = 'Draft written in tab 1, not saved';
  const note1 = tab1.locator('[data-testid=demo-note] textarea');
  await note1.click();
  await note1.pressSequentially(draft, { delay: 10 });
  await tab1.evaluate(() => {
    const ta = document.querySelector('[data-testid=demo-note] textarea') as HTMLTextAreaElement;
    ta.setSelectionRange(5, 5); // caret in the middle: it must not jump
  });
  const focused = () =>
    tab1.evaluate(() => {
      const ta = document.activeElement as HTMLTextAreaElement | null;
      return { inNote: !!ta?.closest('[data-testid=demo-note]'), caret: ta?.selectionStart ?? null };
    });

  // Tab 2 adds a line: tab 1 paints it, the draft and the caret stay.
  await tab2.locator('[data-testid=demo-line-input-text] input').fill('Line from tab 2');
  await tab2.locator('[data-testid=demo-line-add]').click();
  await expect(tab1.locator('[data-testid=demo-line-text]')).toHaveText(['Line from tab 2'], { timeout: 5000 });
  const afterLine = { text: await note1.inputValue(), ...(await focused()), banner: await tab1.locator('[data-testid=demo-note-stale]').count() };

  // Tab 2 saves a different note: tab 1 keeps the draft and warns.
  await tab2.locator('[data-testid=demo-note] textarea').fill('Note saved in tab 2');
  await tab2.locator('[data-testid=demo-note-save]').click();
  await expect(tab1.locator('[data-testid=demo-note-stale]')).toBeVisible({ timeout: 5000 });
  const afterNote = { text: await note1.inputValue(), ...(await focused()) };
  await tab1.screenshot({ path: shot('05-tab1-updated-elsewhere') });
  await tab2.screenshot({ path: shot('05-tab2-saved-note') });
  const server = await itemDetail(context, A, item.id);

  record('05-edit-keeps-text', { afterLine, afterNote, serverNote: server.note });
  expect(afterLine.text).toBe(draft);
  expect(afterLine.inNote).toBe(true);
  expect(afterLine.caret).toBe(5);
  expect(afterLine.banner).toBe(0); // a line does not touch the note: nothing to warn about
  expect(afterNote.text).toBe(draft);
  expect(afterNote.inNote).toBe(true);
  expect(afterNote.caret).toBe(5);
  expect(server.note).toBe('Note saved in tab 2');
});
