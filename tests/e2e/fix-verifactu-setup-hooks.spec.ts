// flow: HUB_HOME verifactu hooks
// VeriFactu's hooks of the Home (its `setup` and `widgets`), as the owner of hub `a` reads them in Spanish: «Configura
// VeriFactu» pending and «Importante» in «Termina de configurar tu negocio» while ERPlora still has no approved
// authorisation (its «Configurar» leads to VeriFactu's Configuration), done without a reload once the account's photo
// approves it; «Pendientes VeriFactu» on the board by default with the server's figure, and the other three panels
// («Cola de contingencia», «Registros por estado», «Eventos AEAT recientes», whose types speak Spanish, never their
// codes) on the board in each size, leaving a capture.
// The photo is sent the way the SaaS sends it (`PUT /internal/hubs/{id}/state`, signed); what the run changes in
// VeriFactu's configuration and in `a`'s photo is put back after it (or removed, if the run made it).
import { expect, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, psql, shot, untilStill } from './helpers';
import { boardWidget, setupCard, setupStep, spanishOwnerWithPanels as spanishOwner } from './home-helpers';
import { keepVerifactu, pushPhoto, putVerifactuBack } from './verifactu-helpers';

const KEY = 'FIX-VERIFACTU-SETUP-HOOKS';
const STEP = 'verifactu.sending_route';
const PANELS = ['verifactu.pending', 'verifactu.contingency', 'verifactu.by_status', 'verifactu.events'];
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */

test.beforeAll(() => {
  keepVerifactu('e2e_fix_vf_hooks');
});

test.afterAll(() => {
  putVerifactuBack();
});

/** ERPlora files, and its authorisation is `status`: what the step reads. */
async function erploraWith(status: string): Promise<void> {
  await pushPhoto(status);
  psql("update verifactu_config set route = 'erplora'");
}

const { row, doneUnderTheFold } = setupStep(STEP);

/** «Ver todo» when the fold keeps the step out of sight: on a phone it shows 2 rows, and a hub without its tax details
 *  has «Los datos de tu negocio» (⛔, before VeriFactu's) pending too. */
async function unfolded(page: Page): Promise<void> {
  await expect(setupCard(page)).toHaveAttribute('aria-busy', 'false');
  const toggle = setupCard(page).locator('[data-testid="setup-toggle"]');
  if ((await row(page).count()) === 0 && (await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
}

test('HUB_HOME verifactu hooks: «Configura VeriFactu» pending until the authorisation is approved, and «Pendientes VeriFactu» by default', async ({ browser }) => {
  await erploraWith('submitted');
  const { context, page } = await spanishOwner(browser, { width: 1440, height: 900 });
  try {
    // Pending while ERPlora's authorisation is under review: «Importante», never «Necesario para facturar».
    await expect(row(page).locator('.setup-row-title')).toHaveText('Configura VeriFactu');
    await expect(row(page).locator('.setup-row-desc')).toHaveText(
      'Firma la autorización para que ERPlora envíe tus facturas a la AEAT, o sube el certificado del negocio.',
    );
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');

    // «Pendientes VeriFactu» on the board by default, with what the server counts.
    const pending = boardWidget(page, 'verifactu.pending');
    await expect(pending.locator('[data-testid="widget-title"]')).toHaveText('Pendientes VeriFactu');
    const summary = await api<{ pending_count: number }>(context, A, 'GET', '/verifactu/stats/compliance_summary');
    expect(summary.status).toBe(200);
    await expect(pending.locator('[data-testid="widget-value"]')).toHaveText(new Intl.NumberFormat('es-ES').format(summary.data.pending_count));
    for (const key of PANELS.slice(1)) await expect(boardWidget(page, key)).toHaveCount(0);

    // «Configurar» leads to VeriFactu's Configuration.
    await row(page).locator(`[data-testid="setup-configure-${STEP}"]`).click();
    await expect(page).toHaveURL(`${A}/verifactu/config`);
    await page.goto(`${A}/`);
    await expect(row(page)).toBeVisible();

    // The account approves it: the step is done without a reload (it leaves the folded list; «Ver todo» says «Hecho»).
    await pushPhoto('approved');
    await doneUnderTheFold(page);
  } finally {
    await context.close();
  }
});

for (const size of SIZES) {
  test(`HUB_HOME verifactu hooks at ${size.label}: the step pending and VeriFactu's four panels on the board`, async ({ browser }) => {
    await erploraWith('none');
    const { context, page } = await spanishOwner(browser, { width: size.width, height: size.height }, PANELS);
    try {
      await unfolded(page);
      await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');
      const titles = ['Pendientes VeriFactu', 'Cola de contingencia', 'Registros por estado', 'Eventos AEAT recientes'];
      for (const [index, key] of PANELS.entries()) {
        await expect(boardWidget(page, key).locator('[data-testid="widget-title"]')).toHaveText(titles[index]);
        await expect(boardWidget(page, key).locator('[data-testid="widget-error"]')).toHaveCount(0);
        await expect(boardWidget(page, key)).toHaveAttribute('aria-busy', 'false');
      }
      // The photo just received is the newest event: its type in Spanish, never its code.
      const events = boardWidget(page, 'verifactu.events');
      await expect(events.locator('[data-testid="verifactu-events-panel-type"]').first()).toHaveText('Configuración cambiada');
      await expect(events).not.toContainText('config_changed');
      await expect(events.locator('[data-testid="verifactu-events-panel-error"]')).toHaveCount(0);
      await expect(boardWidget(page, 'verifactu.by_status').locator('[data-testid="widget-bar"]').first()).toBeVisible();

      // The checklist and the board in sight, as far as the page scrolls, with no sideways scroll.
      await row(page).evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}
