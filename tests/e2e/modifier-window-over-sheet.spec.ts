// flow: MODIFIER-F04 — hub#928
// The windows a group's sheet opens over itself («New option», «Edit option», the confirmation of «Delete»), in Chrome on
// hub `a` at 1440×900 and 820×1180: what is left of the sheet around them is dimmed, as every window dims what it opens
// over. They are narrower than the sheet (a 480px or 420px card on Ionic's 600px window), and Ionic drops the backdrop of
// a modal opened over another one: the sheet showed around them, as bright as before and its words cut at their edges,
// as if it were part of them. Measured on the screen itself: the mean brightness of each strip of the sheet the window
// leaves in sight, with the window open against the same strip just before. Its data are named `E2E Mod Over …` and
// `afterAll` deletes exactly them.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown, untilStill } from './helpers';

const STAMP = Date.now().toString(36).toUpperCase();
const GROUP = `E2E Mod Over ${STAMP}`;

/** At most this much of the brightness left once the window opens: Ionic's backdrop is black at 0.4 (0.6 left). */
const DIMMED = 0.8;

const SIZES = [
  { label: '1440', width: 1440, height: 900 },
  { label: '820', width: 820, height: 1180 },
];

function cleanUp(): void {
  psql(
    [
      "delete from modifier_modifieroption where group_id in (select id from modifier_modifiergroup where name like 'E2E Mod Over %')",
      "delete from modifier_modifiergroup where name like 'E2E Mod Over %'",
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

type Box = { left: number; top: number; right: number; bottom: number };

/** The box of the window `modal` paints (its content, in its shadow root), not the full-screen host. */
async function windowBox(modal: Locator): Promise<Box> {
  return modal.evaluate((el) => {
    const r = el.shadowRoot!.querySelector('.modal-wrapper')!.getBoundingClientRect();
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
  });
}

/** The parts of `back` that `front` leaves in sight, 2px in from every edge (antialiasing), at least 8px each way. */
function strips(back: Box, front: Box): Box[] {
  const rows = { top: Math.max(back.top, front.top), bottom: Math.min(back.bottom, front.bottom) };
  const columns = { left: Math.max(back.left, front.left), right: Math.min(back.right, front.right) };
  return [
    { left: back.left, right: front.left, ...rows },
    { left: front.right, right: back.right, ...rows },
    { top: back.top, bottom: front.top, ...columns },
    { top: front.bottom, bottom: back.bottom, ...columns },
  ]
    .map((s) => ({ left: s.left + 2, top: s.top + 2, right: s.right - 2, bottom: s.bottom - 2 }))
    .filter((s) => s.right - s.left >= 8 && s.bottom - s.top >= 8);
}

/** The mean brightness (0–255) of each of `boxes` in `png`, a screenshot of `page`, decoded in its browser. */
async function brightness(page: Page, png: Buffer, boxes: Box[]): Promise<number[]> {
  return page.evaluate(
    async ({ base64, boxes: areas }) => {
      const blob = new Blob([Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))], { type: 'image/png' });
      const image = await createImageBitmap(blob);
      const canvas = new OffscreenCanvas(image.width, image.height).getContext('2d')!;
      canvas.drawImage(image, 0, 0);
      const scale = image.width / window.innerWidth;
      return areas.map((a) => {
        const x = Math.round(a.left * scale);
        const y = Math.round(a.top * scale);
        const { data } = canvas.getImageData(x, y, Math.round(a.right * scale) - x, Math.round(a.bottom * scale) - y);
        let sum = 0;
        for (let i = 0; i < data.length; i += 4) sum += 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
        return sum / (data.length / 4);
      });
    },
    { base64: png.toString('base64'), boxes },
  );
}

/** Opens `front` with `open` over the sheet and says how bright each strip of the sheet around it is, against before. */
async function aroundOf(page: Page, sheet: Locator, front: Locator, open: () => Promise<void>, shotName: string) {
  const before = await capture(page, `${shotName}-before`);
  await open();
  await expect(front).toBeVisible();
  await untilStill(page);
  const back = await windowBox(sheet);
  const box = await windowBox(front);
  expect(box.right - box.left, 'the window is painted').toBeGreaterThan(0);
  expect(back.right - back.left, 'the sheet is painted').toBeGreaterThan(0);
  const around = strips(back, box);
  const after = await capture(page, shotName);
  const [was, is] = [await brightness(page, before, around), await brightness(page, after, around)];
  return around.map((strip, i) => ({ strip, was: Math.round(was[i]), is: Math.round(is[i]) }));
}

for (const size of SIZES) {
  test(`MODIFIER-F04 at ${size.label}: the sheet around «New option», «Edit option» and «Delete» is dimmed (hub#928)`, async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await login(page, A, '/modifier/groups');
    const name = `${GROUP} ${size.label}`;
    const group = await api<{ id: string }>(context, A, 'POST', '/modifier/groups', { name, max_choices: 2 });
    expect(group.status).toBe(201);
    expect((await api(context, A, 'POST', '/modifier/options', { group_id: group.data.id, name: 'Mayo' })).status).toBe(201);
    await page.reload();
    await shown(page).locator('[data-testid=modifier-groups-row], [data-testid=modifier-groups-empty]').first().waitFor({ state: 'visible' });
    await shown(page).locator('[data-testid=modifier-groups-search] input').fill(name);
    await shown(page).locator(`[data-testid=modifier-groups-row][data-id="${group.data.id}"] [role=cell]`).first().click();
    const sheet = page.locator('ion-modal[data-testid=modifier-sheet]');
    await expect(sheet.locator('[data-testid^=modifier-sheet-options-row-]')).toHaveCount(1);

    const optionForm = page.locator('ion-modal[data-testid=modifier-option-form]');
    const confirm = page.locator('ion-modal[data-testid=modifier-sheet-option-delete]');
    const windows: [string, Locator, () => Promise<void>, () => Promise<void>][] = [
      [
        'New option',
        optionForm,
        () => sheet.locator('[data-testid=modifier-sheet-options-add]').click(),
        () => optionForm.locator('[data-testid=modifier-option-form-cancel]').click(),
      ],
      [
        'Edit option',
        optionForm,
        () => sheet.locator('[data-testid^=modifier-sheet-options-edit-]').click(),
        () => optionForm.locator('[data-testid=modifier-option-form-cancel]').click(),
      ],
      [
        'Delete option',
        confirm,
        () => sheet.locator('[data-testid^=modifier-sheet-options-delete-]').click(),
        () => confirm.locator('[data-testid=modifier-sheet-option-delete-cancel]').click(),
      ],
    ];
    for (const [title, front, open, close] of windows) {
      const around = await aroundOf(page, sheet, front, open, `MODIFIER-F04-over-sheet-${title.replace(' ', '-')}-${size.label}`);
      expect(around.length, `${title}: the sheet shows around it at ${size.label}`).toBeGreaterThan(0);
      for (const { strip, was, is } of around) {
        expect(is, `${title}: the sheet at ${JSON.stringify(strip)} went from ${was} to ${is}`).toBeLessThanOrEqual(was * DIMMED);
      }
      await close();
      await expect(front).toBeHidden();
    }
  });
}
