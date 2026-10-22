// The website's palettes as the editor shows them: the same file the server paints from (apps/website/palettes.json),
// the eight curated ones; each one's two colours, which the owner may change (`theme.custom`, null = the palette's
// own), and what a theme looks like in the template thumbnails.
import { describe, expect, it } from 'vitest';

import RAW from '../../palettes.json';
import { CURATED, currentColours, ownColours, PALETTE_IDS, themeColours, withColour } from './palettes';

describe('palettes', () => {
  it('the curated palettes of the server’s file, in its order, and nothing else', () => {
    expect(PALETTE_IDS).toEqual(['ocean', 'forest', 'terracotta', 'slate', 'rose', 'sand', 'midnight', 'olive']);
    expect(CURATED).toBe(RAW);
  });

  it('a palette’s own two colours are its light main colour and its second colour', () => {
    expect(ownColours('rose')).toEqual({ primary: RAW.rose.light.primary, accent: RAW.rose.accent });
  });

  it('the colours on show are the owner’s when changed, the palette’s otherwise', () => {
    expect(currentColours({ palette: 'rose', custom: null, mode: 'auto' })).toEqual(ownColours('rose'));
    expect(currentColours({ palette: 'rose', custom: { primary: '#112233', accent: '#445566' }, mode: 'auto' })).toEqual({
      primary: '#112233',
      accent: '#445566',
    });
  });

  it('changing one colour keeps the other; back to the palette’s own pair there is nothing to keep', () => {
    const theme = { palette: 'forest' as const, custom: null, mode: 'auto' as const };
    expect(withColour(theme, 'primary', '#112233')).toEqual({ primary: '#112233', accent: RAW.forest.accent });
    const tweaked = { ...theme, custom: { primary: '#112233', accent: RAW.forest.accent } };
    expect(withColour(tweaked, 'accent', '#445566')).toEqual({ primary: '#112233', accent: '#445566' });
    expect(withColour(tweaked, 'primary', RAW.forest.light.primary)).toBeNull();
  });

  it('a theme is drawn with its colours on show, on the palette’s pages or on the derived ones', () => {
    expect(themeColours({ palette: 'forest', custom: null, mode: 'auto' })).toEqual({
      primary: RAW.forest.light.primary,
      accent: RAW.forest.accent,
      bg: RAW.forest.light.bg,
      dark: RAW.forest.dark.bg,
    });
    expect(themeColours({ palette: 'forest', custom: { primary: '#112233', accent: '#445566' }, mode: 'dark' })).toEqual({
      primary: '#112233',
      accent: '#445566',
      bg: '#ffffff',
      dark: '#121417',
    });
  });
});
