// The spies the Apps screen's tests put in place of the confirmation and of the session's refresh. `vi.mock` is
// hoisted above a test's imports, so its factory reaches this module through a dynamic import, as `toast-spies.ts`:
//
//   vi.mock('@erplora/ui/components', async (importOriginal) => (await import('<path>/apps-page-spies')).componentsWithConfirmSpy(importOriginal));
import { vi } from 'vitest';

/** What `useConfirm().confirm` answers: each test says it. */
export const confirmSpy = vi.fn();

export async function componentsWithConfirmSpy(importOriginal: () => Promise<unknown>): Promise<Record<string, unknown>> {
  return { ...((await importOriginal()) as object), useConfirm: () => ({ confirm: confirmSpy }) };
}

export async function accessWithSessionSpy(importOriginal: () => Promise<unknown>): Promise<Record<string, unknown>> {
  return { ...((await importOriginal()) as object), sessionChanged: vi.fn() };
}
