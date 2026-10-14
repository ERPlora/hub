// The colour of a group or a tag (CUSTOMER-F27, F28): a name of the theme («primary» by default), as
// the server stores it. The form offers the theme's colours by name; a colour stored before that is
// not one of them is kept as an option, so saving never rewrites it.
import { describe, expect, it } from 'vitest';

import { colorOptions, THEME_COLORS } from './colors';

describe('colors', () => {
  it('offers the theme colours, primary first', () => {
    expect(THEME_COLORS).toEqual(['primary', 'secondary', 'tertiary', 'success', 'warning', 'danger', 'medium', 'dark']);
  });

  it('keeps a stored colour outside the theme as one more option', () => {
    expect(colorOptions('danger')).toEqual(THEME_COLORS);
    expect(colorOptions('#ff00aa')).toEqual([...THEME_COLORS, '#ff00aa']);
    expect(colorOptions('')).toEqual(THEME_COLORS);
  });
});
