import { expect } from 'vitest';

import { unsavedChangesIn } from '../lib/system-back';

/** The same Android Back contract in every form window, exercised through its own controls. */
export async function expectUnsavedFormOnAndroidBack(options: {
  overlay: () => Element | null;
  change: () => Promise<void> | void;
  restore: () => Promise<void> | void;
}): Promise<void> {
  const overlay = options.overlay();
  expect(overlay).not.toBeNull();
  expect(unsavedChangesIn(overlay!)).toBeUndefined();
  await options.change();
  expect(unsavedChangesIn(overlay!)).toBeDefined();
  await options.restore();
  expect(unsavedChangesIn(overlay!)).toBeUndefined();
}
