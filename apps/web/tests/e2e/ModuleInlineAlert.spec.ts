// A module's inline confirmation dialog can be pressed the FIRST time it opens (hub#2162).
//
// What it pins: module screens are Lit components with a shadow root, and five of them (staff,
// schedules, taxes, appointments, verifactu) confirm with an `<ion-alert>` written INSIDE that
// shadow root. Stencil attaches a scoped component's stylesheet to the root node it first renders
// in, so the alert's sheet lands in the module's `shadowRoot.adoptedStyleSheets`. On `present()`
// Ionic's core delegate teleports the alert to `ion-app`, where that sheet does not apply, and
// Stencil never attaches it again. Until the shell itself had shown an alert of its own, the
// dialog painted unstyled at the foot of the page with its backdrop covering the whole screen:
// a real click on «Cancel» landed on `ion-backdrop` and the person could not finish the action.
//
// Why this is a bench spec and not a unit test: the defect lives in the interplay between the
// real Stencil runtime, the real overlay delegate and the browser's style scoping. A test with a
// simulated Ionic cannot see it (the same lesson as hub#2040), so this drives the shell with its
// real Ionic and a stand-in module component built exactly like a Lit one: a custom element with
// an open shadow root and an `<ion-alert>` rendered inside it.
//
// The probe must be the first alert of the session — the page is loaded fresh and nothing else is
// opened before it. Opening any shell alert first hides the bug, which is precisely how it slipped
// past short manual checks.
import { test, expect } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';
import type { Page } from '@playwright/test';
import { VIEWPORTS } from './viewports';

const HOST_TAG = 'e2e-inline-alert-host';

/** Mounts a Lit-like module component whose shadow root holds an `<ion-alert>`, and presents it. */
async function presentAlertFromShadowRoot(page: Page): Promise<void> {
  await page.evaluate(async (tag) => {
    if (!customElements.get(tag)) {
      customElements.define(
        tag,
        class extends HTMLElement {
          constructor() {
            super();
            this.attachShadow({ mode: 'open' });
          }
        },
      );
    }
    const host = document.createElement(tag);
    const content = document.querySelector('ion-router-outlet .ion-page:not(.ion-page-hidden) ion-content');
    (content ?? document.body).appendChild(host);
    type AlertEl = HTMLElement & { header: string; message: string; buttons: unknown[]; isOpen: boolean };
    const alert = document.createElement('ion-alert') as AlertEl;
    alert.header = 'Deactivate employee';
    alert.message = 'This probe mirrors a module confirmation.';
    alert.buttons = [
      { text: 'Cancel', role: 'cancel', htmlAttributes: { 'data-testid': 'e2e-inline-alert-cancel' } },
      { text: 'Deactivate', role: 'confirm', htmlAttributes: { 'data-testid': 'e2e-inline-alert-confirm' } },
    ];
    alert.addEventListener('ionAlertDidPresent', () => {
      host.dataset.presented = 'true';
    });
    alert.addEventListener('ionAlertDidDismiss', (e) => {
      host.dataset.dismissedRole = String((e as CustomEvent<{ role?: string }>).detail?.role ?? '');
    });
    host.shadowRoot!.appendChild(alert);
    // Let it hydrate INSIDE the shadow root, like a module's alert does on its first render (the
    // custom-elements build has no `componentOnReady`, so wait for the rendered wrapper), then open
    // it the way the modules do: through `isOpen`.
    for (let i = 0; i < 100 && !alert.querySelector('.alert-wrapper'); i++) {
      await new Promise((r) => requestAnimationFrame(r));
    }
    if (!alert.querySelector('.alert-wrapper')) throw new Error('ion-alert never rendered in the shadow root');
    alert.isOpen = true;
  }, HOST_TAG);
}

test.describe("a module's inline ion-alert is styled and pressable the first time (hub#2162)", () => {
  for (const viewport of VIEWPORTS) {
    test(`at ${viewport.width}px the Cancel button receives the real click`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await loggedInSession(page);
      await page.goto('/settings');
      await expect(page.locator('ion-router-outlet .ion-page:not(.ion-page-hidden)').first()).toBeVisible();

      await presentAlertFromShadowRoot(page);

      await expect(page.locator(HOST_TAG)).toHaveAttribute('data-presented', 'true');
      const cancel = page.getByTestId('e2e-inline-alert-cancel');
      await expect(cancel).toBeVisible();

      // The dialog is centred like any shell dialog, not dumped at the foot of the page.
      const wrapper = await page.locator('ion-alert .alert-wrapper').boundingBox();
      expect(wrapper, 'the alert wrapper has a box').not.toBeNull();
      const centreY = wrapper!.y + wrapper!.height / 2;
      expect(Math.abs(centreY - viewport.height / 2)).toBeLessThan(viewport.height * 0.15);
      expect(wrapper!.width).toBeLessThan(viewport.width);

      // What the finger touches at the centre of «Cancel» is the button, not the backdrop.
      const hitAtCancel = await cancel.evaluate((btn) => {
        const r = btn.getBoundingClientRect();
        const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
        return hit === btn || btn.contains(hit) ? 'button' : (hit?.tagName.toLowerCase() ?? 'nothing');
      });
      expect(hitAtCancel).toBe('button');

      // A real click (no `force`): Playwright refuses it if anything intercepts the pointer.
      await cancel.click({ timeout: 5_000 });
      await expect(page.locator(HOST_TAG)).toHaveAttribute('data-dismissed-role', 'cancel');
    });
  }
});

// The same teleport hits an inline `<ion-modal>` (inventory, sales, services and tables open their
// forms that way): the modal itself keeps its styles (it has its own shadow root), but the scoped
// fields inside it were hydrated in the module's shadow root and lose theirs once the modal moves
// to `ion-app`. Measured before the fix: the `ion-input` of such a form came out `position: static`
// instead of Ionic's `relative`, in both modes (modules set `mode="md"` on their inputs).
test('the fields of an inline ion-modal keep their styles once it is presented (hub#2162)', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await loggedInSession(page);
  await page.goto('/settings');
  await expect(page.locator('ion-router-outlet .ion-page:not(.ion-page-hidden)').first()).toBeVisible();

  const positions = await page.evaluate(async (tag) => {
    if (!customElements.get(tag)) {
      customElements.define(
        tag,
        class extends HTMLElement {
          constructor() {
            super();
            this.attachShadow({ mode: 'open' });
          }
        },
      );
    }
    const host = document.createElement(tag);
    document.body.appendChild(host);
    host.shadowRoot!.innerHTML =
      '<ion-modal><ion-content><ion-list>' +
      '<ion-item><ion-input data-probe="ios" label="Name"></ion-input></ion-item>' +
      '<ion-item><ion-input data-probe="md" mode="md" fill="outline" label="Code"></ion-input></ion-item>' +
      '</ion-list></ion-content></ion-modal>';
    const frames = (n: number) =>
      (async () => {
        for (let i = 0; i < n; i++) await new Promise((r) => requestAnimationFrame(r));
      })();
    const modal = host.shadowRoot!.querySelector('ion-modal') as HTMLElement & { isOpen: boolean };
    await frames(30);
    modal.isOpen = true;
    await new Promise((r) => modal.addEventListener('ionModalDidPresent', r, { once: true }));
    const read = (probe: string) => {
      const input = document.querySelector<HTMLElement>(`ion-app ion-modal ion-input[data-probe="${probe}"]`);
      return input ? getComputedStyle(input).position : 'not teleported';
    };
    return { ios: read('ios'), md: read('md') };
  }, HOST_TAG);

  expect(positions).toEqual({ ios: 'relative', md: 'relative' });
});
