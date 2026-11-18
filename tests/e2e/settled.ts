// The one wait of the specs for «nothing moves» and a painted frame; its detector asks every open shadow root too.
import { expect, type Page } from '@playwright/test';

/** How long `untilStill` waits for the page to stop moving: Ionic's overlays enter in well under a second. */
const STILL_TIMEOUT_MS = 10_000;

/**
 * What moves on the page now (run in the page, so self-contained): every finite animation running in the document
 * and in every open shadow root under it, however deep. `document.getAnimations()` leaves shadow roots out, and Ionic
 * animates its overlays (`ion-modal`, `ion-popover`), an `ion-progress-bar`'s bar or an `ion-segment`'s
 * indicator inside theirs. Endless ones (spinners, a shimmer) never stop, so they never count.
 */
function movingInPage(): string[] {
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

/**
 * Puts `movingInPage` in the page as `window.__movingInPage`, for a probe that runs in the page frame by frame and has
 * to know, in the same frame, whether anything moves (the same detector as `untilStill`, never a copy of it).
 */
export async function exposeMovingInPage(page: Page): Promise<void> {
  await page.evaluate(`window.__movingInPage = ${movingInPage.toString()}`);
}

/** A page that navigates while `untilStill` asks what moves: it asks the new page next. Anything else fails the spec. */
function navigating(error: unknown): string[] {
  if (error instanceof Error && /Execution context was destroyed/.test(error.message)) return ['(navigating)'];
  throw error;
}

/**
 * Waits until nothing moves on screen (`movingInPage`): a capture taken mid-animation shows a state the screen is
 * leaving. A page that reloads meanwhile is asked again; one that still moves after `STILL_TIMEOUT_MS` fails the spec
 * with `message`, naming what moves.
 */
export async function untilStill(page: Page, message = 'untilStill(): still moving'): Promise<void> {
  await expect
    .poll(() => page.evaluate(movingInPage).catch(navigating), {
      message,
      timeout: STILL_TIMEOUT_MS,
      intervals: [16],
    })
    .toEqual([]);
}

/**
 * Resolves once the browser has painted the page as it is now: a frame's callbacks run before it is painted, the next
 * frame's once it has been. A screenshot right after `setViewportSize` needs it.
 */
export async function painted(page: Page): Promise<void> {
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))));
}

/**
 * Settled: nothing moving (`untilStill`: an overlay of Ionic entering included, endless spinners aside) and the page
 * painted as it is now (`painted`): the capture shows the state the flow reached, not a frame of Ionic's transition nor,
 * right after `setViewportSize`, the previous size's. The one wait of every spec (service-helpers.ts and
 * schedule-helpers.ts hand it out too).
 */
export async function settled(page: Page): Promise<void> {
  await untilStill(page);
  await painted(page);
}
