// Regression test for ERPlora/hub#1752 — the visual bench must COMPARE something.
//
// The bug this pins, and why it needed a guard of its own: the hub has five `*Visual.spec.ts`
// that screenshot the shell at three widths, and NOT ONE reference image was ever committed
// (`visual-baselines.yml` had zero runs; hub#1250 closed as done without them landing). When the
// reference is missing the case SKIPS, so every PR got a green `playwright (test:e2e)` check that
// reads as "the layout was checked" while nothing had been looked at — the worst of both worlds,
// and the reason hub#1715's QR had to be measured by hand in a browser.
//
// Why this guard is a vitest file and not another Playwright case:
//
//   · It has to fail on the state where there is NOTHING to compare, and a Playwright spec cannot
//     report that honestly — the very run that would detect it is the one being skipped.
//   · It costs milliseconds and needs no browser and no database, so a repo that loses its
//     baselines goes red in `pnpm test` instead of twenty minutes into the e2e job.
//
// What it does NOT replace: a baseline missing ONE file still fails inside Playwright, through
// `updateSnapshots: 'none'` (`visual-baseline-gate.ts`, hub#1250). This guard covers the other
// shape — the screen whose references never existed, which `'none'` cannot see because the case
// is skipped before it asserts.
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { VIEWPORTS } from './e2e/viewports.ts';

const E2E_DIR = fileURLToPath(new URL('./e2e', import.meta.url));

// The baselines the REPO ships are the Linux ones: they are what CI compares against. A Mac's
// PNGs never match Linux's font stack, so they are gitignored (`*-darwin.png`) and must not count
// as "this screen is covered" — a guard that accepted them would go green on the developer's
// machine and red in CI, which is the opposite of useful.
const PLATFORM_SUFFIX = '-chromium-linux.png';

/** Every `*Visual.spec.ts` under `tests/e2e/`, which is the whole visual contract of the shell. */
function visualSpecs(): string[] {
  return readdirSync(E2E_DIR)
    .filter((name) => name.endsWith('Visual.spec.ts'))
    .sort();
}

/**
 * The snapshot prefix a spec uses, read from the spec itself (`const snapshot = \`login-${width}.png\``).
 *
 * Parsed instead of listed here on purpose: a hardcoded list is a second place to update, and the
 * failure mode of forgetting it is this guard passing while a new screen goes uncovered — the
 * exact shape of the defect it exists to prevent.
 */
function snapshotPrefix(spec: string): string {
  const source = readFileSync(join(E2E_DIR, spec), 'utf8');
  const match = /const snapshot = `([a-z0-9-]+)-\$\{width\}\.png`/.exec(source);
  expect(
    match,
    `${spec}: this guard could not find its snapshot name. It reads the literal ` +
      '`const snapshot = `<name>-${width}.png`` — keep that shape, or teach the guard the new one. ' +
      'Leaving it unreadable would silently drop this screen from the visual contract (hub#1752).',
  ).not.toBeNull();
  return match![1];
}

describe('el banco visual tiene contra qué comparar (hub#1752)', () => {
  it('hay specs visuales que guardar — si no, el resto de este fichero no prueba nada', () => {
    // Without this, deleting every `*Visual.spec.ts` would turn the guard below into a loop over
    // an empty list: green, and nothing left comparing anything.
    expect(visualSpecs().length).toBeGreaterThanOrEqual(5);
  });

  it.each(visualSpecs())(
    'REGRESIÓN: %s tiene su imagen de referencia en los tres viewports',
    (spec) => {
      const dir = join(E2E_DIR, `${spec}-snapshots`);
      expect(
        existsSync(dir),
        `${spec} no tiene ni una imagen de referencia (${spec}-snapshots/ no existe), así que sus ` +
          'capturas se saltan y el check sale verde sin mirar la pantalla. Regenéralas con el ' +
          'workflow «Regenerar baselines visuales (Linux)» y commitea el artefacto (hub#1752).',
      ).toBe(true);

      const prefix = snapshotPrefix(spec);
      const present = readdirSync(dir);
      for (const { width } of VIEWPORTS) {
        expect(present, `${spec}: falta la referencia de ${width}px`).toContain(
          `${prefix}-${width}${PLATFORM_SUFFIX}`,
        );
      }
    },
  );
});

// Regression test for ERPlora/hub#1752 — a baseline that contains a CLOCK is a booby trap.
//
// Found by looking at the images the runner produced before committing them: the dashboard reads
// «Buenos días · Hoy, viernes, 11 de septiembre» and settings reads «Automática · Europe/Madrid,
// 08:51». Committed as they came, the dashboard baseline would have gone red the next DAY (and at
// every change of greeting), and settings on the next MINUTE — turning every PR in the repo red
// over a diff it never touched, which is the disease hub#1806/#1818 exist to cure. A visual
// contract that cries wolf gets muted, and a muted contract is the state hub#1752 is closing.
//
// So the clock is frozen for the whole visual contract, and this guard keeps it that way: a new
// `*Visual.spec.ts` that screenshots a screen showing the time cannot forget.
describe('el contrato visual no fotografía el reloj (hub#1752)', () => {
  it.each(visualSpecs())('%s congela el reloj antes de capturar', (spec) => {
    const source = readFileSync(join(E2E_DIR, spec), 'utf8');
    expect(
      /freezeVisualClock\s*\(/.test(source),
      `${spec} no llama a freezeVisualClock(page): si la pantalla pinta la hora o la fecha, su ` +
        'baseline caduca sola y pone en rojo PRs que no la han tocado (hub#1752).',
    ).toBe(true);
  });
});

// Regression test for ERPlora/hub#1752 — a baseline that contains the install QR is a booby trap,
// and hub#1812 (this same branch) is what armed it.
//
// The sidebar QR encodes the address of the hub ON SCREEN, which in the bench is
// `http://localhost:<port>` (`lib/install-qr.ts` → `hubUrl(host) ?? origin`). Until hub#1812 the
// bench pinned 8787/5173, so that address — and therefore every module of the symbol — was the
// same on every run. Now each run allocates its own port (`bench-ports.ts`), so the QR is
// different EVERY TIME.
//
// Measured on 2026-09-11, regenerating at `HUB_WEB_URL=http://localhost:8850` and comparing at
// `:8860` with nothing else changed: the four 1440px screens that paint the sidebar — apps,
// dashboard, employees and settings — all failed (dashboard: 3168 px, ratio 0.01, against a
// `maxDiffPixelRatio` of 0.002). The 834/390 captures survive only because the sidebar is not on
// screen at those widths.
//
// So the symbol is MASKED, not frozen: what it encodes is genuinely machine-specific, and its
// content already has unit tests of its own (`lib/install-qr.test.ts`,
// `components/sidebar-qr-symbol.test.ts`). Masking keeps the QR's BOX in the contract — Playwright
// paints a solid rectangle over the locator — so a code that disappears, moves or changes size
// still turns the capture red. What stops being compared is only the pixel noise of the address.
describe('el contrato visual no fotografía el QR de instalación (hub#1752)', () => {
  it.each(visualSpecs())('%s tapa el QR antes de capturar', (spec) => {
    const source = readFileSync(join(E2E_DIR, spec), 'utf8');
    expect(
      /visualSnapshotMask\s*\(/.test(source),
      `${spec} no pasa visualSnapshotMask(page) a toHaveScreenshot(): el QR del sidebar codifica ` +
        'el puerto del banco, que desde hub#1812 cambia en cada corrida, así que su baseline ' +
        'caduca sola y pone en rojo PRs que no han tocado esa pantalla (hub#1752).',
    ).toBe(true);
  });
});
