import { applyUserThemePreferences, resetUserThemePreferences, type ThemeMode, type ThemePalette } from '@erplora/ui/shell';

import type { Preferences } from '../operations/profile';

export type Appearance = Pick<Preferences, 'theme_mode' | 'palette' | 'ui_scale'>;

/** Paints the person's own appearance on the open app; an empty mode and palette at 100 % are the business's. */
export function paintAppearance({ theme_mode, palette, ui_scale }: Appearance): void {
  if (!theme_mode && !palette && ui_scale === 100) {
    resetUserThemePreferences();
    return;
  }
  applyUserThemePreferences((theme_mode || null) as ThemeMode | null, (palette || null) as ThemePalette | null, undefined, ui_scale);
}
