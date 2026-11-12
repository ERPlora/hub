// @vitest-environment node
// flow: ninguno — e2e harness (hub#1303)
// `scrolledTo()` (helpers.ts) when the list paints itself again while the spec scrolls to what it found. After
// `page.setViewportSize`, the DataTable switches between its cards and its rows across its phone breakpoint a frame or
// more later (its `matchMedia` «change», #274): a spec checks the text in what the size before painted, and Playwright's
// `locator.scrollIntoViewIfNeeded` takes that element once and keeps it, so it throws «Element is not attached to the
// DOM» once the list paints it again (reservation-book.spec.ts, `saysWhy`, at 834). `scrolledTo` looks for it again
// and scrolls to what the list paints now; any other error fails as before, and a list that never stops painting
// itself again fails saying so. Nine specs and helpers had each written their own way past the same repaint before it (a
// retry of the scroll on a clock of 2 s, in `toPass`); the last block keeps a new copy of that retry from appearing
// anywhere in the e2e while those nine move to `scrolledTo` (hub#837), one by one.
import { globSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Locator } from '@playwright/test';
import { describe, expect, it } from 'vitest';

import { scrolledTo } from './helpers';

/** One element the fake list paints: a card (a phone) or a row (a tablet or a desk). */
interface Painted {
  kind: 'card' | 'row';
  connected: boolean;
}

/** The message Playwright throws when the element its scroll took is gone from the page. */
const NOT_ATTACHED =
  'locator.scrollIntoViewIfNeeded: Element is not attached to the DOM\n' +
  'Call log:\n  - attempting scroll into view action\n    - waiting for element to be stable\n';

/**
 * A reservation's reason in a list that paints `first`, and a locator for it that scrolls the way Playwright's does:
 * it takes the element painted when it is called, waits a turn of the event loop for it to stand still (a round trip
 * to the browser), and throws `NOT_ATTACHED` if the list painted it again meanwhile. `repaintsWhileScrolling` is how
 * many of the scrolls, from the first, the list paints itself again during (cards ↔ rows): what a resize that lands
 * between the spec's check and its scroll does. `fails` makes every scroll throw that error instead. Never a timer
 * (vitest.setup.ts): `setImmediate` runs in the next turn, so a scroll that looks again forever still lets Vitest's
 * clock cut the test instead of hanging the run.
 */
function reasonIn(first: Painted['kind'], { repaintsWhileScrolling = 0, fails }: { repaintsWhileScrolling?: number; fails?: Error } = {}) {
  let painted: Painted = { kind: first, connected: true };
  let repaints = repaintsWhileScrolling;
  const scrolled: Painted['kind'][] = [];
  let calls = 0;
  const repaint = (): void => {
    painted.connected = false;
    painted = { kind: painted.kind === 'card' ? 'row' : 'card', connected: true };
  };
  const reason = {
    async scrollIntoViewIfNeeded() {
      calls += 1;
      if (fails) throw fails;
      const taken = painted;
      if (repaints > 0) {
        repaints -= 1;
        queueMicrotask(repaint);
      }
      await new Promise((resolve) => setImmediate(resolve));
      if (!taken.connected) throw new Error(NOT_ATTACHED);
      scrolled.push(taken.kind);
    },
    toString: () => "locator('[data-testid=reservation-list-reason]')",
  };
  return {
    reason: reason as unknown as Locator,
    scrolled,
    calls: () => calls,
  };
}

describe('scrolledTo() when the list paints itself again for the new size (hub#1303)', () => {
  it('scrolls to the row the list paints for the new size when it repaints the card while scrolling', async () => {
    // The spec found the reason in the card the size before painted; the list paints it again as a row meanwhile.
    const list = reasonIn('card', { repaintsWhileScrolling: 1 });

    await scrolledTo(list.reason);

    expect(list.scrolled).toEqual(['row']);
    expect(list.calls()).toBe(2);
  });

  it('looks for it again as many times as the list paints itself again, and scrolls to the last one', async () => {
    const list = reasonIn('card', { repaintsWhileScrolling: 3 });

    await scrolledTo(list.reason);

    expect(list.scrolled).toEqual(['row']);
    expect(list.calls()).toBe(4);
  });

  it('scrolls once when nothing paints itself again', async () => {
    const list = reasonIn('row');

    await scrolledTo(list.reason);

    expect(list.scrolled).toEqual(['row']);
    expect(list.calls()).toBe(1);
  });

  it('fails as before on any other error of the scroll, without looking again', async () => {
    const timeout = new Error('locator.scrollIntoViewIfNeeded: Timeout 30000ms exceeded.');
    const list = reasonIn('row', { fails: timeout });

    await expect(scrolledTo(list.reason)).rejects.toBe(timeout);
    expect(list.calls()).toBe(1);
  });

  it('fails naming the locator when the list never stops painting itself again', async () => {
    const list = reasonIn('card', { repaintsWhileScrolling: Number.POSITIVE_INFINITY });

    await expect(scrolledTo(list.reason)).rejects.toThrow(
      /scrolledTo: locator\('\[data-testid=reservation-list-reason\]'\) was painted again \d+ times while scrolling to it/,
    );
    expect(list.scrolled).toEqual([]);
  });
});

const E2E_DIR = dirname(fileURLToPath(import.meta.url));

/** The e2e's helpers and specs, in its subfolders too: not Vitest's own tests nor what a run leaves (dot folders). */
const helpersAndSpecs = (): string[] =>
  globSync('**/*.ts', { cwd: E2E_DIR, exclude: (name) => name === 'node_modules' || name.startsWith('.') || name.endsWith('.test.ts') });

/** The bodies of the retries in `source` that scroll: an `expect(async () => { … }).toPass()` with a
 *  `scrollIntoViewIfNeeded` in it, the way past a repaint `scrolledTo` is the one of. */
function scrollRetries(source: string): string[] {
  return [...source.matchAll(/expect\(\s*async\s*\(\)\s*=>\s*\{([\s\S]*?)\}\s*(?:,[^()]*?)?\)\s*\.toPass\(/g)]
    .map((match) => match[1])
    .filter((body) => body.includes('scrollIntoViewIfNeeded'));
}

/** The specs and helpers that still retry their own scroll (a clock of 2 s in `toPass`), written before `scrolledTo`:
 *  hub#837 moves each to it and takes it off this list. A new copy fails the check; one that moved fails it too until
 *  it leaves the list, so the list only shrinks. */
const OWN_RETRIES_LEFT = [
  'cash-register-flows.spec.ts',
  'customer-flows.spec.ts',
  'fix-whatsapp-inbox-template-header-media.spec.ts',
  'payment-flow.spec.ts',
  'staff-commissions.spec.ts',
  'staff-flows.spec.ts',
  'tax-helpers.ts',
  'verifactu-flows.spec.ts',
  'website-flows.spec.ts',
];

describe('the e2e scrolls past a repaint one way, with scrolledTo of helpers.ts (hub#1303)', () => {
  it('there are helpers and specs to look at, the shared helper and the lists that scrolled their own way among them', () => {
    expect(helpersAndSpecs()).toEqual(
      expect.arrayContaining(['helpers.ts', 'reservation-book.spec.ts', 'tax-helpers.ts', 'website-flows.spec.ts', 'qa/assistant-battery.spec.ts']),
    );
    expect(helpersAndSpecs().filter((name) => name.endsWith('.test.ts'))).toEqual([]);
  });

  it('no helper or spec retries a scroll of its own but the ones still to move to scrolledTo (hub#837)', () => {
    const own = helpersAndSpecs().filter((name) => scrollRetries(readFileSync(join(E2E_DIR, name), 'utf8')).length > 0);
    expect(own.sort()).toEqual(OWN_RETRIES_LEFT);
  });

  it('the check reads the shapes the copies had as a retry of a scroll, and scrolledTo or another retry as none', () => {
    const copies = [
      [
        '    await expect(async () => {',
        '      await seen.scrollIntoViewIfNeeded({ timeout: 2000 });',
        '      await expect(seen).toBeInViewport({ timeout: 1000 });',
        '    }, `${key} at ${vp.label}`).toPass();',
      ],
      [
        '    await expect(async () => {',
        '      const seen = target();',
        '      await seen.scrollIntoViewIfNeeded({ timeout: 2000 });',
        '      await expect(seen).toBeInViewport({ timeout: 1000 });',
        '    }, `${key} at ${vp.label}`).toPass();',
      ],
      ['await expect(async () => { await row.scrollIntoViewIfNeeded(); }).toPass({ timeout: 10_000 });'],
    ].map((lines) => lines.join('\n'));
    const others = [
      '    await scrolledTo(target());',
      '    await expect(async () => {\n      expect(await rowNames(page)).toContain(name);\n    }).toPass();',
      '    await row.scrollIntoViewIfNeeded();',
    ];
    expect(copies.map((source) => scrollRetries(source).length)).toEqual(copies.map(() => 1));
    expect(others.flatMap(scrollRetries)).toEqual([]);
  });
});
