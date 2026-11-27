// flow: FLOW-F10 FLOW-F11
// The lists of the automation editor name each option in words with its app under it, never by its internal name
// («whatsapp_inbox.conversation.list»): what starts it («Choose what happens»), what a step looks up («What to look
// up») and what it does («What to do»), in English and in Spanish, at the three sizes. Nothing is saved.
import { expect, type Page, test } from '@playwright/test';

import { choose } from './flow-helpers';
import { A, capture, horizontalOverflow, login, shown } from './helpers';

const SIZES = [
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1280x720', width: 1280, height: 720 },
];
const LANGUAGES = [
  { code: 'en', happens: 'Something happens', event: 'a task is completed', query: 'Look for tasks', command: 'Create a task', app: 'Tasks' },
  { code: 'es', happens: 'Pasa algo', event: 'se completa una tarea', query: 'Buscar tareas', command: 'Crear una tarea', app: 'Tareas' },
];
/** How the server names an event or an operation: `<app>.<entity>.<action>`. */
const INTERNAL_NAME = /\b[a-z_]+\.[a-z_]+\.[a-z_]+\b/;

/** Opens the list of the `Combo` `testid`: no option says an internal name, and `id` reads its `words` over its `app`. */
async function listsInWords(page: Page, testid: string, id: string, words: string, app: string): Promise<void> {
  await shown(page).locator(`[data-testid=${testid}] input`).click();
  const options = page.locator(`[data-testid^=${testid}-option-]`);
  await expect(options.first()).toBeVisible();
  for (const text of await options.allInnerTexts()) expect(text, testid).not.toMatch(INTERNAL_NAME);
  await expect(page.locator(`[data-testid="${testid}-option-${id}"]`)).toHaveText(`${words} ${app}`);
}

for (const language of LANGUAGES) {
  for (const size of SIZES) {
    test(`FLOW-F10 y FLOW-F11: each option of the editor's lists says its words and its app, never its internal name, in ${language.code} at ${size.label}`, async ({ browser }) => {
      const context = await browser.newContext({ baseURL: A, viewport: size });
      const page = await context.newPage();
      try {
        await login(page, A, '/');
        await context.addCookies([{ name: 'django_language', value: language.code, domain: new URL(A).hostname, path: '/' }]);
        await page.goto(`${A}/flow/automations/new`);
        await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language.code}`));
        const editor = shown(page);
        await expect(editor.locator('[data-testid=flow-editor-nosteps]')).toBeVisible();

        await editor.locator('[data-testid=flow-trigger-open]').click();
        await choose(page, 'flow-trigger-kind', language.happens);
        await listsInWords(page, 'flow-trigger-event', 'task.task.completed', language.event, language.app);
        await page.keyboard.press('Escape');

        await editor.locator('[data-testid=flow-editor-add-query]').click();
        await listsInWords(page, 'flow-step-action-s1', 'task.task.list', language.query, language.app);
        expect(await horizontalOverflow(page), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
        await capture(page, `FLOW-F11-what-to-look-up-${language.code}-${size.label}`);
        await page.keyboard.press('Escape');

        await editor.locator('[data-testid=flow-editor-add-command]').click();
        await listsInWords(page, 'flow-step-action-s2', 'task.task.create', language.command, language.app);
      } finally {
        await context.close();
      }
    });
  }
}
