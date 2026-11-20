// `@erplora/ui/shell` with its toasts as spies (a real toast would leave its timer armed past the test). The hub setup
// mocks the shell with it for every test and clears the spies before each one; a test reads them from the shell:
//
//   import { toastSuccess } from '@erplora/ui/shell';  …  expect(toastSuccess).toHaveBeenCalledWith('Saved');
import { vi } from 'vitest';

const spies = { toast: vi.fn(), toastSuccess: vi.fn(), toastError: vi.fn(), toastWarning: vi.fn(), toastInfo: vi.fn() };

export async function shellWithToastSpies(importOriginal: () => Promise<unknown>): Promise<Record<string, unknown>> {
  return { ...((await importOriginal()) as object), ...spies };
}

export function clearToastSpies(): void {
  for (const spy of Object.values(spies)) spy.mockClear();
}
