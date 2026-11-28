// The editor's preview shows the draft the server holds, so it reloads whenever that draft changes: after a save
// of the editor and when a save made elsewhere (the assistant, another device) comes in live. A live result that
// leaves the draft as it was (its own save coming back, a publication) does not reload it again.
import { describe, expect, it } from 'vitest';

import { ionValue, mountWebsite, settle } from '../__tests__/mount-website';
import { SITE } from '../__tests__/site';
import type { SiteOut } from '../operations';
import WebsitePage from './WebsitePage.vue';

async function setup() {
  const m = await mountWebsite(WebsitePage, { api: () => Response.json(SITE) });
  const call = await m.live();
  const show = (site: SiteOut, rev: number) => m.result(call, 'website.site.get', site, rev);
  const frame = () => m.wrapper.get('[data-testid="website-preview-frame"]').attributes('src');
  const field = (id: string) => (m.wrapper.get(`[data-testid="${id}"]`).element as HTMLElement & { value?: unknown }).value;
  await show(SITE, 1);
  return { ...m, show, frame, field };
}

const withTagline = (tagline: string): SiteOut => ({ ...SITE, content: { ...SITE.content, hero: { ...SITE.content.hero, tagline } } });

describe('WebsitePage preview', () => {
  it('reloads when a draft saved elsewhere comes in live, as the editor follows it', async () => {
    const s = await setup();
    const before = s.frame();
    await s.show(withTagline('Market cooking in the centre'), 2);
    expect(s.field('website-field-hero-tagline')).toBe('Market cooking in the centre');
    expect(s.frame()).not.toBe(before);
  });

  it('reloads once after its own save, not again when that save comes back live', async () => {
    const s = await setup();
    const before = s.frame();
    await ionValue(s.wrapper.get('[data-testid="website-field-hero-tagline"]').element, 'Since 1998 ', 'ionInput');
    await s.wrapper.get('[data-testid="website-save"]').trigger('click');
    await settle();
    const saved = s.frame();
    expect(saved).not.toBe(before);
    // The server keeps the text without the space around it.
    await s.show(withTagline('Since 1998'), 2);
    expect(s.frame()).toBe(saved);
  });

  it('stays as it is when a live result leaves the draft as it was', async () => {
    const s = await setup();
    const before = s.frame();
    await s.show({ ...SITE, published_version: 1, is_live: true }, 2);
    expect(s.frame()).toBe(before);
  });
});
