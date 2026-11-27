// The device's colour scheme in a test, with the shell's appearance back to the business's around each test:
// `prefersDark(true)` is a device set to dark, which the «System (auto)» mode follows.
import { resetUserThemePreferences } from '@erplora/ui/shell';
import { afterEach, beforeEach, vi } from 'vitest';

export function withColourScheme(): { prefersDark: (dark: boolean) => void } {
  let dark = false;
  beforeEach(() => {
    dark = false;
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query.includes('dark') && dark,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    resetUserThemePreferences();
  });
  afterEach(() => {
    resetUserThemePreferences();
    vi.unstubAllGlobals();
  });
  return {
    prefersDark: (value) => {
      dark = value;
    },
  };
}
