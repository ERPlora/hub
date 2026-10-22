// The website's palettes in the editor: the file the server paints from (apps/website/palettes.json: eight curated
// palettes, each a light and a dark set that passes WCAG AA) and the owner's two colours over the chosen one
// (`theme.custom`, null = the palette's own), whose page the server derives (apps/website/palettes.py). The editor
// shows the palettes as swatches, the two colours on show as fields, and draws the template thumbnails in them.
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

export const CURATED: Readonly<Record<PaletteId, CuratedPalette>> = RAW;
export const PALETTE_IDS: readonly PaletteId[] = Object.keys(CURATED) as PaletteId[];

/** The pages the server derives the owner's colours on start from: white, and a near-black for dark. */
const DERIVED_BG = '#ffffff';
const DERIVED_DARK = '#121417';

/** What decides the colours: the palette and the owner's pair over it (a whole theme will do; its mode does not). */
type Colouring = Pick<Theme, 'palette' | 'custom'> & Partial<Pick<Theme, 'mode'>>;

export interface ThemeColours {
  primary: string;
  accent: string;
  bg: string;
  dark: string;
}

/** A palette's own two colours, those the owner may change: its light main colour and its second colour. */
export function ownColours(palette: PaletteId): CustomColours {
  const { light, accent } = CURATED[palette];
  return { primary: light.primary, accent };
}

/** The two colours on show: the owner's when changed, the palette's own otherwise. */
export function currentColours(theme: Colouring): CustomColours {
  return theme.custom ? { ...theme.custom } : ownColours(theme.palette);
}

/** The owner's colours once `key` is `value` (`#rrggbb`), the other one kept; `null` when the pair is the palette's
 * own again (the server stores it so too). */
export function withColour(theme: Colouring, key: keyof CustomColours, value: string): CustomColours | null {
  const next = { ...currentColours(theme), [key]: value.toLowerCase() };
  const own = ownColours(theme.palette);
  return next.primary === own.primary && next.accent === own.accent ? null : next;
}

/** The colours a theme is drawn with in the editor: the main and second colour on show, and the light and dark page
 * (the palette's, or those the owner's colours are derived on). */
export function themeColours(theme: Colouring): ThemeColours {
  const { primary, accent } = currentColours(theme);
  if (theme.custom) return { primary, accent, bg: DERIVED_BG, dark: DERIVED_DARK };
  const { light, dark } = CURATED[theme.palette];
  return { primary, accent, bg: light.bg, dark: dark.bg };
}
