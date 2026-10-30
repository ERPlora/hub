// What the specs of the website editor (website*.spec.ts and the fixes seen in it) share and the rest of the e2e does not.
import { expect, type Page } from '@playwright/test';

import { settled } from './helpers';

/**
 * The page at rest for its capture: no focus ring (the website's own step), then the harness's one wait, `settled`
 * (helpers.ts): nothing moving, in the document or in any shadow root (Bootstrap's buttons fade 150 ms, the dev server
 * injects the stylesheets after the first paint, and in the editor Ionic animates its dialogs and toasts in theirs),
 * and the page painted as it is now.
 */
export async function atRest(page: Page): Promise<void> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await settled(page);
}

/** The editor's section `name` (`website-section-<name>`) opened, if it was not already. */
export async function openSection(page: Page, name: string): Promise<void> {
  const accordion = page.getByTestId(`website-section-${name}`);
  if ((await accordion.getAttribute('class'))?.includes('accordion-expanded')) return;
  await accordion.locator('ion-item[slot="header"]').click();
  await expect(accordion).toHaveClass(/accordion-expanded/);
}

/** A photo drawn in the page (no binary in the repository): a gradient with `label` in a corner, as a JPEG. */
export async function photo(page: Page, label: string, hue: number): Promise<Buffer> {
  const url = await page.evaluate(
    ({ label, hue }) => {
      const canvas = document.createElement('canvas');
      canvas.width = 600;
      canvas.height = 600;
      const draw = canvas.getContext('2d') as CanvasRenderingContext2D;
      const gradient = draw.createLinearGradient(0, 0, 600, 600);
      gradient.addColorStop(0, `hsl(${hue}, 70%, 70%)`);
      gradient.addColorStop(1, `hsl(${hue + 40}, 60%, 35%)`);
      draw.fillStyle = gradient;
      draw.fillRect(0, 0, 600, 600);
      draw.fillStyle = 'rgba(255, 255, 255, 0.9)';
      draw.font = '600 48px Georgia, serif';
      draw.fillText(label, 40, 560);
      return canvas.toDataURL('image/jpeg', 0.86);
    },
    { label, hue },
  );
  return Buffer.from(url.slice(url.indexOf(',') + 1), 'base64');
}
