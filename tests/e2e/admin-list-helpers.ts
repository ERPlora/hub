// How a list of the Hub admin (hubs.erplora.com/admin) sits at a phone's, two tablets' and a desktop's width. Django
// draws the list's table inside its own box (`.results`, `overflow-x: auto`): the page reads no sideways scroll while the
// box asks for it and the last columns are out of sight, so both are measured.
import { type Browser, expect, type Locator, type Page } from '@playwright/test';

import { managePy } from './global-setup';
import { horizontalOverflow } from './helpers';
import { STACK } from './stack';

export const ADMIN_LIST_SIZES = [
  { label: '375', viewport: { width: 375, height: 667 } },
  { label: '768', viewport: { width: 768, height: 1024 } },
  // The tablet the fleet looks at: the filter must still be under the list here (a cut at 800 px passes 768).
  { label: '820', viewport: { width: 820, height: 1180 } },
  { label: '1280', viewport: { width: 1280, height: 860 } },
];

/** Runs `python` in control's shell (the registry of hubs, never a business) and returns the last line it printed. */
export function inControl(python: string[]): string {
  const out = managePy(STACK.database)(['shell', '-c', python.join('\n')]);
  if (out.status !== 0) throw new Error(`control's shell exited with ${out.status}:\n${out.stdout}\n${out.stderr}`);
  return out.stdout.trim().split('\n').at(-1) ?? '';
}

/** Python for `inControl` that makes `username` a superuser of the platform once and prints its session's key last. */
export function staffSession(username: string): string[] {
  return [
    'from django.contrib.auth import get_user_model',
    'from django.test import Client',
    `root = get_user_model().objects.filter(username="${username}").first()`,
    `root = root or get_user_model().objects.create_superuser("${username}", "${username}@example.com", None)`,
    'client = Client()',
    'client.force_login(root)',
    'print(client.cookies["sessionid"].value)',
  ];
}

/** A page of the platform's admin signed in with `session`, at `viewport` and in `locale` (the browser's own without
 *  one); its context is closed by whoever opened it. */
export async function adminPage(
  browser: Browser,
  session: string,
  viewport: { width: number; height: number },
  locale?: string,
): Promise<Page> {
  const context = await browser.newContext({ viewport, locale });
  await context.addCookies([{ name: 'sessionid', value: session, domain: 'hubs.localhost', path: '/' }]);
  return context.newPage();
}

/** How the cell of `column` (its `list_display` name) of `row` sits: by how many pixels its text runs past the cell and
 *  the list's box past its own width (both 0 when it fits), and on how many lines its text is laid out. */
async function laidOut(row: Locator, column: string): Promise<{ pastItsCell: number; pastTheList: number; lines: number }> {
  return row.locator(`td.field-${column}`).evaluate((cell) => {
    const list = cell.closest('.results') as HTMLElement;
    const text = document.createRange();
    text.selectNodeContents(cell);
    const tops = new Set([...text.getClientRects()].map((line) => Math.round(line.top)));
    return {
      pastItsCell: Math.max(0, cell.scrollWidth - cell.clientWidth),
      pastTheList: Math.max(0, list.scrollWidth - list.clientWidth),
      lines: tops.size,
    };
  });
}

/** The long text of `row`'s cell of `column` (`what` names it) breaks into several lines inside its cell, and neither
 *  the list's box nor the page asks to be scrolled sideways. Soft: a failing size says every measure at once. */
export async function expectBrokenInItsCell(page: Page, row: Locator, column: string, what: string): Promise<void> {
  const sits = await laidOut(row, column);
  expect.soft(sits.pastItsCell, `${what} runs past its cell`).toBe(0);
  expect.soft(sits.pastTheList, 'the list asks to be scrolled sideways').toBe(0);
  expect.soft(await horizontalOverflow(page), 'the page asks to be scrolled sideways').toBe(0);
  expect.soft(sits.lines, `${what} breaks into several lines`).toBeGreaterThan(1);
}
