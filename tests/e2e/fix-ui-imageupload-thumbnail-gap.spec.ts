// flow: ui-imageupload-thumbnail-gap — FIX of @erplora/ui's ImageUpload (FIX-UI-IMAGEUPLOAD-THUMBNAIL-TOUCHES-TEXT)
// In Website every image field (the logo, the cover, each photo of the gallery) is an ImageUpload: its thumbnail sits
// in an ion-item's `slot="start"`, whose 16px gap to the text (md and ios) is a `::slotted` margin of the item's shadow.
// Tailwind's preflight (`margin: 0`, a document rule) wiped it, and the thumbnail touched «Cover photo» and «Photo 1».
// Here, at 390, 834 and 1440, the empty cover and a gallery photo with its image: the text starts the thumbnail's own
// margin after it (the token, at least 12px), the thumbnail stays 64×64 with its margin above and below, and nothing
// (title, rules, «Choose image», «Replace image», «Remove») overlaps it, leaves its row or is cut. The shell pins Ionic
// to ios, so md is measured on a copy of each field marked `mode="md"`, laid out at its width and removed. The site's
// draft is put back as it was.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, hostPage, record } from './helpers';
import { atRest, openSection, photo } from './website-helpers';

const KEY = 'FIX-UI-IMAGEUPLOAD-THUMBNAIL-TOUCHES-TEXT';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;
/** The smallest gap between the thumbnail and its text. */
const MIN_GAP = 12;

interface Draft {
  template: string;
  theme: Record<string, unknown>;
  content: Record<string, Record<string, unknown>>;
}

/** How an ImageUpload is laid out, in the mode Ionic gave its item. */
interface Layout {
  mode: string;
  /** The text's left edge minus the thumbnail's right edge. */
  gap: number;
  /** The thumbnail's `margin-inline-end`, in px. */
  margin: number;
  size: [number, number];
  marginBlock: [string, string];
  /** Parts that come closer than MIN_GAP to the thumbnail, run past the item or are cut. */
  problems: string[];
}

/** Measures the ImageUpload `root`; with `md`, a copy of it marked `mode="md"`, laid out at its width and then removed. */
async function layout(root: Locator, md = false): Promise<Layout> {
  return root.evaluate(
    async (original, { md, minGap }) => {
      let field = original as HTMLElement;
      if (md) {
        field = original.cloneNode(true) as HTMLElement;
        // A fresh copy: no mode class of the original, no test id twice on the page.
        for (const el of [field, ...field.querySelectorAll<HTMLElement>('*')]) {
          el.classList.remove('ios', 'hydrated');
          el.removeAttribute('data-testid');
        }
        field.setAttribute('mode', 'md');
        // At the original's width, out of its row (a gallery row is a flex row that would squeeze a second child).
        const width = original.getBoundingClientRect().width;
        field.style.cssText = `position: fixed; inset-inline-start: 0; inset-block-start: 0; width: ${width}px; z-index: 99999;`;
        document.body.append(field);
        const ready = [...field.querySelectorAll('*')].map(
          (el) => (el as HTMLElement & { componentOnReady?: () => Promise<unknown> }).componentOnReady?.() ?? null,
        );
        await Promise.all(ready);
        await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
      }
      try {
        const item = field.querySelector('ion-item') as HTMLElement;
        const thumb = field.querySelector('ion-thumbnail') as HTMLElement;
        const body = field.querySelector('.image-upload__body') as HTMLElement;
        const edge = thumb.getBoundingClientRect();
        const row = item.getBoundingClientRect();
        const style = getComputedStyle(thumb);
        const problems: string[] = [];
        for (const part of field.querySelectorAll<HTMLElement>('ion-label h3, ion-label p, ion-button')) {
          const box = part.getBoundingClientRect();
          if (!box.width) continue;
          const name = `${part.tagName.toLowerCase()} «${(part.textContent ?? '').trim()}»`;
          if (box.left < edge.right + minGap - 0.5) problems.push(`${name} starts ${(box.left - edge.right).toFixed(1)}px after the thumbnail`);
          if (box.right > row.right + 0.5) problems.push(`${name} runs ${(box.right - row.right).toFixed(1)}px past its row`);
          const native = part.shadowRoot?.querySelector('.button-native') as HTMLElement | null;
          if (native && native.scrollWidth > native.clientWidth + 1) problems.push(`${name} is cut`);
        }
        return {
          mode: item.classList.contains('md') ? 'md' : item.classList.contains('ios') ? 'ios' : 'none',
          gap: body.getBoundingClientRect().left - edge.right,
          margin: parseFloat(style.marginInlineEnd),
          size: [edge.width, edge.height] as [number, number],
          marginBlock: [style.marginTop, style.marginBottom] as [string, string],
          problems,
        };
      } finally {
        if (md) field.remove();
      }
    },
    { md, minGap: MIN_GAP },
  );
}

function expectGap(found: Layout, where: string): void {
  expect(found.problems, `${where}: overlaps`).toEqual([]);
  expect(found.gap, `${where}: gap from the thumbnail to the text`).toBeGreaterThanOrEqual(MIN_GAP);
  expect(Math.abs(found.gap - found.margin), `${where}: the gap is the thumbnail's margin (${found.margin}px)`).toBeLessThanOrEqual(1);
  expect(found.size, `${where}: thumbnail size`).toEqual([64, 64]);
  expect(found.marginBlock, `${where}: thumbnail margin above and below`).toEqual(['12px', '12px']);
}

let owner: { context: BrowserContext; page: Page };
let kept: Draft;

test.beforeAll(async ({ browser }) => {
  owner = await hostPage(browser, A, { next: '/website', viewport: { width: 1440, height: 900 } });
  // The owner's session for the fleet's visual sweep of the editor (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await owner.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  const site = await api<Draft>(owner.context, A, 'GET', '/website/site');
  expect(site.status).toBe(200);
  kept = { template: site.data.template, theme: site.data.theme, content: site.data.content };
});

test.afterAll(async () => {
  if (!owner) return;
  await owner.page.goto('about:blank');
  const restored = await api(owner.context, A, 'POST', '/website/site', kept);
  expect(restored.status, JSON.stringify(restored.data)).toBe(200);
  await owner.context.close();
});

test('ui-imageupload-thumbnail-gap: in Website the image fields keep their gap from the thumbnail to the text, at 390, 834 and 1440, in ios and md', async () => {
  const { page } = owner;
  // The cover empty and the gallery empty, then one photo through the gallery's own upload.
  const content = {
    ...kept.content,
    hero: { ...kept.content.hero, cover: null },
    gallery: { ...kept.content.gallery, hidden: false, images: [] },
  };
  const saved = await api(owner.context, A, 'POST', '/website/site', { ...kept, content });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  await page.goto(`${A}/website`);
  await expect(page.getByTestId('website-editor')).toBeVisible({ timeout: 30_000 });
  await openSection(page, 'gallery');
  await page.getByTestId('website-gallery-add-file').setInputFiles({
    name: 'work.jpg',
    mimeType: 'image/jpeg',
    buffer: await photo(page, 'Work', 160),
  });
  await expect(page.getByTestId('website-gallery-photo-0-image')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('website-save-state')).toHaveText(/All changes saved/, { timeout: 15_000 });

  const cover = page.getByTestId('website-image-cover');
  const galleryPhoto = page.getByTestId('website-gallery-photo-0');
  await expect(page.getByTestId('website-image-cover-empty')).toBeVisible();
  const measured: Record<string, Layout> = {};
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    for (const [name, field] of [
      ['cover', cover],
      ['gallery photo', galleryPhoto],
    ] as const) {
      await field.scrollIntoViewIfNeeded();
      const ios = await layout(field);
      measured[`${name} ${size.label} ios`] = ios;
      expect(ios.mode, `${name} at ${size.label}`).toBe('ios');
      expectGap(ios, `${name} at ${size.label} (ios)`);
      const md = await layout(field, true);
      measured[`${name} ${size.label} md`] = md;
      expect(md.mode, `${name} copy at ${size.label}`).toBe('md');
      expectGap(md, `${name} at ${size.label} (md)`);
    }
    await expect.poll(() => horizontalOverflow(page), `sideways scroll at ${size.label}`).toBeLessThanOrEqual(1);
    // The gallery photo with its buttons at the bottom: on a tablet and a computer the cover shows above it.
    await galleryPhoto.evaluate((el) => el.scrollIntoView({ block: 'end' }));
    await atRest(page);
    await capture(page, `${KEY}-${size.label}`);
  }
  record(KEY, measured);
});
