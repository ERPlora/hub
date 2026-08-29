// hub#1298 — triaged as DESFASADA against `origin/develop`. The issue assumed Ionic's OLD
// default `--ion-color-danger: #eb445a` (~3.81:1 on white, under WCAG AA's 4.5:1 floor), the
// same figure Ionic ships/shipped for `warning` (hub#1291/#1299). But this shell never overrides
// `danger` in `theme/variables.css`, and the pinned `@ionic/core@8.8.9` (see `package.json`,
// `pnpm-lock.yaml`) ships a DIFFERENT, already-accessible default:
//
//   --ion-color-danger        #c5000f   6.21:1 on white
//   --ion-color-danger-shade  #ad000d   7.55:1 on white
//
// Confirmed in a real browser (throwaway harness, hub#1298 PR body): `.hero-failed`
// (`BlueprintHeroCard.vue`) and `noteTextColor()`'s danger pass-through (`ImportPanel.vue`) both
// resolve to `#ad000d` today — 7.55:1, well clear of AA. Unlike hub#1291's `warning` fix, no
// icon-only remap is needed for either component: reapplying that pattern to a color that
// already passes would just be churn.
//
// What the audit (the issue's real ask) turned up instead: `SystemPage.vue`'s `.event-row__error`
// carried `var(--ion-color-danger, #eb445a)` — the exact STALE Ionic value, hardcoded as a CSS
// fallback that never actually renders (the custom property is always defined via
// `@ionic/core`'s own `core.css`) but is misleading source-of-truth and is almost certainly where
// this issue's `#eb445a` figure came from. `SetupBlockingStrip.vue` already carried the CORRECT
// current fallback (`var(--ion-color-danger, #c5000f)`), so the two files disagreed with each
// other about what "the danger color" even is.
//
// This guard, like `warning-text-contrast.hub1291.test.ts`, is a SOURCE test: no runtime error
// would ever flag a hardcoded contrast-failing color literal.
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = fileURLToPath(new URL('..', import.meta.url));
const THEME_DIR = fileURLToPath(new URL('.', import.meta.url));

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sourceFiles(full));
    else if (entry.name.endsWith('.vue') || entry.name.endsWith('.css')) out.push(full);
  }
  return out;
}

// WCAG 2.x relative-luminance contrast ratio — same formula as hub#1291's guard.
function channel(c: number): number {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}
function luminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}
function contrastRatio(a: [number, number, number], b: [number, number, number]): number {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}
function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)];
}

const WHITE: [number, number, number] = [255, 255, 255];
const AA_FLOOR = 4.5;

/** Any `var(--ion-color-danger[-shade], #hex)` fallback literal, wherever it appears. */
const DANGER_VAR_WITH_FALLBACK = /var\(\s*(--ion-color-danger(?:-shade)?)\s*,\s*(#[0-9a-fA-F]{3,8})\s*\)/g;

function dangerFallbackOffenders(source: string): Array<{ token: string; hex: string; ratio: number }> {
  const offenders: Array<{ token: string; hex: string; ratio: number }> = [];
  for (const m of source.matchAll(DANGER_VAR_WITH_FALLBACK)) {
    const [, token, hex] = m;
    const ratio = contrastRatio(hexToRgb(hex), WHITE);
    if (ratio < AA_FLOOR) offenders.push({ token, hex, ratio });
  }
  return offenders;
}

describe('the real @ionic/core danger default passes WCAG AA today (hub#1298 premise check)', () => {
  it('is #c5000f / #ad000d for the pinned @ionic/core version — not the older #eb445a', () => {
    // Read the ACTUAL installed package: if a future dependency bump ships a less accessible
    // default (as Ionic once did for `warning`, per hub#1291), this goes red instead of staying
    // silently wrong.
    const corePath = join(SRC, '..', 'node_modules', '@ionic', 'core', 'css', 'core.css');
    const coreCss = readFileSync(corePath, 'utf8');
    const danger = coreCss.match(/--ion-color-danger:\s*(#[0-9a-fA-F]{3,8})/)?.[1];
    const dangerShade = coreCss.match(/--ion-color-danger-shade:\s*(#[0-9a-fA-F]{3,8})/)?.[1];
    expect(danger, 'core.css must declare --ion-color-danger').toBeTruthy();
    expect(dangerShade, 'core.css must declare --ion-color-danger-shade').toBeTruthy();

    const dangerRatio = contrastRatio(hexToRgb(danger!), WHITE);
    const shadeRatio = contrastRatio(hexToRgb(dangerShade!), WHITE);

    expect(dangerRatio, `--ion-color-danger (${danger}) vs white`).toBeGreaterThanOrEqual(AA_FLOOR);
    expect(shadeRatio, `--ion-color-danger-shade (${dangerShade}) vs white`).toBeGreaterThanOrEqual(AA_FLOOR);
  });

  it('the shell theme does not override danger with a value that would fail AA', () => {
    const variablesCss = readFileSync(join(THEME_DIR, 'variables.css'), 'utf8');
    // Only the un-scoped `:root` block — a `.ion-palette-dark` override is a separate surface.
    const rootBlock = variablesCss.match(/:root\s*\{([^}]*)\}/)?.[1] ?? '';
    for (const m of rootBlock.matchAll(/--ion-color-danger(-shade)?:\s*(#[0-9a-fA-F]{3,8})/g)) {
      const [, shadeSuffix, hex] = m;
      const ratio = contrastRatio(hexToRgb(hex), WHITE);
      expect(ratio, `theme override --ion-color-danger${shadeSuffix ?? ''} (${hex}) vs white`).toBeGreaterThanOrEqual(AA_FLOOR);
    }
  });
});

describe('no source file hardcodes a contrast-failing danger fallback (hub#1298)', () => {
  it('detects a bad fallback literal when one is present — proves the check itself works', () => {
    // The exact shape of the real defect this guard found: a `var(--ion-color-danger, <stale
    // hex>)` fallback whose literal fails AA. Verified against a synthetic snippet so the
    // assertion below does not depend on any single file staying broken (or fixed) over time.
    const offenders = dangerFallbackOffenders('.sample { color: var(--ion-color-danger, #eb445a); }');
    expect(offenders).toEqual([{ token: '--ion-color-danger', hex: '#eb445a', ratio: expect.closeTo(3.81, 2) }]);
  });

  it('every var(--ion-color-danger[-shade], #hex) fallback across apps/web/src passes AA', () => {
    const files = sourceFiles(SRC);
    const offenders: string[] = [];
    for (const file of files) {
      const source = readFileSync(file, 'utf8');
      for (const o of dangerFallbackOffenders(source)) {
        offenders.push(`src/${relative(SRC, file)}: var(${o.token}, ${o.hex}) — ${o.ratio.toFixed(2)}:1, needs ${AA_FLOOR}:1`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
