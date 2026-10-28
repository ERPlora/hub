// flow: hub-e2e-capture — FIX of the e2e harness (FIX-HUB-E2E-SHOT-BEFORE-RESIZE-UNCHECKED): `settled()` ignored Ionic
// The harness's `settled()` (helpers.ts; service-helpers.ts and schedule-helpers.ts hand out the same one), the wait the
// captures and measurements of the specs take: once it returns, nothing on the screen moves any more. Ionic animates
// its overlays (`ion-toast`, `ion-modal`, `ion-popover`) with Web Animations on elements of their shadow roots, which
// `document.getAnimations()` leaves out: right after the old `settled()`, a toast still entering counted 0 animations in
// the document and 1 in its own shadow root. The checks here read the page on their own, never through `settled()`'s
// code. The same fix as erplora.com's e2e (FIX-SAAS-E2E-SETTLED-IGNORES-IONIC-ANIMATIONS).
import { expect, type Page, test } from '@playwright/test';

import { A, api, capture, createItem, login, repeatedTop, settled as baseSettled, shown, uniqueName } from './helpers';
import { signedIn, snap } from './cart-checkout-helpers';
import { settled as scheduleSettled } from './schedule-helpers';
import { settled } from './service-helpers';

const TASK = 'FIX-HUB-E2E-SETTLED-IONIC-ANIMATIONS';

const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** The finite animations running in the document and in every open shadow root under it, however deep. */
const stillMoving = (page: Page) =>
  page.evaluate(() => {
    const roots: Array<Document | ShadowRoot> = [document];
    const moving: string[] = [];
    for (const root of roots) {
      for (const element of root.querySelectorAll('*')) if (element.shadowRoot) roots.push(element.shadowRoot);
      for (const animation of root.getAnimations()) {
        if (animation.playState === 'running' && animation.effect?.getTiming().iterations !== Infinity) {
          const target = (animation.effect as KeyframeEffect | null)?.target;
          moving.push(`${root instanceof ShadowRoot ? `${root.host.localName} › ` : ''}${target?.localName ?? '?'}`);
        }
      }
    }
    return moving;
  });

/** The finite animations running in the document alone (what the old `settled()` read) and in the toast's shadow root. */
const toastAnimations = (page: Page) =>
  page.evaluate(() => {
    const running = (list: Animation[]) =>
      list.filter((animation) => animation.playState === 'running' && animation.effect?.getTiming().iterations !== Infinity).length;
    const toast = [...document.querySelectorAll('ion-toast')].at(-1);
    return { document: running(document.getAnimations()), toast: running(toast?.shadowRoot?.getAnimations() ?? []) };
  });

/** The box of the toast on screen (its `.toast-wrapper`, in its shadow root) and the window's size. */
const toastBox = (page: Page) =>
  page.locator('ion-toast').last().evaluate((toast) => {
    const box = toast.shadowRoot?.querySelector('.toast-wrapper')?.getBoundingClientRect();
    if (!box) throw new Error('ion-toast without its .toast-wrapper');
    return { top: box.top, bottom: box.bottom, left: box.left, right: box.right, width: innerWidth, height: innerHeight };
  });

test('hub-e2e-capture: after settled() a toast of Ionic has stopped, whole on screen, in the three sizes', async ({ page, context }) => {
  await login(page, A, '/demo/items');
  const item = await createItem(context, A, uniqueName('Settled toast'));
  try {
    // «Save note» with the network down: the page's error toast (`toastError`), and nothing is saved.
    await page.route('**/api/demo/**', (route) => (route.request().method() === 'POST' ? route.abort('internetdisconnected') : route.continue()));
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto(`/demo/items/${item.id}`);
      const detail = shown(page);
      await detail.locator('[data-testid=demo-note] textarea').fill(`Note at ${size.label}`);
      await expect(detail.getByTestId('demo-note-save')).toBeEnabled();
      await settled(page);
      await detail.getByTestId('demo-note-save').click();
      await expect(page.locator('ion-toast').last()).toBeVisible();
      await settled(page);
      expect(await toastAnimations(page), `the toast still entering after settled() at ${size.label}`).toEqual({ document: 0, toast: 0 });
      expect(await stillMoving(page), `still moving after settled() at ${size.label}`).toEqual([]);
      const box = await toastBox(page);
      expect(box.top, `toast top at ${size.label}`).toBeGreaterThanOrEqual(0);
      expect(box.left, `toast left at ${size.label}`).toBeGreaterThanOrEqual(0);
      expect(box.bottom, `toast bottom at ${size.label}`).toBeLessThanOrEqual(box.height);
      expect(box.right, `toast right at ${size.label}`).toBeLessThanOrEqual(box.width);
      expect(await repeatedTop(page, await capture(page, `${TASK}-${size.label}`))).toBe(0);
    }
  } finally {
    await page.unroute('**/api/demo/**');
    const res = await api(context, A, 'POST', '/demo/items/delete', { id: item.id });
    expect(res.status).toBeLessThan(300);
  }
});

test('hub-e2e-capture: the snap() of cart_checkout captures a toast of Ionic once it has stopped, at 390, 834 and 1440', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/demo/items');
  const item = await createItem(context, A, uniqueName('Snap toast'));
  // Animations at a fifth of their speed (Chrome's own control): the toast enters for longer than a capture takes, so
  // a snap() that does not wait for it captures it still sliding in.
  const devtools = await context.newCDPSession(page);
  await devtools.send('Animation.enable');
  try {
    await page.route('**/api/demo/**', (route) => (route.request().method() === 'POST' ? route.abort('internetdisconnected') : route.continue()));
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      await devtools.send('Animation.setPlaybackRate', { playbackRate: 1 });
      await page.goto(`/demo/items/${item.id}`);
      const detail = shown(page);
      await detail.locator('[data-testid=demo-note] textarea').fill(`Note at ${size.label}`);
      await expect(detail.getByTestId('demo-note-save')).toBeEnabled();
      await settled(page);
      await devtools.send('Animation.setPlaybackRate', { playbackRate: 0.2 });
      await detail.getByTestId('demo-note-save').click();
      await expect(page.locator('ion-toast').last()).toBeVisible();
      await snap(page, `${TASK}-SNAP`, size.label);
      expect(await stillMoving(page), `still moving once snap() captured at ${size.label}`).toEqual([]);
    }
  } finally {
    await devtools.send('Animation.setPlaybackRate', { playbackRate: 1 });
    await page.unroute('**/api/demo/**');
    const res = await api(context, A, 'POST', '/demo/items/delete', { id: item.id });
    expect(res.status).toBeLessThan(300);
    await context.close();
  }
});

test('hub-e2e-capture: settled() waits for an animation two shadow roots deep and not for an endless one', async ({ page }) => {
  await login(page, A, '/demo/items');
  await settled(page);
  // A host with a shadow root holding an endless animation (a spinner) and, one shadow root further down, a finite one.
  await page.evaluate(() => {
    const host = document.createElement('div');
    const inner = document.createElement('div');
    const spinner = document.createElement('span');
    const deep = document.createElement('span');
    deep.textContent = 'moving';
    host.attachShadow({ mode: 'open' }).append(inner, spinner);
    inner.attachShadow({ mode: 'open' }).append(deep);
    document.body.append(host);
    spinner.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 400, iterations: Infinity });
    const finite = deep.animate([{ transform: 'translateX(0)' }, { transform: 'translateX(40px)' }], { duration: 800 });
    (window as unknown as { settledProbe: Animation }).settledProbe = finite;
  });
  await settled(page);
  expect(await page.evaluate(() => (window as unknown as { settledProbe: Animation }).settledProbe.playState)).toBe('finished');
  expect(await stillMoving(page)).toEqual([]);
});

test('hub-e2e-capture: settled() keeps waiting when the page reloads under it', async ({ page }) => {
  await login(page, A, '/demo/items');
  // Something still moves when the page reloads: `settled()` asks the new page instead of failing with the old one's
  // «Execution context was destroyed». A few rounds, each reloading at another moment of the wait.
  for (let round = 0; round < 5; round++) {
    await page.goto('/demo/items');
    await expect(page.getByTestId('demo-items-add').first()).toBeVisible();
    await page.evaluate((delay) => {
      document.body.appendChild(document.createElement('div')).animate([{ opacity: 0 }, { opacity: 1 }], { duration: 1500 });
      setTimeout(() => location.reload(), delay);
    }, 200 + round * 37);
    await settled(page);
  }
  await expect(page.getByTestId('demo-items-add').first()).toBeVisible();
  expect(await stillMoving(page)).toEqual([]);
});

test('hub-e2e-capture: the settled() of service-helpers.ts and of schedule-helpers.ts is the one of helpers.ts', () => {
  expect(settled).toBe(baseSettled);
  expect(scheduleSettled).toBe(baseSettled);
});
