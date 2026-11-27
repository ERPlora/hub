// The five windows that group their controls without a box paint the group with FieldGroup (hub#1487): a new
// appointment's customer, a schedule's week, a device's printers, an API key's access and a package's lines. At 390,
// 834 and 1440 each group is a fieldset with no border, margin or padding that may shrink with its window, laid out as
// its window says, and nothing scrolls sideways.
import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, horizontalOverflow, login, psql, shown, THREE_SIZES, turnOffTurnedOn, turnOnMissing, untilStill } from './helpers';
import { dialog, presentedDialog } from './inventory-helpers';
import { asTheApp } from './printing-helpers';
import { pickMember, staffCleanUp } from './staff-helpers';

const TAG = 'E2E Group';
const PRINTER = `${TAG} printer`;
const MEMBER = { first_name: `${TAG} Iris`, last_name: 'Grouped' };

/** The apps the five windows live in, each after the ones it requires. */
const APPS = ['tax', 'customer', 'staff', 'service', 'schedule', 'appointment', 'printing'];

interface GroupedWindow {
  key: string;
  path: string;
  dialog: string;
  group: string;
  /** How the window's own class lays the group out. */
  layout: { display: string; rowGap: string };
  open: (page: Page) => Promise<void>;
  /** Opened inside the installed app: the device window is offered nowhere else. */
  inTheApp?: boolean;
}

/** Taps the shown one of `testids` (a screen with two views has a button in each). */
const tap =
  (...testids: string[]) =>
  (page: Page) =>
    shown(page)
      .locator(testids.map((testid) => `[data-testid=${testid}]`).join(', '))
      .filter({ visible: true })
      .first()
      .click();

const WINDOWS: readonly GroupedWindow[] = [
  {
    key: 'appointment-customer',
    path: '/appointment/agenda',
    dialog: 'appointment-form',
    group: '[data-testid=appointment-form-customer]',
    layout: { display: 'block', rowGap: 'normal' },
    open: tap('appointment-list-add', 'appointment-agenda-add'),
  },
  {
    key: 'schedule-week',
    path: '/staff/schedules',
    dialog: 'staff-schedule-form',
    group: '.staff-week',
    layout: { display: 'grid', rowGap: '10px' },
    open: async (page) => {
      await pickMember(page, 'staff-schedules-member', MEMBER.last_name, `${MEMBER.first_name} ${MEMBER.last_name}`);
      await tap('staff-schedules-add')(page);
    },
  },
  {
    key: 'device-printers',
    path: '/printing/devices',
    dialog: 'printing-device',
    group: '.printing-device__printers',
    layout: { display: 'grid', rowGap: '10px' },
    open: tap('printing-devices-add'),
    inTheApp: true,
  },
  {
    key: 'api-key-scopes',
    path: '/employees#apikeys',
    dialog: 'api-key-form',
    group: '.api-key-scopes',
    layout: { display: 'flex', rowGap: '8px' },
    open: tap('api-keys-new'),
  },
  {
    key: 'package-lines',
    path: '/service/packages',
    dialog: 'service-package-form',
    group: '.service-package-form__lines',
    layout: { display: 'grid', rowGap: '14px' },
    open: tap('service-packages-add'),
  },
];

const turnedOn: string[] = [];

function cleanUp(): void {
  staffCleanUp(TAG);
  psql(`delete from printing_printer where name like '${TAG}%'`);
}

async function ownerOn(browser: Browser, path: string, inTheApp = false) {
  const context = await browser.newContext({ baseURL: A, locale: 'en-US' });
  if (inTheApp) await asTheApp(context);
  const page = await context.newPage();
  await login(page, A, path);
  return { context, page };
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerOn(browser, '/');
  await turnOnMissing(context, A, APPS, turnedOn);
  const member = await api(context, A, 'POST', '/staff/members', MEMBER);
  expect(member.status, JSON.stringify(member.data)).toBe(201);
  const printer = await api(context, A, 'POST', '/printing/printers', { name: PRINTER, kind: 'network', address: '10.0.0.87', usage: 'receipt' });
  expect(printer.status, JSON.stringify(printer.data)).toBe(201);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerOn(browser, '/');
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

/** The group's element, its box (border, margin and padding on every side, as a set) and its layout. */
function paintedAs(group: Locator) {
  return group.evaluate((element) => {
    const style = getComputedStyle(element);
    const box = ['top', 'right', 'bottom', 'left'].flatMap((side) => [
      style.getPropertyValue(`border-${side}-width`),
      style.getPropertyValue(`margin-${side}`),
      style.getPropertyValue(`padding-${side}`),
    ]);
    return { tag: element.tagName, box: [...new Set(box)], minWidth: style.minWidth, display: style.display, rowGap: style.rowGap };
  });
}

for (const window of WINDOWS) {
  test(`${window.key}: a group without a box, laid out as its window says, at 390, 834 and 1440`, async ({ browser }) => {
    const { context, page } = await ownerOn(browser, window.path, window.inTheApp);
    for (const size of THREE_SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await untilStill(page);
      const opened = await presentedDialog(page, window.dialog, () => window.open(page));
      const group = opened.locator(window.group);
      await group.scrollIntoViewIfNeeded();
      expect.soft(await paintedAs(group), `${window.key} at ${size.label}`).toEqual({ tag: 'FIELDSET', box: ['0px'], minWidth: '0px', ...window.layout });
      expect.soft(await horizontalOverflow(page), `${window.key} at ${size.label}: no sideways scroll`).toBeLessThanOrEqual(0);
      await page.mouse.move(0, 0);
      await capture(page, `HUB-1487-${window.key}-${size.label}`);
      await opened.locator(`[data-testid=${window.dialog}-cancel]`).click();
      await expect(dialog(page, window.dialog)).toBeHidden();
    }
    await context.close();
  });
}
