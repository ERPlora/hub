// The shell's toasts as the specs find them. The shell paints one stack at the bottom edge and one at the top, each
// with up to three toasts on screen, the newest first in the DOM: a toast is found by what it says, never by its place.
import { expect, type Locator, type Page } from '@playwright/test';

type Scope = Page | Locator;

const TOAST = '[data-testid="toast"]';

/** Every toast on screen at both edges, the newest of each edge first (a toast that is leaving still counts). */
export const toasts = (scope: Scope): Locator => scope.locator(TOAST);

/** The newest toast that says `text`. */
export const toastSaying = (scope: Scope, text: string | RegExp): Locator => toasts(scope).filter({ hasText: text }).first();

/** The toast shown with `id` (`toast…(message, { id })`). */
export const toastWithId = (scope: Scope, id: string): Locator => scope.locator(`${TOAST}[data-toast-id="${id}"]`);

/** The newest toast at the bottom edge, where every toast goes unless it asks for the top. */
export const newestToast = (scope: Scope): Locator =>
  scope.locator(`[data-testid="toast-stack"][data-position="bottom"] ${TOAST}`).first();

/** How many finite animations still run on the newest toast and inside it (its entrance), read on that toast alone. */
export const toastAnimationsRunning = (page: Page): Promise<number> =>
  newestToast(page).evaluate((toast) => {
    const running = (animation: Animation) => animation.playState === 'running' && animation.effect?.getTiming().iterations !== Infinity;
    return toast.getAnimations({ subtree: true }).filter(running).length;
  });

/** What a person can read on screen now: each toast not faded out whose words are not hidden behind the front one. */
export function readableToasts(page: Page): Promise<string[]> {
  return toasts(page).evaluateAll((all) =>
    all
      .filter((t) => getComputedStyle(t).opacity !== '0')
      .filter((t) => getComputedStyle(t.firstElementChild ?? t).opacity !== '0')
      .map((t) => (t as HTMLElement).innerText.trim()),
  );
}

/** The id of the first toast on screen; `null` with none. */
const firstId = async (all: Locator): Promise<string | null> => ((await all.count()) > 0 ? all.first().getAttribute('data-toast-id') : null);

/**
 * Closes every toast on screen as a person does with the keyboard: Escape on the toast that has the focus. One that
 * waited its turn comes on screen as another leaves, so each is followed by its id until it has gone.
 */
export async function dismissToasts(page: Page): Promise<void> {
  const all = toasts(page);
  for (let id = await firstId(all); id !== null; id = await firstId(all)) {
    const toast = toastWithId(page, id);
    // A toast whose time ran out meanwhile cannot take the key: its leaving is what is checked next.
    await toast.press('Escape', { timeout: 2000 }).catch(() => undefined);
    await expect(toast).toHaveCount(0);
  }
}
