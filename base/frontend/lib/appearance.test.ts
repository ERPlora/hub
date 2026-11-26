// The person's own appearance painted on the open app, as «My profile» and the follower beside the pane paint it:
// the mode, the palette and the interface scale they chose; empty, the business's.
import { hasLocalPalette, themeMode, themePalette, themeScale } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { withColourScheme } from '../__tests__/colour-scheme';
import { paintAppearance } from './appearance';

const html = document.documentElement;
const { prefersDark } = withColourScheme();

const BUSINESS = { theme_mode: '', palette: '', ui_scale: 100 } as const;

describe('paintAppearance', () => {
  it('dark, light and system each paint at once', () => {
    paintAppearance({ ...BUSINESS, theme_mode: 'dark' });
    expect(themeMode.value).toBe('dark');
    expect(html.classList.contains('ion-palette-dark')).toBe(true);

    paintAppearance({ ...BUSINESS, theme_mode: 'light' });
    expect(themeMode.value).toBe('light');
    expect(html.classList.contains('ion-palette-dark')).toBe(false);

    prefersDark(true);
    paintAppearance({ ...BUSINESS, theme_mode: 'system' });
    expect(themeMode.value).toBe('system');
    expect(html.classList.contains('ion-palette-dark')).toBe(true);
  });

  it('a palette and an interface scale of their own are painted with the mode', () => {
    paintAppearance({ theme_mode: 'dark', palette: 'forest', ui_scale: 110 });
    expect(themePalette.value).toBe('forest');
    expect(hasLocalPalette.value).toBe(true);
    expect(themeScale.value).toBe(110);
    expect(html.classList.contains('ion-palette-dark')).toBe(true);
  });

  it('nothing of their own goes back to the business’s appearance', () => {
    paintAppearance({ theme_mode: 'dark', palette: 'forest', ui_scale: 120 });
    paintAppearance(BUSINESS);
    expect(themeMode.value).toBe('system');
    expect(hasLocalPalette.value).toBe(false);
    expect(themeScale.value).toBe(100);
    expect(html.classList.contains('ion-palette-dark')).toBe(false);
  });
});
