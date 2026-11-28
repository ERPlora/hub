// The preview beside the website's editor shows the draft the server holds. When that draft is saved from outside the
// editor while the page is open (the assistant or another device, both through `website.site.save`, here through the
// API), the editor's fields follow it and the preview reloads on its own, as after a save of the editor: nobody has
// to press «Reload the preview» to see the change. At each of the three sizes (on a phone or a tablet, on the
// «Preview» tab), with its capture. The site is put back as the run found it, offline.
// flow: WEBSITE-F06 WEBSITE-F01
import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow } from './helpers';
import { THREE_SIZES } from './screen';
import { atRest, ownerOfTheSite, type Site, siteBackOffline } from './website-helpers';

const preview = (page: Page) => page.frameLocator('[data-testid="website-preview-frame"]');

/** The draft `found` with `tagline` under the header's title, saved through the API, away from the open editor. */
async function saveTaglineElsewhere(page: Page, found: Site, tagline: string): Promise<void> {
  const content = { ...found.content, hero: { ...found.content.hero, tagline } };
  const saved = await api(page.context(), A, 'POST', '/website/site', { template: found.template, theme: found.theme, content });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
}

test('WEBSITE-F06: a draft saved outside the editor reloads the preview on its own, as the editor follows it', async ({
  browser,
}) => {
  const { owner, found } = await ownerOfTheSite(browser, THREE_SIZES[2]);
  const { page } = owner;
  try {
    await expect(page.getByTestId('website-editor')).toBeVisible({ timeout: 30_000 });
    for (const size of THREE_SIZES) {
      await page.setViewportSize(size);
      const tabs = page.getByTestId('website-view');
      const label = `${size.width}x${size.height}`;
      const tagline = `Market cooking in the centre ${label}`;
      await saveTaglineElsewhere(page, found, tagline);
      await expect(page.getByTestId('website-field-hero-tagline').locator('input')).toHaveValue(tagline);
      if (await tabs.isVisible()) await tabs.locator('ion-segment-button').filter({ hasText: 'Preview' }).click();
      await expect(preview(page).getByText(tagline, { exact: true })).toBeVisible({ timeout: 15_000 });
      expect(await horizontalOverflow(page), `sideways scroll at ${label}`).toBeLessThanOrEqual(1);
      await atRest(page);
      await capture(page, `APP-WEBSITE-PREVIEW-LIVE-${label}`);
      if (await tabs.isVisible()) await tabs.locator('ion-segment-button').filter({ hasText: 'Edit' }).click();
    }
  } finally {
    await siteBackOffline(owner.context, found);
    await owner.context.close();
  }
});
