// The editor's draft: what `website.site.save` takes, cut from what `website.site.get` answers, and the server's
// 422 read back onto the fields.
import { describe, expect, it } from 'vitest';

import { SITE } from '../__tests__/site';
import { errorUnder, sameDraft, toDraft, toSaveIn } from './draft';


describe('draft', () => {
  it('is the template, the theme and the content, copied (editing it never touches the live result)', () => {
    const draft = toDraft(SITE);
    expect(Object.keys(draft)).toEqual(['template', 'theme', 'content']);
    draft.content.hero.title = 'Changed';
    draft.theme.palette = 'forest';
    expect(SITE.content.hero.title).toBe('Fresh food');
    expect(SITE.theme.palette).toBe('ocean');
  });

  it('copies Vue’s readonly proxies too (a live result is one)', async () => {
    const { readonly, reactive } = await import('vue');
    const draft = toDraft(readonly(reactive(structuredClone(SITE))) as typeof SITE);
    expect(draft.content.topbar.name).toBe('Pepe');
  });

  it('pads the address to its four lines so each has its field', () => {
    expect(toDraft(SITE).content.location.address_lines).toEqual(['', '', '', '']);
    const one = { ...SITE, content: { ...SITE.content, location: { ...SITE.content.location, address_lines: ['Gran Vía 1'] } } };
    expect(toDraft(one).content.location.address_lines).toEqual(['Gran Vía 1', '', '', '']);
  });

  it('sends the address without its empty lines', () => {
    const draft = toDraft(SITE);
    draft.content.location.address_lines = ['', 'Gran Vía 1', ' ', ''];
    expect(toSaveIn(draft).content.location.address_lines).toEqual(['Gran Vía 1']);
    expect(draft.content.location.address_lines).toHaveLength(4);
  });

  it('compares two drafts by what they say, empty address lines aside', () => {
    const draft = toDraft(SITE);
    expect(sameDraft(draft, toDraft(SITE))).toBe(true);
    expect(sameDraft(draft, { ...draft, template: 'bold' })).toBe(false);
    const padded = toDraft(SITE);
    padded.content.location.address_lines = ['', '', '', ' '];
    expect(sameDraft(draft, padded)).toBe(true);
  });

  it('compares the texts as the server keeps them: without the spaces around them', () => {
    const typing = toDraft(SITE);
    typing.content.topbar.name = 'Pepe ';
    expect(sameDraft(typing, toDraft(SITE))).toBe(true);
    typing.content.topbar.name = 'Pepe B';
    expect(sameDraft(typing, toDraft(SITE))).toBe(false);
  });

  it('finds the server’s message for a field or for anything under it', () => {
    const fields = { 'content.hero.title': 'Too long.', 'content.contact.hours.0.intervals.0': 'Same times.' };
    expect(errorUnder(fields, 'content.hero.title')).toBe('Too long.');
    expect(errorUnder(fields, 'content.contact.hours')).toBe('Same times.');
    expect(errorUnder(fields, 'content.hero.tagline')).toBeUndefined();
    expect(errorUnder(undefined, 'content.hero.title')).toBeUndefined();
  });
});
