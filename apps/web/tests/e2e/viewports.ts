// The three widths of the project's UI contract: desktop, tablet and phone.
//
// Its own module (and not a const inside `shell-visual-helpers.ts`) because two very different
// runners need it: Playwright, which takes the screenshots, and vitest, which guards that the
// baselines for those screenshots are actually in the repo
// (`tests/visual-baselines-present.test.ts`, hub#1752). Importing the helpers from vitest would
// drag `@playwright/test` into a suite that has no browser and no reason to load it.
export const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 834, height: 1112 },
  { width: 390, height: 844 },
] as const;
