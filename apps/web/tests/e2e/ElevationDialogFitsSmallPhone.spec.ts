// Regression test for ERPlora/hub#2445 — on a small phone the manager's approval dialog cut off its
// title and pushed «Cancel» below the bottom edge, and nothing in it scrolled.
//
// The dialog had `--height: auto` and a plain body: once the manager picked their name, the
// heading, the «what is being approved» sentence, the pinpad and — after five wrong PINs — the lock
// notice added up to more than a 375×667 screen, and Ionic centred the overflow. Measured on the
// bench: title at top = -25 px, «Cancelar» at bottom = 692 px, no scroller.
//
// The contract pinned here is the one every till PIN dialog keeps (Square, Toast): the title stays
// on screen at the top, the action row stays on screen at the bottom, and whatever does not fit in
// between scrolls. It is checked in both steps of the dialog (choosing who approves, typing the
// PIN with the lock notice up), on the phone of the report, on a phone held sideways (the lowest
// screen there is) and on the three viewports of the UI contract, in Spanish, whose copy is the
// longest the dialog has to hold.
//
// The dialog is opened through the shell's own approver (`lib/elevation` → `askForApproval`, the
// function the transport calls), so what is on screen is the real `ion-modal`, `ok-pinpad` and the
// real person list the runtime of the bench serves. The ask itself is scripted: what is under test
// is the layout, and the refusal it answers with is the tallest one the dialog can show.
import { test, expect, type Page } from '../bench-boot';
import { loggedInSession, VIEWPORTS } from './shell-visual-helpers';

test.use({ locale: 'es-ES' });

const SCREENS = [
  { width: 375, height: 667 },
  { width: 568, height: 320 },
  { width: 820, height: 1180 },
  ...VIEWPORTS,
] as const;

async function openApproval(page: Page, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await loggedInSession(page);
  await page.goto('/');
  await expect(page.locator('[data-testid="elevation-modal"]')).toBeAttached();
  await page.evaluate(async () => {
    const elevation = await import(/* @vite-ignore */ `${location.origin}/src/lib/elevation.ts`);
    // Not awaited: the promise is the caller's, and it only settles when somebody answers.
    void elevation.askForApproval({
      command: 'sales.void',
      payload: {},
      permission: 'sales.void',
      // The tallest refusal there is: the lock after five wrong PINs, with its wait in minutes.
      approve: () => Promise.reject({ code: 'too_many_attempts', retryAfterSecs: 300 }),
      approveWithBadge: () => Promise.reject({ code: 'hub.elevation.rejected' }),
    });
  });
  await expect(page.getByTestId('elevation-cancel')).toBeVisible();
  // Playwright calls an `ion-modal` visible while it is still sliding in (opacity and transform
  // mid-animation), and every box measured then is off by the slide. Measure the settled dialog.
  await page.waitForFunction(() => {
    const modal = document.querySelector('ion-modal.elevation-modal');
    const wrapper = modal?.shadowRoot?.querySelector('.modal-wrapper');
    // Before Ionic starts presenting, the wrapper is ALSO opaque and untransformed: what tells a
    // presented modal from one about to slide in is that it is no longer hidden and nothing on the
    // page (shadow roots included) is still animating.
    if (!modal || !wrapper || modal.classList.contains('overlay-hidden')) return false;
    if (document.getAnimations().some((a) => a.playState === 'running')) return false;
    const style = getComputedStyle(wrapper);
    const still = style.transform === 'none' || style.transform === 'matrix(1, 0, 0, 1, 0, 0)';
    return still && style.opacity === '1';
  });
}

async function boxOf(page: Page, testId: string) {
  const box = await page.getByTestId(testId).boundingBox();
  if (!box) throw new Error(`${testId} has no box`);
  return box;
}

/** The heading — the title and WHAT is being approved — and the action row are both inside the
 * screen, without scrolling anything: the manager never types a PIN under a sentence they cannot
 * read, and never has to hunt for the way out. */
async function expectHeadingAndCancelOnScreen(page: Page, height: number, also: string[] = []) {
  for (const testId of ['elevation-title', 'elevation-what', 'elevation-cancel', ...also]) {
    const box = await boxOf(page, testId);
    expect(box.y, `${testId} starts inside the screen`).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height, `${testId} ends inside the screen`).toBeLessThanOrEqual(height);
  }
}

/** Both edges of whatever sits between the heading and the actions can be scrolled into the gap
 * between them — the pinpad does not fit whole on a phone held sideways, but every key of it can
 * be brought on screen, and none of it hides under the heading or the actions. */
async function expectReachable(page: Page, testId: string) {
  for (const block of ['start', 'end'] as const) {
    await page.getByTestId(testId).evaluate((el, b) => el.scrollIntoView({ block: b }), block);
    const box = await boxOf(page, testId);
    const what = await boxOf(page, 'elevation-what');
    const cancel = await boxOf(page, 'elevation-cancel');
    if (block === 'start') {
      expect(box.y, `${testId}: its top scrolls to just below the heading`).toBeGreaterThanOrEqual(
        what.y + what.height - 1,
      );
      expect(box.y, `${testId}: its top scrolls above Cancel`).toBeLessThan(cancel.y);
    } else {
      expect(box.y + box.height, `${testId}: its bottom scrolls to just above Cancel`).toBeLessThanOrEqual(
        cancel.y + 1,
      );
      expect(box.y + box.height, `${testId}: its bottom scrolls below the heading`).toBeGreaterThan(
        what.y + what.height,
      );
    }
  }
}

test.describe('Manager approval dialog fits every screen (hub#2445)', () => {
  for (const viewport of SCREENS) {
    test(`${viewport.width}×${viewport.height}: title and Cancel stay on screen, the rest scrolls`, async ({
      page,
    }) => {
      await openApproval(page, viewport);

      // Step 1 — who approves.
      await expectHeadingAndCancelOnScreen(page, viewport.height);
      await expectReachable(page, 'elevation-person');

      // Step 2 — the PIN, with the lock notice up (the tallest the dialog gets).
      await page.getByTestId('elevation-person').first().click();
      const pinpad = page.getByTestId('elevation-pinpad');
      await expect(pinpad).toBeVisible();
      await pinpad.evaluate((el) => el.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '111111' } })));
      await expect(page.getByTestId('elevation-error')).toBeVisible();

      // The refusal is read where it lands, next to Cancel: a manager who just typed a wrong PIN
      // must not have to scroll to learn the dialog is locked for five minutes.
      await expectHeadingAndCancelOnScreen(page, viewport.height, ['elevation-error']);
      await expectReachable(page, 'elevation-pinpad');
      // Scrolling the pinpad, either way, never drags the heading or the notice off the screen.
      await expectHeadingAndCancelOnScreen(page, viewport.height, ['elevation-error']);

      // And Cancel, always there, still closes it.
      await page.getByTestId('elevation-cancel').click();
      await expect(pinpad).toBeHidden();
    });
  }
});
