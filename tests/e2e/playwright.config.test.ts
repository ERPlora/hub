// The Playwright config runs `global-setup.ts` before the first spec: the guard that refuses local
// databases with unapplied migrations (2026-10-16). Its unit tests prove the guard; this one proves
// Playwright calls it, which a dropped `globalSetup` line would silently undo.
import { isAbsolute, join } from 'node:path';

import { expect, it } from 'vitest';

import config from './playwright.config';

it('runs global-setup.ts before the specs', () => {
  const setup = config.globalSetup;
  expect(typeof setup).toBe('string');
  expect(isAbsolute(setup as string)).toBe(true);
  expect(setup).toMatch(new RegExp(`${join('tests', 'e2e', 'global-setup.ts')}$`));
});
