// flow: printing-locale — FIX-HUB-PRINTING-ES-TEXTS-SHADOWED-BY-AN-EARLIER-APP (PRINTING-F14): Django joins every
// app's Spanish catalogue and the first that translates a message wins, so printing's job «Cancelled» read
// appointment's «Cancelada». The owner opens «Cancel» on a job of the queue, someone else cancels it meanwhile (by
// the API), and the cancel window says the server's refusal as it came: «… este está cancelado.», a job's word,
// never «cancelada». In Spanish, at 390, 834 and 1440. What this file makes carries its own reference and goes away.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
import { dialog } from './inventory-helpers';
import { FLOW_VIEWPORTS } from './printing-helpers';
import { stamp } from './sale-helpers';

const KEY = 'FIX-HUB-PRINTING-ES-TEXTS-SHADOWED-BY-AN-EARLIER-APP';
const PREFIX = 'e2e-locale';
const REF = `${PREFIX}-${stamp()}`;
/** printing's catalogue (`apps/printing/locale/es/LC_MESSAGES/django.po`), letter by letter. */
const REFUSED = 'Un trabajo que se está imprimiendo o ya se imprimió no se cancela; este está cancelado.';

function cleanUp(): void {
  psql(`delete from printing_printjob where reference like '${PREFIX}-%'`);
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/** The owner on `a` in Spanish: the Hub's language cookie, as the sign-in sets it from the account. */
async function spanishOwner(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1440, height: 900 }, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/printing/jobs');
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  return { context, page };
}

async function cancelAction(page: Page, id: string): Promise<void> {
  const hook = `printing-jobs-row-${id}-cancel`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=printing-jobs-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

test('printing-locale: a job cancelled meanwhile is refused as «cancelado» in the cancel window', async ({ browser }) => {
  const { context, page } = await spanishOwner(browser);
  try {
    const queued = await api<{ job: { id: string } }>(context, A, 'POST', '/printing/jobs', {
      document_type: 'kitchen_order',
      document: { order_number: 7, table: '4', items: [{ name: 'Paella', quantity: 2 }] },
      source_ref: REF,
      job_key: REF,
    });
    expect(queued.status).toBe(201);
    const id = queued.data.job.id;

    await page.goto(`${A}/printing/jobs`);
    await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
    const row = shown(page).locator('[data-testid=printing-jobs-row]').filter({ hasText: REF });
    await expect(row).toContainText('Pendiente');
    await cancelAction(page, id);
    const modal = dialog(page, 'printing-cancel-job');
    await expect(modal).toBeVisible();

    // Someone else cancels it first.
    expect((await api(context, A, 'POST', '/printing/jobs/cancel', { job_id: id, reason: 'e2e' })).status).toBe(200);
    await modal.locator('[data-testid=printing-cancel-job-submit]').click();
    const error = modal.locator('[data-testid=printing-cancel-job-error]');
    await expect(error).toHaveText(REFUSED);
    await expect(error).not.toContainText('cancelada');

    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await expect(error).toHaveText(REFUSED);
      await capture(page, `${KEY}-${viewport.label}`);
    }
  } finally {
    await context.close();
  }
});
