// The plan's space is one check of base (FIX-HUB-BASE-PLAN-SPACE-CHECK-COPIED-IN-THREE-APPS): Files and the website's
// images refused past it each with a copy of its code and its sentence; now both refuse through the same one. In
// Spanish, as the owner of hub `a` with a plan of 1 MB: Files refuses a second file of 600 KB with «No queda espacio…»
// in its notice and keeps nothing, and with the space then exactly full, Files' upload and the website's image upload
// answer the same 409 `base.file_no_space` with that very sentence. A capture of the notice per viewport.
//
// Every test starts and ends with the business's files emptied and the photo of hub `a` as it was; what its apps keep
// (the website's images) stays, and counts.
// flow: base-plan-space-check
import { crc32, deflateSync } from 'node:zlib';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, hostPage, psql, shown } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;
const KEY = 'FIX-HUB-BASE-PLAN-SPACE-CHECK-COPIED-IN-THREE-APPS';
const MB = 1024 * 1024;
/** What the person reads past the plan's space in Spanish, as Files said it before the check was shared. */
const NO_SPACE = 'No queda espacio para ese archivo: tu plan incluye 1 MB.';

interface Listing {
  folders: { path: string }[];
  files: { path: string; name: string }[];
  space: { used_bytes: number };
}
interface Refusal {
  error: { code: string; message: string; fields?: Record<string, string> };
}

/** A grey PNG of `width`×`height` (8-bit greyscale, no filter): a new one is never kept yet. */
function png(width: number, height: number): Buffer {
  const chunk = (type: string, data: Buffer) => {
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(body));
    return Buffer.concat([length, body, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header.set([8, 0, 0, 0, 0], 8);
  const rows = Buffer.alloc((width + 1) * height, 0x99);
  for (let y = 0; y < height; y++) rows[y * (width + 1)] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(rows)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

/** Empties the business's files at `origin` with the owner's session, through `base.file.delete`. */
async function wipe(context: BrowserContext, origin: string): Promise<void> {
  const { status, data } = await api<Listing>(context, origin, 'GET', '/files');
  expect(status, `the listing of ${origin}`).toBe(200);
  for (const path of [...data.folders.map((f) => f.path), ...data.files.map((f) => f.path)]) {
    const gone = await api(context, origin, 'POST', '/files/delete', { path });
    expect(gone.status, `deleting ${path} at ${origin}`).toBe(200);
  }
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const item = (page: Page, path: string) => shown(page).locator(`[data-item="${path}"]`);
const toast = (page: Page, text: string) => page.locator('ion-toast').filter({ hasText: text }).last();

async function upload(page: Page, name: string, size: number): Promise<void> {
  await testid(page, 'files-upload-input').setInputFiles([
    { name, mimeType: 'application/octet-stream', buffer: Buffer.alloc(size, 7) },
  ]);
}

test.describe.configure({ mode: 'serial' });

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  test(`base-plan-space-check — past the plan's space, Files and the website refuse with the same sentence in Spanish at ${label}`, async ({
    browser,
  }) => {
    // The photo of hub `a` with a plan of 1 MB of space, as erplora.com sends it (`plan.max_storage_bytes`).
    const before = psql("select state::text from base_hub where slug = 'a'");
    psql(`update base_hub set state = state || '{\\"plan\\": {\\"max_storage_bytes\\": ${MB}}}' where slug = 'a'`);
    const { context, page } = await hostPage(browser, A, { viewport, next: '/files' });
    // In Spanish (the Hub's language cookie, as the sign-in sets it): the screen and the server's answers.
    await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
    try {
      await wipe(context, A);
      // What `a`'s apps keep counts too (an earlier spec's website images): the first file tops it up to 600 KB.
      const kept = (await api<Listing>(context, A, 'GET', '/files')).data.space.used_bytes;
      expect(kept, 'what the apps of `a` keep leaves room for the test').toBeLessThan(600 * 1024);
      await page.reload();
      await expect(testid(page, 'files-empty')).toBeVisible();

      await upload(page, 'scan.dat', 600 * 1024 - kept);
      await expect(item(page, 'scan.dat')).toBeVisible();
      // Past the plan's space, Files refuses with the sentence and keeps nothing.
      await upload(page, 'second.dat', 600 * 1024);
      await expect(toast(page, `No se pudo subir «second.dat»: ${NO_SPACE}`)).toBeVisible();
      await expect(item(page, 'second.dat')).toHaveCount(0);
      await page.mouse.move(0, 0);
      expect(await horizontalOverflow(page), `${label}: no sideways scroll`).toBeLessThanOrEqual(0);
      await capture(page, `${KEY}-${label}`);

      // The space exactly full: any new byte goes past it, for Files and for the website's images alike.
      const fill = await api(context, A, 'POST', '/files/upload', {
        folder: '',
        name: 'fill.dat',
        content_base64: Buffer.alloc(MB - 600 * 1024, 7).toString('base64'),
      });
      expect(fill.status, 'filling the plan to the byte').toBe(200);
      const byFiles = await api<Refusal>(context, A, 'POST', '/files/upload', {
        folder: '',
        name: 'one more.dat',
        content_base64: Buffer.from('x').toString('base64'),
      });
      // A picture never kept before (its file is named by its content: one kept would take no more space).
      const picture = png(3, 1 + (Date.now() % 997));
      const byWebsite = await api<Refusal>(context, A, 'POST', '/website/images', {
        filename: 'logo.png',
        content_type: 'image/png',
        data_base64: picture.toString('base64'),
      });
      for (const [who, answer] of [
        ['Files', byFiles],
        ['the website', byWebsite],
      ] as const) {
        expect([answer.status, answer.data.error.code, answer.data.error.message, answer.data.error.fields], who).toEqual([
          409,
          'base.file_no_space',
          NO_SPACE,
          undefined,
        ]);
      }
    } finally {
      psql(`update base_hub set state = '${before.replaceAll('"', '\\"')}' where slug = 'a'`);
      await wipe(context, A).catch(() => undefined);
      await context.close();
    }
  });
}
