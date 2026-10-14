// The colour of a group or a tag (CUSTOMER-F27, F28): a name of the theme, as the server keeps it
// (`primary` by default). The product typed it in a free text box; here the form offers the theme's
// colours by name, and a colour stored before that is not one of them stays as an option.

export const THEME_COLORS = ['primary', 'secondary', 'tertiary', 'success', 'warning', 'danger', 'medium', 'dark'] as const;

export type ThemeColor = (typeof THEME_COLORS)[number];

export const isThemeColor = (value: string): value is ThemeColor => (THEME_COLORS as readonly string[]).includes(value);

/** The colours to offer when the stored one is `current`. */
export function colorOptions(current: string): string[] {
  return current && !isThemeColor(current) ? [...THEME_COLORS, current] : [...THEME_COLORS];
}
