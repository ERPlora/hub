// The website's palettes in the editor: the file the server paints from (apps/website/palettes.json: eight curated
// palettes, each a light and a dark set that passes WCAG AA) and `custom`, the owner's two colours, whose page the
// server derives (apps/website/palettes.py). The editor shows them as swatches and draws the template thumbnails in
// the chosen one's colours.
import RAW from '../../palettes.json';
import type { CustomColours, PaletteId, Theme } from '../operations';

export interface ModeColours {
  primary: string;
  bg: string;
  surface: string;
  text: string;
  link: string;
  border: string;
}

export interface CuratedPalette {
  accent: string;
  light: ModeColours;
  dark: ModeColours;
}

export type CuratedId = Exclude<PaletteId, 'custom'>;

export const CURATED: Readonly<Record<CuratedId, CuratedPalette>> = RAW;
export const PALETTE_IDS: readonly PaletteId[] = [...(Object.keys(CURATED) as CuratedId[]), 'custom'];

/** The page a custom palette starts from before the server derives it: white, and a near-black for dark. */
const CUSTOM_BG = '#ffffff';
const CUSTOM_DARK = '#121417';

export interface ThemeColours {
  primary: string;
  accent: string;
  bg: string;
  dark: string;
}

/** The colours a theme is drawn with in the editor: the main and second colour, the light and the dark page. */
export function themeColours(theme: Theme): ThemeColours {
  if (theme.palette === 'custom' && theme.custom) {
    return { primary: theme.custom.primary, accent: theme.custom.accent, bg: CUSTOM_BG, dark: CUSTOM_DARK };
  }
  const palette = CURATED[theme.palette === 'custom' ? 'ocean' : theme.palette];
  return { primary: palette.light.primary, accent: palette.accent, bg: palette.light.bg, dark: palette.dark.bg };
}

/** The colours «Your colours» opens with: those chosen before, or the palette on show. */
export function startingCustom(theme: Theme): CustomColours {
  if (theme.custom) return { ...theme.custom };
  const { primary, accent } = themeColours(theme);
  return { primary, accent };
}
