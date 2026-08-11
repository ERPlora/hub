import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

// NO INSTALL MODAL (hub#685) — nothing greets a person with a dialog they did not ask for.
//
// The hub used to open «Get the full experience / Native view» over the dashboard the moment someone
// came in. It was wrong in two different ways at once, and only the second one is about the demo. On
// a real till it interrupts the FIRST task of the day, on every entry, until whoever is on shift
// finds the "don't show again" checkbox and does the product's job for it. On the public demo — a
// browser session that lasts an hour and whose whole pitch is «nothing to install» — it is the first
// thing a visitor sees of a product they came to look at, and it covers exactly the screen the demo
// exists to show.
//
// Ioan's decision (2026-08-10, hub#685) is not "hide it in demos": the modal goes, everywhere.
// Installing stays perfectly possible — it is a real PWA and every browser offers it from its own
// menu — but it becomes something a person GOES AND DOES, never something the app asks them about.
//
// This guard reads the SOURCE, following the convention of `no-purchase-steering.test.ts`, because
// the defect class is "somebody re-adds a helpful little dialog at boot eight weeks from now and
// nobody connects it to this issue". Asserting on a mounted tree would only cover the component we
// just deleted; this covers the one that has not been written yet.
const SRC = fileURLToPath(new URL('..', import.meta.url));

/**
 * What must not come back, and why each one on its own is enough to fail:
 *
 *  - `PwaInstallModal`        → the component itself, by name.
 *  - `installModalOpen`       → the state that opened it, in any new component.
 *  - `maybeShowInstallModal`  → the call at boot; this is the interruption proper.
 *  - `beforeinstallprompt`    → capturing the browser's own offer only makes sense to re-serve it
 *                               ourselves later. Left uncaptured, Chromium shows its own install
 *                               affordance in the address bar, which is exactly what we want.
 */
const BANNED = [
  'PwaInstallModal',
  'installModalOpen',
  'maybeShowInstallModal',
  'beforeinstallprompt',
];

/** Every source file the app ships, minus the tests that describe it. */
function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      out.push(...sourceFiles(path));
      continue;
    }
    if (!/\.(ts|vue)$/.test(entry)) continue;
    if (/\.test\.ts$/.test(entry)) continue;
    out.push(path);
  }
  return out;
}

describe('the shell never asks anyone to install it', () => {
  it('no shipped source mounts, opens or prepares an install prompt', () => {
    const offenders: string[] = [];

    for (const path of sourceFiles(SRC)) {
      const source = readFileSync(path, 'utf8');
      const lines = source.split('\n');
      for (const term of BANNED) {
        const line = lines.findIndex((l) => l.includes(term));
        if (line === -1) continue;
        offenders.push(`${path.slice(SRC.length)}:${line + 1} → ${term}`);
      }
    }

    // Named one per line: when this fails, the message IS the list of controls to deal with.
    expect(offenders.join('\n')).toBe('');
  });

  it('keeps the service worker: the PWA stays installable, it just stops asking', () => {
    // Removing the nag must not remove the reason someone would install it. The manifest plus a
    // service worker with a `fetch` handler is what makes the browser offer the install itself; take
    // the registration out with the modal and the app quietly stops being installable at all.
    const pwa = readFileSync(join(SRC, 'lib/pwa.ts'), 'utf8');
    expect(pwa).toContain("navigator.serviceWorker.register('/sw.js')");
  });
});
