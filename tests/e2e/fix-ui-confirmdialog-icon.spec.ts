// The icon of a dialog's confirm button keeps its distance from the label (FIX-UI-CONFIRMDIALOG-ICON-GAP): in
// Staff → Staff, «Deactivate» on a member asked with «⊘Deactivate», the icon against the word, while the list's
// «+ Add» kept its gap. Tailwind's preflight (`* { margin: 0 }`) is a document rule, and a document rule beats the
// `::slotted(ion-icon[slot=start])` margin Ionic gives an icon inside `ion-button`: every `ion-button` with a
// `HubIcon slot="start"` lost it (the DataTable puts its own back). Measured in the page at 390×844, 834×1112 and
// 1440×900 (the shell pins Ionic's ios mode, ADR-0143; md has the same rule): from the icon's right edge to the
// label's first letter, Ionic's 0.3em of the icon, and the same gap from the spinner while the confirmation runs.
// Only the gap comes back: the outer side (`margin-inline-start`) stays `0px`, as on main, or every SaaS button
// that sets only its own gap pulled its icon into the padding (saas#54). What the run creates is deleted.
// flow: ui:ConfirmDialog
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';

const TAG = 'E2E Gap';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

function cleanup(): void {
  psql(`delete from staff_member where first_name like '${TAG}%'`);
}

test.beforeAll(cleanup);
test.afterAll(cleanup);

async function ownerPage(browser: Browser) {
  const context = await browser.newContext({ baseURL: A, viewport: VIEWPORTS[0], locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/staff/members');
  return { context, page };
}

interface Gap {
  /** From the right edge of the icon (or spinner) in `slot="start"` to the first letter of the label, in px. */
  gap: number;
  /** The font size of what sits in `slot="start"`, in px: Ionic's gap is 0.3em of the icon. */
  startFontSize: number;
  /** What sits in `slot="start"`. */
  start: string;
  /** Its margin on the outer side (`margin-inline-start`), as computed. */
  outer: string;
}

/** The gap between a button's start icon (or spinner) and its label, measured on the laid-out page. */
function startGap(button: Locator): Promise<Gap> {
  return button.evaluate((el) => {
    const start = el.querySelector(':scope > [slot="start"]');
    const label = [...el.childNodes].find((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim());
    if (!start || !label?.textContent) throw new Error(`no start icon or no label in ${el.outerHTML}`);
    const first = label.textContent.search(/\S/);
    const range = document.createRange();
    range.setStart(label, first);
    range.setEnd(label, first + 1);
    return {
      gap: range.getBoundingClientRect().left - start.getBoundingClientRect().right,
      startFontSize: parseFloat(getComputedStyle(start).fontSize),
      start: start.tagName.toLowerCase(),
      outer: getComputedStyle(start).marginInlineStart,
    };
  });
}

/** Ionic's own gap: 0.3em of the icon (1.35em of its button), never under 4px; the outer side as on main. */
function expectIonicGap(measured: Gap, what: string): void {
  expect(measured.start, what).toBe('ion-icon');
  expect(measured.outer, `${what}: ${JSON.stringify(measured)}`).toBe('0px');
  expect(measured.gap, `${what}: ${JSON.stringify(measured)}`).toBeGreaterThanOrEqual(4);
  expect(Math.abs(measured.gap - 0.3 * measured.startFontSize), `${what}: ${JSON.stringify(measured)}`).toBeLessThanOrEqual(0.5);
}

/** Opens «Deactivate» on the member's row, from its button or, when the row folded it, from its «⋮» menu. */
async function openDeactivate(page: Page, id: string): Promise<Locator> {
  const button = shown(page).locator(`[data-testid=staff-members-row-${id}-deactivate]`);
  if (await button.isVisible()) await button.click();
  else {
    await shown(page).locator(`[data-testid=staff-members-row-${id}-menu]`).click();
    await page.locator(`ion-popover [data-testid=staff-members-row-${id}-deactivate]`).click();
  }
  const dialog = page.locator('ion-modal[data-testid=staff-member-deactivate]');
  await expect(dialog).toBeVisible();
  return dialog;
}

test('ui:ConfirmDialog — the confirm button keeps its icon apart from «Deactivate», like the list’s «+ Add»', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const name = `${TAG} Ana Icon${stamp}`;
  const { context, page } = await ownerPage(browser);
  try {
    const res = await api<{ id: string }>(context, A, 'POST', '/staff/members', { first_name: `${TAG} Ana`, last_name: `Icon${stamp}` });
    expect(res.status, JSON.stringify(res.data)).toBe(201);
    const id = res.data.id;
    let iconGap = 0;
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${A}/staff/members`);
      await expect(shown(page).locator('[data-testid=staff-members-row]', { hasText: name })).toBeVisible();
      const add = await startGap(shown(page).locator('[data-testid=staff-members-add]'));
      expect(add.gap, `«+ Add» ${vp.label}: ${JSON.stringify(add)}`).toBeGreaterThanOrEqual(4);

      const dialog = await openDeactivate(page, id);
      await expect(dialog).toContainText(`Take ${name} off the floor?`);
      const submit = dialog.locator('[data-testid=staff-member-deactivate-submit]');
      await expect(submit).toHaveText('Deactivate');
      const confirm = await startGap(submit);
      expectIonicGap(confirm, `«Deactivate» ${vp.label}`);
      if (vp === VIEWPORTS[0]) iconGap = confirm.gap;
      await page.waitForTimeout(400);
      await page.screenshot({ path: shot(`FIX-UI-CONFIRMDIALOG-ICON-GAP-${vp.label}`) });
      await dialog.locator('[data-testid=staff-member-deactivate-cancel]').click();
      await expect(dialog).toBeHidden();
    }

    // While the confirmation runs, the spinner takes the icon's place, at the same distance from the label.
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    await page.route('**/api/staff/members/deactivate', async (route) => {
      await held;
      await route.continue();
    });
    await page.setViewportSize(VIEWPORTS[0]);
    await page.goto(`${A}/staff/members`);
    await expect(shown(page).locator('[data-testid=staff-members-row]', { hasText: name })).toBeVisible();
    const dialog = await openDeactivate(page, id);
    const submit = dialog.locator('[data-testid=staff-member-deactivate-submit]');
    await submit.click();
    await expect(submit.locator(':scope > ion-spinner[slot="start"]')).toBeVisible();
    const pending = await startGap(submit);
    expect(pending.start).toBe('ion-spinner');
    expect(pending.outer, `«Deactivate» pending: ${JSON.stringify(pending)}`).toBe('0px');
    expect(Math.abs(pending.gap - iconGap), `«Deactivate» pending: ${JSON.stringify(pending)}, icon ${iconGap}`).toBeLessThanOrEqual(0.5);
    release();
    await expect(dialog).toBeHidden();
  } finally {
    await context.close();
  }
});
