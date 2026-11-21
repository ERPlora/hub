// What the Kitchen specs share: the three sizes their screens are captured at, and the capture at each of them.
import type { Page } from '@playwright/test';

import { capture as captureScreen } from './helpers';

export const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** The built app can load Ionic's label styles after the theme, and Vite's dev server before it: moves them last, so a
 *  rule of a ticket that only ties with Ionic's loses here as it does in the app. */
export async function ionicLabelStylesLast(page: Page): Promise<void> {
  await page.evaluate(() => {
    const ionic = Array.from(document.querySelectorAll('style')).find((style) => style.textContent?.includes('.item.sc-ion-label-ios-h'));
    if (!ionic) throw new Error('Ionic label styles not found');
    ionic.parentElement?.append(ionic);
  });
}

/** Captures `APP-KITCHEN-<flow>-<size>` at each size once `ready` holds there, and leaves the page at 1440×900. */
export async function capture(page: Page, flow: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await captureScreen(page, `APP-KITCHEN-${flow}-${size.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}
