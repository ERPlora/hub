// Files of the business (APP-BASE-8; the old hub's FilesPage, docs/reference/old-hub/files-*.png) in the three
// viewports, as the owner of hub `a`: from the side menu's «Files», the empty folder; a folder made and two files
// uploaded (a third with a taken name keeps «name (1).ext», a program is refused with its sentence); the tree on the
// left — a «Folders» selector on a narrow screen —, the path, grid and list, «Space»; an image and a text opened in
// the preview and a file downloaded, private (`no-store`, an attachment); renamed and moved to another folder; deleted
// after asking. The employee opens and downloads but changes nothing. Hub `b` never sees, reads nor touches `a`'s, and a
// path that climbs out is refused. Each flow leaves its capture `APP-BASE-8-<G key>-<width>` once nothing scrolls
// sideways.
//
// The stack keeps the files on disk (`MEDIA_ROOT`); every test starts and ends with the business's files emptied
// through the product's own operations.
// flow: BASE-G82 BASE-G83 BASE-G84 BASE-G85 BASE-G86
import { crc32, deflateSync } from 'node:zlib';

import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, B, EMPLOYEE, hostPage, psql, shot, shown, untilStill } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** A 1×1 PNG. */
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
);
/** A grey PNG of `width`×`height` (8-bit greyscale, no filter). */
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
const NOTE = 'Pay the supplier on Friday.\nAsk for the March invoice.\n';

interface Listing {
  folders: { path: string }[];
  files: { path: string; name: string }[];
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

test.describe.configure({ mode: 'serial' });

/** The capture of a flow, once the screen settled. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  // The pointer rests where the last click was: an iOS outline button under it is drawn at 60 % (hover).
  await page.mouse.move(0, 0);
  await expect(shown(page).locator('[data-testid="files-loading"]:visible')).toHaveCount(0);
  await untilStill(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-8-${key}-${width}`) });
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const item = (page: Page, path: string) => shown(page).locator(`[data-item="${path}"]`);
const dialog = (page: Page, id: string) => page.locator(`ion-modal[data-testid="${id}"]`);
const toast = (page: Page, text: string | RegExp) => page.locator('ion-toast').filter({ hasText: text }).last();

/** The messages of the notices painted on screen now: an open toast whose box inside its shadow root has a height. */
function paintedNotices(page: Page): Promise<string[]> {
  return page.locator('ion-toast').evaluateAll((toasts) =>
    toasts
      .filter((t) => !t.classList.contains('overlay-hidden'))
      .filter((t) => (t.shadowRoot?.querySelector('.toast-wrapper')?.getBoundingClientRect().height ?? 0) > 0)
      .map((t) => t.shadowRoot?.querySelector('.toast-message')?.textContent?.trim() ?? ''),
  );
}

/** Opens the actions of `path` and picks `action` (`open`, `download`, `rename`, `move`, `delete`). */
async function act(page: Page, path: string, action: string): Promise<void> {
  await item(page, path).locator('[data-testid="files-item-actions"]').click();
  const choice = page.locator(`ion-popover [data-testid="files-action-${action}"]`);
  await expect(choice).toBeVisible();
  await choice.click();
  await expect(page.locator('ion-popover[data-testid="files-actions-menu"]')).toBeHidden();
}

/** WCAG contrast of `locator`'s text against its own background (both opaque). */
async function contrast(locator: Locator): Promise<number> {
  return locator.evaluate((el) => {
    // `color-mix()` computes to `color(srgb r g b)` in 0…1; the rest to `rgb(r, g, b)` in 0…255.
    const channels = (css: string) => {
      const values = (css.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
      return css.startsWith('color(') ? values : values.map((v) => v / 255);
    };
    const luminance = (css: string) => {
      const [r, g, b] = channels(css).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const style = getComputedStyle(el);
    const [fg, bg] = [luminance(style.color), luminance(style.backgroundColor)];
    return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
  });
}

async function upload(page: Page, files: { name: string; mimeType: string; buffer: Buffer }[]): Promise<void> {
  await testid(page, 'files-upload-input').setInputFiles(files);
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);
  const narrow = width < 768;

  test(`BASE-G82 BASE-G83 — see, make a folder and upload at ${width}`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    try {
      await wipe(context, A);
      // BASE-G82 — «Files» is in the side menu (behind the menu button on a narrow screen: the address then).
      if (width >= 1440) {
        await page.locator('[data-testid="nav-files"]').first().click();
        await expect(page).toHaveURL(`${A}/files`);
      } else {
        await page.goto(`${A}/files`);
      }
      await expect(testid(page, 'files-empty')).toContainText('No files');
      await expect(testid(page, 'files-empty')).toContainText('Upload a file or drag it here.');
      await expect(testid(page, 'files-space')).toHaveText(/^Space: 0 B used · No limit$/);
      // The tree is content of the page: on the left from a tablet up, a «Folders» selector on a phone.
      await expect(testid(page, 'files-tree')).toBeVisible({ visible: !narrow });
      await expect(testid(page, 'files-folder-select')).toBeVisible({ visible: narrow });
      await snap(page, 'BASE-G82-empty', width);

      // BASE-G83 — a folder, asked by its name.
      await testid(page, 'files-new-folder').click();
      const folderDialog = dialog(page, 'files-new-folder-dialog');
      await expect(folderDialog).toBeVisible();
      await folderDialog.locator('[data-testid="files-new-folder-name"] input').fill('Invoices');
      await folderDialog.locator('[data-testid="files-new-folder-dialog-submit"]').click();
      await expect(toast(page, 'Folder created.')).toBeVisible();
      await expect(item(page, 'Invoices')).toHaveAttribute('data-kind', 'folder');

      // BASE-G83 — two files uploaded at the top; a third with a taken name keeps «name (1).ext».
      await upload(page, [
        { name: 'logo.png', mimeType: 'image/png', buffer: PNG },
        { name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from(NOTE) },
      ]);
      await expect(toast(page, 'Files uploaded.')).toBeVisible();
      await expect(item(page, 'logo.png')).toBeVisible();
      await expect(item(page, 'notes.txt')).toBeVisible();
      await upload(page, [{ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('again') }]);
      await expect(toast(page, 'Uploaded as “notes (1).txt”: there was already one with that name.')).toBeVisible();
      await expect(item(page, 'notes (1).txt')).toBeVisible();

      // BASE-G83 — a program is refused, and the notice says why (hub#1776), never a code.
      await upload(page, [{ name: 'setup.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ') }]);
      await expect(
        toast(page, 'Could not upload “setup.exe”: Programs (.exe) can\'t be kept in Files: they could harm whoever opens them.'),
      ).toBeVisible();
      await expect(item(page, 'setup.exe')).toHaveCount(0);

      // BASE-G82 — a long name wraps inside its card, and every card of the row keeps its icon at the top.
      const long = 'supplier price list for the second quarter of the year.csv';
      await upload(page, [{ name: long, mimeType: 'text/csv', buffer: Buffer.from('item;price\nflour;12\n') }]);
      await expect(item(page, long)).toBeVisible();
      const icons = await shown(page)
        .locator('[data-item]')
        .evaluateAll((cards) =>
          cards.map((card) => ({
            row: Math.round(card.getBoundingClientRect().top),
            icon: Math.round(card.querySelector('.files-item-icon')!.getBoundingClientRect().top),
          })),
        );
      for (const { row, icon } of icons) {
        expect(icon, `the icon of a card at ${row}`).toBe(icons.find((other) => other.row === row)!.icon);
      }

      // BASE-G82 — folders first, then the files; «Space» counts what is kept.
      await expect(shown(page).locator('[data-item]')).toHaveCount(5);
      await expect(shown(page).locator('[data-item]').first()).toHaveAttribute('data-kind', 'folder');
      await expect(testid(page, 'files-space')).toHaveText(/^Space: \d+ B used · No limit$/);
      // The open folder stands out in the tree and stays readable.
      if (!narrow) expect(await contrast(testid(page, 'files-root'))).toBeGreaterThanOrEqual(4.5);
      await snap(page, 'BASE-G82', width);

      // BASE-G82 — the list shows each file's size and when it changed.
      await testid(page, 'files-view-list').click();
      await expect(testid(page, 'files-items')).toHaveClass(/files-list/);
      await expect(item(page, 'notes.txt')).toContainText(`${NOTE.length} B ·`);
      // Each name on one line, cut in what it says and never in its extension (Drive, Dropbox, iOS Files); the size
      // and the date under it on a phone, beside it from a tablet up.
      const rows = await shown(page)
        .locator('[data-item]')
        .evaluateAll((items) =>
          items.map((row) => {
            const name = row.querySelector<HTMLElement>('.files-item-name')!;
            const meta = row.querySelector<HTMLElement>('.files-item-meta')!.getBoundingClientRect();
            const extension = row.querySelector<HTMLElement>('.files-item-ext');
            const box = name.getBoundingClientRect();
            return {
              item: row.getAttribute('data-item'),
              oneLine: box.height < parseFloat(getComputedStyle(name).fontSize) * 2,
              extensionWhole:
                !extension ||
                (extension.scrollWidth <= extension.clientWidth + 1 &&
                  extension.getBoundingClientRect().right <= row.getBoundingClientRect().right),
              metaBelow: meta.top >= box.bottom - 1,
            };
          }),
        );
      for (const row of rows) {
        expect(row.oneLine, `${row.item} at ${width}: its name on one line`).toBe(true);
        expect(row.extensionWhole, `${row.item} at ${width}: its extension whole`).toBe(true);
        expect(row.metaBelow, `${row.item} at ${width}: size and date ${width <= 600 ? 'under' : 'beside'} the name`).toBe(
          width <= 600,
        );
      }
      await snap(page, 'BASE-G82-list', width);
      await testid(page, 'files-view-grid').click();

      // BASE-G82 — into the folder: its path, and back to the top from the path.
      if (narrow) {
        await testid(page, 'files-folder-select').locator('ion-select').click();
        await page.locator('ion-popover ion-select-option, ion-popover ion-radio').filter({ hasText: 'Invoices' }).first().click();
      } else {
        await testid(page, 'files-tree').getByRole('button', { name: 'Invoices' }).click();
      }
      await expect(page).toHaveURL(`${A}/files?folder=Invoices`);
      await expect(shown(page).locator('.files-crumbs [data-crumb="Invoices"]')).toHaveAttribute('aria-current', 'true');
      await expect(testid(page, 'files-empty')).toBeVisible();
      if (!narrow) {
        const open = testid(page, 'files-tree').locator('[aria-current="true"]');
        await expect(open).toHaveText('Invoices');
        expect(await contrast(open)).toBeGreaterThanOrEqual(4.5);
      }
      await upload(page, [{ name: 'march.txt', mimeType: 'text/plain', buffer: Buffer.from('March') }]);
      await expect(item(page, 'Invoices/march.txt')).toBeVisible();
      await snap(page, 'BASE-G83', width);

      // BASE-G82 — the search looks in the open folder.
      await shown(page).locator('.files-crumbs [data-crumb=""]').click();
      await expect(page).toHaveURL(`${A}/files`);
      await testid(page, 'files-search').locator('input').fill('note');
      await expect(shown(page).locator('[data-item]')).toHaveCount(2);
      await testid(page, 'files-search').locator('input').fill('nothing like it');
      await expect(testid(page, 'files-no-match')).toHaveText('No file in this folder matches “nothing like it”.');

      // BASE-G83 — two notices in a row never cover each other: the second closes the first, and it reads whole.
      const refused = toast(page, 'Could not upload “setup.exe”');
      await upload(page, [{ name: 'setup.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ') }]);
      await expect(refused).toBeVisible();
      await upload(page, [{ name: 'later.txt', mimeType: 'text/plain', buffer: Buffer.from('later') }]);
      const kept = toast(page, 'Files uploaded.');
      await expect(kept).toBeVisible();
      // What is painted, read inside each toast's shadow root (the host spans the screen either way): one notice, the
      // last; the one before is closed, never left underneath.
      await expect.poll(() => paintedNotices(page)).toEqual(['Files uploaded.']);
      await expect(kept).toBeInViewport({ ratio: 1 });
      await page.mouse.move(0, 0);
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-8-BASE-G83-notices-${width}`) });

      // BASE-G83 — a batch with a file kept and one refused: one notice, its sentences one after the other on one line
      // (a notice paints a line break as a bare space), what was kept first and the refusal with its reason.
      await upload(page, [
        { name: 'kept.txt', mimeType: 'text/plain', buffer: Buffer.from('kept') },
        { name: 'virus.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ') },
      ]);
      const both = "Files uploaded. Could not upload “virus.exe”: Programs (.exe) can't be kept in Files: they could harm whoever opens them.";
      await expect.poll(() => paintedNotices(page)).toEqual([both]);
      await expect(toast(page, both)).toBeInViewport({ ratio: 1 });
      await page.mouse.move(0, 0);
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-8-BASE-G83-batch-notice-${width}`) });
    } finally {
      await wipe(context, A).catch(() => undefined);
      await context.close();
    }
  });

  test(`BASE-G84 — open and download at ${width}`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/files' });
    try {
      await wipe(context, A);
      await upload(page, [
        { name: 'logo.png', mimeType: 'image/png', buffer: PNG },
        { name: 'tall.png', mimeType: 'image/png', buffer: png(300, 3000) },
        { name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from(NOTE) },
      ]);
      await expect(item(page, 'notes.txt')).toBeVisible();

      // An image, shown by the hub's own address, never larger than itself; closed, back to the folder.
      await item(page, 'logo.png').locator('[data-testid="files-item-main"]').click();
      const preview = page.locator('[data-testid="file-preview"]').last();
      await expect(preview.locator('[data-testid="file-preview-title"]')).toHaveText('logo.png');
      await expect(preview.locator('[data-testid="file-preview-image"]')).toHaveAttribute('src', /^\/api\/files\/raw\?/);
      await expect
        .poll(() => preview.locator('[data-testid="file-preview-image"]').evaluate((img: HTMLImageElement) => img.naturalWidth))
        .toBe(1);
      const image = preview.locator('[data-testid="file-preview-image"]');
      await expect(image).toBeVisible();
      await expect.poll(() => image.evaluate((img) => img.getBoundingClientRect().width)).toBe(1);
      await preview.locator('[data-testid="file-preview-close"]').click();
      await expect(preview).toBeHidden();

      // A tall one fits whole in the viewer, as Drive's does; «Zoom in» makes it larger than that.
      await item(page, 'tall.png').locator('[data-testid="files-item-main"]').click();
      await expect(preview.locator('[data-testid="file-preview-title"]')).toHaveText('tall.png');
      await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalHeight)).toBe(3000);
      await expect(image).toBeVisible();
      const body = preview.locator('.file-preview-body');
      // Until the viewer is presented whole, a box may not be there yet: asked again, never taken as a fit.
      await expect
        .poll(async () => {
          const [picture, viewer] = [await image.boundingBox(), await body.boundingBox()];
          return Boolean(picture && viewer && picture.height > 0 && picture.height <= viewer.height);
        })
        .toBe(true);
      expect(await body.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeLessThanOrEqual(0);
      const fitted = (await image.boundingBox())!.width;
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-8-BASE-G84-image-${width}`) });
      await preview.locator('[data-testid="file-preview-zoom-in"]').click();
      await expect.poll(async () => (await image.boundingBox())?.width ?? 0).toBeCloseTo(fitted * 1.25, 0);
      await preview.locator('[data-testid="file-preview-close"]').click();
      await expect(preview).toBeHidden();

      // A text, read in the preview.
      await act(page, 'notes.txt', 'open');
      await expect(preview.locator('[data-testid="file-preview-text"]')).toContainText('Pay the supplier on Friday.');
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-8-BASE-G84-${width}`) });

      // Downloaded with its name, from the preview.
      const [download] = await Promise.all([
        page.waitForEvent('download'),
        preview.locator('[data-testid="file-preview-download"]').click(),
      ]);
      expect(download.suggestedFilename()).toBe('notes.txt');
      await preview.locator('[data-testid="file-preview-close"]').click();

      // Private: never kept by a cache, an attachment unless shown, sandboxed.
      const raw = await context.request.get(`${A}/api/files/raw?path=notes.txt`);
      expect(raw.status()).toBe(200);
      expect(raw.headers()['cache-control']).toBe('private, no-store');
      expect(raw.headers()['content-disposition']).toBe("attachment; filename*=UTF-8''notes.txt");
      expect(raw.headers()['content-security-policy']).toContain('sandbox');
      expect(await raw.text()).toBe(NOTE);
    } finally {
      await wipe(context, A).catch(() => undefined);
      await context.close();
    }
  });

  test(`BASE-G85 BASE-G86 — rename, move and delete at ${width}`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/files' });
    try {
      await wipe(context, A);
      for (const name of ['Invoices', 'Contracts']) {
        expect((await api(context, A, 'POST', '/files/folder', { parent: '', name })).status).toBe(200);
      }
      await upload(page, [{ name: 'march.txt', mimeType: 'text/plain', buffer: Buffer.from('March') }]);
      await expect(item(page, 'march.txt')).toBeVisible();

      // BASE-G85 — renamed by its new name.
      await act(page, 'march.txt', 'rename');
      const renameDialog = dialog(page, 'files-rename-dialog');
      await expect(renameDialog.locator('[data-testid="files-rename-name"] input')).toHaveValue('march.txt');
      await renameDialog.locator('[data-testid="files-rename-name"] input').fill('april.txt');
      await renameDialog.locator('[data-testid="files-rename-dialog-submit"]').click();
      await expect(toast(page, 'Renamed.')).toBeVisible();
      await expect(item(page, 'april.txt')).toBeVisible();
      await expect(item(page, 'march.txt')).toHaveCount(0);

      // BASE-G85 — a taken name is refused with its sentence, and the dialog stays.
      await act(page, 'april.txt', 'rename');
      await renameDialog.locator('[data-testid="files-rename-name"] input').fill('Invoices');
      await renameDialog.locator('[data-testid="files-rename-dialog-submit"]').click();
      await expect(renameDialog.locator('[data-testid="files-rename-dialog-error"]')).toContainText(
        'There is already a file or folder with that name here.',
      );
      await renameDialog.locator('[data-testid="files-rename-dialog-cancel"]').click();

      // BASE-G85 — moved into a folder; the notice names it (hub#2197).
      await act(page, 'april.txt', 'move');
      const moveDialog = dialog(page, 'files-move-dialog');
      await expect(moveDialog).toContainText('Move “april.txt”');
      await moveDialog.locator('[data-testid="files-move-option"][data-to="Invoices"]').click();
      await expect(moveDialog.locator('[data-testid="files-move-option"][data-to="Invoices"]')).toHaveAttribute('aria-selected', 'true');
      expect(await contrast(moveDialog.locator('[data-testid="files-move-option"][data-to="Invoices"]'))).toBeGreaterThanOrEqual(4.5);
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-8-BASE-G85-move-${width}`) });
      await moveDialog.locator('[data-testid="files-move-dialog-submit"]').click();
      await expect(toast(page, 'Moved to “Invoices”.')).toBeVisible();
      await expect(item(page, 'april.txt')).toHaveCount(0);

      // BASE-G85 — a folder, with what it holds, into another: the open folder follows it.
      await page.goto(`${A}/files?folder=Invoices`);
      await expect(item(page, 'Invoices/april.txt')).toBeVisible();
      await testid(page, 'files-folder-actions').click();
      await page.locator('ion-popover [data-testid="files-action-move"]').click();
      await moveDialog.locator('[data-testid="files-move-option"][data-to="Contracts"]').click();
      // Never inside itself: the folder is no destination of its own.
      await expect(moveDialog.locator('[data-testid="files-move-option"][data-to="Invoices"]')).toHaveCount(0);
      await moveDialog.locator('[data-testid="files-move-dialog-submit"]').click();
      await expect(toast(page, 'Moved to “Contracts”.')).toBeVisible();
      await expect(page).toHaveURL(`${A}/files?folder=Contracts/Invoices`);
      await expect(item(page, 'Contracts/Invoices/april.txt')).toBeVisible();
      await snap(page, 'BASE-G85', width);

      // BASE-G86 — a file, after asking.
      await act(page, 'Contracts/Invoices/april.txt', 'delete');
      const ask = page.locator('.ep-confirm-dialog').last();
      await expect(ask).toContainText('You are about to delete “april.txt”. This cannot be undone.');
      await expect(ask.getByRole('button', { name: 'Delete' })).toBeInViewport({ ratio: 1 });
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-8-BASE-G86-${width}`) });
      await ask.getByRole('button', { name: 'Delete' }).click();
      await expect(toast(page, 'File deleted.')).toBeVisible();
      await expect(testid(page, 'files-empty')).toBeVisible();

      // BASE-G86 — a folder and everything in it; the screen goes back to where it was.
      await testid(page, 'files-folder-actions').click();
      await page.locator('ion-popover [data-testid="files-action-delete"]').click();
      await expect(ask).toContainText('You are about to delete “Invoices” and everything in it. This cannot be undone.');
      await ask.getByRole('button', { name: 'Delete' }).click();
      await expect(toast(page, 'Folder deleted.')).toBeVisible();
      await expect(page).toHaveURL(`${A}/files?folder=Contracts`);
      await expect(testid(page, 'files-empty')).toBeVisible();
      await snap(page, 'BASE-G86-done', width);
    } finally {
      await wipe(context, A).catch(() => undefined);
      await context.close();
    }
  });

  test(`BASE-G82 BASE-G83 — the plan's space at ${width}`, async ({ browser }) => {
    // The photo of hub `a` with a plan of 1 MB of space, as erplora.com sends it (`plan.max_storage_bytes`).
    const before = psql("select state::text from base_hub where slug = 'a'");
    psql(`update base_hub set state = state || '{\\"plan\\": {\\"max_storage_bytes\\": ${1024 * 1024}}}' where slug = 'a'`);
    const { context, page } = await hostPage(browser, A, { viewport, next: '/files' });
    try {
      await wipe(context, A);
      await page.reload();
      const meter = testid(page, 'files-space');
      await expect(meter.locator('.usage-meter__label')).toHaveText('Space: 0 B of 1 MB');
      await upload(page, [{ name: 'scan.dat', mimeType: 'application/octet-stream', buffer: Buffer.alloc(600 * 1024, 7) }]);
      await expect(item(page, 'scan.dat')).toBeVisible();
      await expect(meter.locator('.usage-meter__label')).toHaveText('Space: 600 KB of 1 MB');
      // The bar at the exact share, never figures rounded to GB.
      await expect(meter.locator('[role="progressbar"]')).toHaveAttribute('aria-valuenow', '59');
      await expect(meter).not.toContainText('GB');
      await snap(page, 'BASE-G82-space', width);

      // Past the plan's space, refused with its sentence; nothing is kept.
      await upload(page, [{ name: 'second.dat', mimeType: 'application/octet-stream', buffer: Buffer.alloc(600 * 1024, 7) }]);
      await expect(
        toast(page, 'Could not upload “second.dat”: There is no space left for that file: your plan includes 1 MB.'),
      ).toBeVisible();
      await expect(item(page, 'second.dat')).toHaveCount(0);
      await snap(page, 'BASE-G83-no-space', width);
    } finally {
      psql(`update base_hub set state = '${before.replaceAll('"', '\\"')}' where slug = 'a'`);
      await wipe(context, A).catch(() => undefined);
      await context.close();
    }
  });
}

test('BASE-G82 BASE-G84 — the employee opens and downloads, and changes nothing', async ({ browser }) => {
  const owner = await hostPage(browser, A, { viewport: VIEWPORTS[834], next: '/files' });
  const employee = await hostPage(browser, A, { viewport: VIEWPORTS[834], next: '/', credentials: EMPLOYEE });
  try {
    await wipe(owner.context, A);
    // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
    if (process.env.E2E_SAVE_STORAGE_STATE) await owner.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    await upload(owner.page, [{ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from(NOTE) }]);
    await expect(item(owner.page, 'notes.txt')).toBeVisible();

    const page = employee.page;
    await page.goto(`${A}/files`);
    await expect(item(page, 'notes.txt')).toBeVisible();
    await expect(testid(page, 'files-upload')).toHaveCount(0);
    await expect(testid(page, 'files-new-folder')).toHaveCount(0);
    await item(page, 'notes.txt').locator('[data-testid="files-item-actions"]').click();
    await expect(page.locator('ion-popover [data-testid="files-action-download"]')).toBeVisible();
    await expect(page.locator('ion-popover [data-testid="files-action-rename"]')).toHaveCount(0);
    await expect(page.locator('ion-popover [data-testid="files-action-delete"]')).toHaveCount(0);
    await snap(page, 'BASE-G82-employee', 834);
    // Nor by the API: only who runs the business changes the files.
    const refused = await api<{ code?: string }>(employee.context, A, 'POST', '/files/delete', { path: 'notes.txt' });
    expect(refused.status).toBe(403);
    expect((await api<Listing>(owner.context, A, 'GET', '/files')).data.files.map((f) => f.name)).toEqual(['notes.txt']);
  } finally {
    await wipe(owner.context, A).catch(() => undefined);
    await owner.context.close();
    await employee.context.close();
  }
});

test('BASE-G82 BASE-G84 BASE-G85 BASE-G86 — hub b never sees, reads, moves nor deletes a’s files', async ({ browser }) => {
  const a = await hostPage(browser, A, { viewport: VIEWPORTS[1440], next: '/files' });
  const b = await hostPage(browser, B, { viewport: VIEWPORTS[1440], next: '/files' });
  try {
    await wipe(a.context, A);
    await wipe(b.context, B);
    await upload(a.page, [{ name: 'secret.txt', mimeType: 'text/plain', buffer: Buffer.from('only a') }]);
    await expect(item(a.page, 'secret.txt')).toBeVisible();

    // From b's host, nothing of a's: not listed, not read, not renamed, moved nor deleted.
    await b.page.reload();
    await expect(testid(b.page, 'files-empty')).toBeVisible();
    expect((await api<Listing>(b.context, B, 'GET', '/files')).data.files).toEqual([]);
    expect((await b.context.request.get(`${B}/api/files/raw?path=secret.txt`)).status()).toBe(404);
    for (const [path, body] of [
      ['/files/rename', { path: 'secret.txt', name: 'mine.txt' }],
      ['/files/move', { path: 'secret.txt', to: '' }],
      ['/files/delete', { path: 'secret.txt' }],
    ] as const) {
      expect((await api(b.context, B, 'POST', path, body)).status, `${path} at b`).toBe(404);
    }
    // A path that climbs out of the business's files is refused, never followed.
    for (const path of ['../secret.txt', '/secret.txt', '..\\secret.txt']) {
      const climbed = await b.context.request.get(`${B}/api/files/raw?path=${encodeURIComponent(path)}`);
      expect([400, 404, 422], `${path} at b`).toContain(climbed.status());
    }
    // Still a's, whole.
    const kept = await a.context.request.get(`${A}/api/files/raw?path=secret.txt`);
    expect(await kept.text()).toBe('only a');
  } finally {
    await wipe(a.context, A).catch(() => undefined);
    await wipe(b.context, B).catch(() => undefined);
    await a.context.close();
    await b.context.close();
  }
});
