// Pixel budget of the shell's visual contract (ERPlora/hub#1823).
//
// A module of its own, next to `bench-ports.ts` and `bench-app-version.ts`, for the reason those
// have one: `playwright.config.ts` is loaded by Playwright and by nothing else, so a number that
// only lives inside it can never be guarded. `visual-diff-budget.test.ts` runs in vitest, in
// milliseconds, with no browser and no database — and it is what keeps the budget honest.
//
// WHAT THE BUDGET IS FOR. `toHaveScreenshot` counts the pixels that differ from the baseline and
// fails when there are more than it is allowed. The allowance used to be `maxDiffPixelRatio:
// 0.002` — 0.2 % OF THE SCREEN, i.e. 2592 px at 1440x900 — sized to absorb font antialiasing.
// Two things were wrong with that, both measured on 2026-09-11:
//
//   · The noise it was absorbing is ZERO. Three consecutive runs of the whole contract (45
//     captures) with `maxDiffPixels: 0` found not one differing pixel. hub#1752 and hub#1812 had
//     already removed every moving part — frozen clock, pinned timezone, pinned app version,
//     masked install QR — and CI regenerates its baselines on the same runner image it compares
//     them on.
//   · The signal it was hiding is TEXT. A whole short label rewritten (`v0.0.0-bench` ->
//     `v1.1.7`) moved 106 px and one digit (`v1.1.7` -> `v1.1.8`) moved 33 px; both passed green.
//
// WHY ABSOLUTE AND NOT A SMALLER RATIO. The budget has to stay under the ink of a GLYPH, and a
// glyph does not grow with the viewport. A ratio makes the guard weakest where the screen is
// biggest — the same one-digit change sat 78x under budget at 1440x900 and 20x under it at
// 390x844 — so one absolute number is the only shape that holds at all three widths at once.

/**
 * Pixels a capture may differ from its baseline before the case fails.
 *
 * 20 is chosen between two MEASURED bounds, not picked for feel: the noise floor below it is 0 px
 * and the smallest real change above it is 33 px (one digit). The cushion is deliberate — a
 * budget of 0 turns a single stray pixel from a browser bump into fifteen red captures at once,
 * and a contract that cries wolf gets muted, which is the state hub#1752 existed to leave behind.
 */
export const VISUAL_DIFF_BUDGET_PX = 20;

/**
 * Differing pixels measured across three consecutive runs of the whole contract (15 captures
 * each) with `maxDiffPixels: 0`, against baselines the same machine had just written.
 *
 * Zero. Recorded as a named constant because it is the fact that licenses the budget above: if a
 * future run starts flaking, this is the number to re-measure before widening anything.
 */
export const MEASURED_NOISE_FLOOR_PX = 0;

/**
 * Differing pixels of the smallest REAL change measured on this bench: one digit of the sidebar
 * footer version at 1440px (`v1.1.7` -> `v1.1.8`), 2026-09-11.
 *
 * The budget must stay under this, or a one-character change goes green again — the defect of
 * hub#1823. The whole label rewritten (`v0.0.0-bench` -> `v1.1.7`) moved 106 px, for scale.
 */
export const SMALLEST_MEASURED_TEXT_CHANGE_PX = 33;

/**
 * The budget this file replaced, kept so the guard can keep stating, executably, why a fraction
 * of the screen cannot be the unit here (`visual-diff-budget.test.ts`).
 */
export const LEGACY_DIFF_PIXEL_RATIO = 0.002;

/**
 * What `playwright.config.ts` hands to `expect.toHaveScreenshot`.
 *
 * `animations: 'disabled'` and `caret: 'hide'` travel with the budget on purpose: they are the
 * other two things that keep a capture from moving between runs, and splitting them from the
 * number that depends on them is how one of them gets dropped later without anyone noticing.
 */
export const VISUAL_SCREENSHOT_OPTIONS = {
  maxDiffPixels: VISUAL_DIFF_BUDGET_PX,
  animations: 'disabled',
  caret: 'hide',
} as const;
