// @vitest-environment happy-dom
// hub#2073 — the document the hub serves must never be a blank page while the shell boots.
//
// `main.ts` mounts the app only after the runtime answers `/api/hub/context` (and after a shell
// courier, if any, is redeemed). A hub that answers slowly — waking up, a bad link — left `#app`
// EMPTY for as long as that took: a grey page with no menu, no message and no login card, on ANY
// address. It was reported on `/m/…` deep links because that is where it was filmed, but a probe
// that delays `/api/hub/context` paints the same blank on `/apps`.
//
// The cure is the one every POS/ERP web app uses (Square, Shopify, Odoo): a static progress
// indicator INSIDE `#app`, painted by the HTML itself before any script runs, that Vue replaces
// when it mounts. These assertions read the served document, because that is the only thing on
// screen during the wait — nothing from the bundle (its CSS included) exists yet.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// `import.meta.url` is not a file URL under happy-dom; the suite always runs from `apps/web`.
const INDEX = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');

function served(): Document {
  return new DOMParser().parseFromString(INDEX, 'text/html');
}

describe('the hub document shows progress while the shell boots (hub#2073)', () => {
  it('the mount point is not empty before the app mounts', () => {
    const app = served().getElementById('app');
    expect(app).not.toBeNull();
    expect(app!.children.length).toBeGreaterThan(0);
  });

  it('what it holds is announced as a progress status, not decoration', () => {
    const app = served().getElementById('app')!;
    const status = app.querySelector('[role="status"]');
    expect(status).not.toBeNull();
    expect(status!.getAttribute('aria-busy')).toBe('true');
    // On the indicator and NOT on `#app`: Vue replaces the mount point's CONTENT, not its
    // attributes, so a busy flag on `#app` would announce the working shell as busy forever.
    expect(app.hasAttribute('aria-busy')).toBe(false);
  });

  it('it is styled by the document itself, not by the bundle that has not loaded yet', () => {
    const doc = served();
    const indicator = doc.querySelector('#app [role="status"]')!;
    const css = Array.from(doc.head.querySelectorAll('style'))
      .map((s) => s.textContent ?? '')
      .join('\n');
    // Every class the indicator uses has a rule in the document's own <style>.
    const classes = Array.from(indicator.querySelectorAll('*'))
      .concat(indicator)
      .flatMap((el) => Array.from(el.classList));
    expect(classes.length).toBeGreaterThan(0);
    for (const cls of classes) expect(css).toContain(`.${cls}`);
    // And it spins: a still shape on a grey page reads as frozen, which is the defect.
    expect(css).toMatch(/animation\s*:/);
    expect(css).toMatch(/@keyframes/);
  });

  it('it carries no hardcoded prose: the document cannot translate, so it shows no words', () => {
    const indicator = served().querySelector('#app [role="status"]')!;
    expect((indicator.textContent ?? '').trim()).toBe('');
  });
});
