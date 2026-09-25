// Regression test for ERPlora/hub#2100 — an e2e spec must not hand the router's navigation
// promise back across `page.evaluate`.
//
// What broke: `ModuleDeepLinkHiddenCopy.spec.ts` drove the shell with
// `page.evaluate(async (to) => { await router.push(to) })`. Playwright then awaits that promise
// over CDP, and Chromium's inspector only holds it WEAKLY. Twice on develop (runs 36045129248 and
// 36070769805, `1 failed, 40 passed`) the first navigation to a lazily loaded screen failed with
// `page.evaluate: Resulting promise was garbage collected.` while the navigation itself went on
// and landed — the trace shows the address already at `/m/e2e_till/pos` and the screen mounting.
// The product was fine; the wait was the defect, and it painted unrelated PRs red.
//
// The fix is to start the navigation without returning its promise and wait from OUTSIDE the page
// for what the promise stood for (the router committed the route, then Ionic settled). This guard
// keeps the pattern from coming back in any spec: it is a pattern, not a one-off, so it gets a
// mechanical check that costs milliseconds and needs no browser.
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const E2E_DIR = fileURLToPath(new URL('./e2e', import.meta.url));

/** `await`/`return` of a router navigation: the promise an evaluate would carry back over CDP. */
const AWAITED_ROUTER_NAVIGATION = /\b(?:await|return)\s+[\w.$]*\brouter\s*\.\s*(?:push|replace|go|back|forward)\s*\(/i;

function specs(): string[] {
  return readdirSync(E2E_DIR)
    .filter((name) => name.endsWith('.spec.ts'))
    .sort();
}

describe('e2e specs drive the router without carrying its promise over CDP (hub#2100)', () => {
  it('the check catches the shape that flaked', () => {
    expect(AWAITED_ROUTER_NAVIGATION.test('await app.config.globalProperties.$router.push(to);')).toBe(true);
    expect(AWAITED_ROUTER_NAVIGATION.test('return router.replace(path)')).toBe(true);
    expect(AWAITED_ROUTER_NAVIGATION.test('void app.config.globalProperties.$router.push(to);')).toBe(false);
  });

  it.each(specs())('%s does not await a router navigation', (name) => {
    const offending = readFileSync(join(E2E_DIR, name), 'utf8')
      .split('\n')
      .map((line, i) => ({ line: i + 1, text: line.trim() }))
      .filter(({ text }) => !text.startsWith('//') && AWAITED_ROUTER_NAVIGATION.test(text));
    expect(offending).toEqual([]);
  });
});
