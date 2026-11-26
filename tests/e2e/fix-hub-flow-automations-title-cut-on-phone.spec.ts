// flow: flow-automations-list
// On a phone, in Spanish, the bar of «Automatizaciones» must read its title whole beside «⋮», the help's «?» and the
// bell with a notice pending: at 375 px the bell's pill left «Automatizaci…», and there the bell takes the room of
// one button, its count a badge on its corner. The owner of hub `a` opens the list in Spanish at 375, 390, 834 and
// 1440 px with «Todavía no puedes facturar» in the bell (its issuer parked for the run and put back after it): the
// title is read whole (its `.toolbar-title` not cut with «…»), the help and the bell are on the bar, and «Nueva
// automatización» opens the new automation from the bar, by its icon and its words from a tablet on and as a row of
// «⋮» on a phone. No sideways scroll. Each width leaves its capture. Nothing is created.
import { expect, type Page, test } from '@playwright/test';

import { actionBell } from './action-center';
import { saveSessionForTheSweep, shown, signedInSpanish, untilStill } from './helpers';
import { parkIssuer, unparkIssuer } from './invoice-helpers';
import { capturedFitting } from './screen';
import { topbar, topbarMore, topbarMoreMenu } from './topbar';

const KEY = 'FIX-HUB-FLOW-AUTOMATIONS-TITLE-CUT-ON-PHONE';
const PARKED = 'e2e_flow_title_cut_issuer';
const NEW_AUTOMATION = 'Nueva automatización';
const SIZES = [
  { label: '375', width: 375, height: 667, phone: true },
  { label: '390', width: 390, height: 844, phone: true },
  { label: '834', width: 834, height: 1112, phone: false },
  { label: '1440', width: 1440, height: 900, phone: false },
];

test.beforeAll(() => parkIssuer(PARKED));
test.afterAll(() => unparkIssuer(PARKED));

/** Presses «Nueva automatización» where the bar puts it: on the bar from a tablet on, in «⋮» on a phone. */
async function pressNewAutomation(page: Page, phone: boolean): Promise<void> {
  if (!phone) {
    const words = await shown(page).locator('[data-testid=flow-new]').evaluate((el) => (el as HTMLElement).innerText.trim());
    expect(words, 'its words on the bar').toBe(NEW_AUTOMATION);
    await shown(page).getByRole('button', { name: NEW_AUTOMATION, exact: true }).click();
    return;
  }
  await topbarMore(page).click();
  await topbarMoreMenu(page).getByRole('button', { name: NEW_AUTOMATION, exact: true }).click();
}

for (const size of SIZES) {
  test(`flow-automations-list at ${size.label}: «Automatizaciones» read whole beside the help and the bell`, async ({ browser }) => {
    const { context, page } = await signedInSpanish(browser, { width: size.width, height: size.height }, '/flow/automations');
    await saveSessionForTheSweep(context);
    try {
      // The list as the owner reads it: its gallery painted, nothing still loading, the bell with its notice.
      await expect(shown(page).locator('[data-testid^=flow-card-open-]').first()).toBeVisible();
      await expect(shown(page).locator('.flow-page__loading')).toHaveCount(0);
      await expect(actionBell(page)).toHaveClass(/has-notices/);
      await untilStill(page);

      const heading = topbar(page).locator('ion-title');
      await expect(heading).toContainText('Automatizaciones');
      const cut = await heading.evaluate((el) => {
        const box = (el.shadowRoot?.querySelector('.toolbar-title') ?? el) as HTMLElement;
        return box.scrollWidth > box.clientWidth;
      });
      expect(cut, `the title «Automatizaciones» at ${size.label} is read whole`).toBe(false);
      await expect(topbar(page).getByRole('button', { name: 'Ayuda', exact: true })).toBeVisible();
      await expect(actionBell(page)).toBeVisible();

      await capturedFitting(page, `${KEY}-${size.label}`, size.label);

      await pressNewAutomation(page, size.phone);
      await page.waitForURL(/\/flow\/automations\/new$/);
    } finally {
      await context.close();
    }
  });
}
