// The two detectors the e2e runs in the page itself: what moves on it, and whether a screenshot repeats the top of
// the page at its bottom. The waits and the captures of helpers.ts use them.
import type { Page } from '@playwright/test';

/**
 * What moves on the page now (run in the page, so self-contained): every finite animation running in the document
 * and in every open shadow root under it, however deep. `document.getAnimations()` leaves shadow roots out, and Ionic
 * animates its overlays (`ion-modal`, `ion-popover`), an `ion-progress-bar`'s bar or an `ion-segment`'s
 * indicator inside theirs. Endless ones (spinners, a shimmer) never stop, so they never count.
 */
export function movingInPage(): string[] {
  const roots: Array<Document | ShadowRoot> = [document];
  const moving: string[] = [];
  for (const root of roots) {
    for (const element of root.querySelectorAll('*')) if (element.shadowRoot) roots.push(element.shadowRoot);
    for (const animation of root.getAnimations()) {
      if (animation.playState !== 'running' || animation.effect?.getTiming().iterations === Infinity) continue;
      const target = (animation.effect as KeyframeEffect | null)?.target;
      moving.push(`${root instanceof ShadowRoot ? `${root.host.localName} › ` : ''}${target?.localName ?? '?'}`);
    }
  }
  return moving;
}

/** The fewest rows `repeatedTop` counts as a stripe. */
const STRIPE_MIN_ROWS = 8;

/**
 * How many rows at the bottom of `png`, a screenshot of `page`, repeat the first rows of the image: 0 when none. It is
 * what a capture taken before the browser painted the page at its new size shows (the area the resize uncovered,
 * filled with the top of the page): evidence of a screen nobody saw. A stripe whose rows are each one flat colour (a
 * background at both ends, a hairline across it) does not count, nor one that is the same row over and over, whatever
 * its colours across: a background crossed by a border (the assistant's panel, all the screen on a phone, with its left
 * border; a card's veil over it). The top of the page a capture before the paint repeats is its topbar, rows unlike
 * each other. Decoded in `page`'s browser: the e2e has no image library. Ported from erplora.com's e2e (`repeatedTop`
 * of its tests/e2e/panel/fixtures.ts).
 */
export async function repeatedTop(page: Page, png: Buffer): Promise<number> {
  return page.evaluate(
    async ({ base64, minRows }) => {
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const { width, height } = bitmap;
      const context = new OffscreenCanvas(width, height).getContext('2d');
      if (!context) throw new Error('repeatedTop: no 2d context to read the screenshot');
      context.drawImage(bitmap, 0, 0);
      const pixels = new Uint32Array(context.getImageData(0, 0, width, height).data.buffer);
      const sameRow = (a: number, b: number) => {
        for (let x = 0; x < width; x++) if (pixels[a * width + x] !== pixels[b * width + x]) return false;
        return true;
      };
      const flatRow = (row: number) => {
        for (let x = 1; x < width; x++) if (pixels[row * width + x] !== pixels[row * width]) return false;
        return true;
      };
      for (let rows = Math.floor(height / 2); rows >= minRows; rows--) {
        let repeated = true;
        let flat = true;
        let uniform = true;
        for (let row = 0; row < rows && repeated; row++) {
          repeated = sameRow(height - rows + row, row);
          flat &&= flatRow(row);
          uniform &&= sameRow(row, 0);
        }
        if (repeated && !flat && !uniform) return rows;
      }
      return 0;
    },
    { base64: png.toString('base64'), minRows: STRIPE_MIN_ROWS },
  );
}
