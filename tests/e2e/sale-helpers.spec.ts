// flow: ninguno — FIX tests/e2e (ayudante `tillIsPhone` de las e2e de Ventas; rv-hub-292)
// `tillIsPhone` (sale-helpers.ts) answers for the window the page is in, never for the size before. The till lays itself
// out a frame after a resize (its media query and its ResizeObserver), and the specs that read its cart button straight
// after `setViewportSize` tapped the previous size's button. On a real till that late frame is too short to catch every
// time, so this page stands in for a till that is slow on purpose: it changes `pos-till--phone` 1.5 s after its media
// query changes. The lag is the page's; the test waits for nothing. No stack: the page is written in place.
import { expect, test } from '@playwright/test';

import { tillIsPhone } from './sale-helpers';

/** A till as `PosPage.vue` marks it (`pos-till`, `pos-till--phone` by its media query) inside a shown page, slow to
 *  follow the window: its class catches up `lag` ms after the media query changes. */
const slowTill = (lag: number) => `
  <div class="ion-page">
    <div class="pos-till" data-testid="pos-till">till</div>
  </div>
  <script>
    const till = document.querySelector('[data-testid=pos-till]');
    const media = matchMedia('(max-width: 820px), (max-height: 500px)');
    const follow = () => till.classList.toggle('pos-till--phone', media.matches);
    follow();
    media.addEventListener('change', () => setTimeout(follow, ${lag}));
  </script>`;

test('tillIsPhone answers for the window the till is in now, not for the size before, however late the till follows', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.setContent(slowTill(1500));
  expect(await tillIsPhone(page), 'a phone at 390').toBe(true);
  await page.setViewportSize({ width: 834, height: 1112 });
  expect(await tillIsPhone(page), 'no phone at 834, straight after 390').toBe(false);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await tillIsPhone(page), 'a phone at 390, straight after 834').toBe(true);
  await page.setViewportSize({ width: 1440, height: 900 });
  expect(await tillIsPhone(page), 'no phone at 1440, straight after 390').toBe(false);
});
