// usePreviewReload: the preview's reload key, which goes up whenever the draft the server holds says something new.
import { describe, expect, it } from 'vitest';
import { nextTick, ref } from 'vue';

import { SITE } from '../__tests__/site';
import { toDraft } from '../lib/draft';
import type { SaveIn } from '../operations';
import { usePreviewReload } from './usePreviewReload';

function withTitle(title: string): SaveIn {
  const draft = toDraft(SITE);
  draft.content.hero.title = title;
  return draft;
}

describe('usePreviewReload', () => {
  it('keeps its first key while the first draft arrives', async () => {
    const saved = ref<SaveIn | null>(null);
    const key = usePreviewReload(saved);
    saved.value = toDraft(SITE);
    await nextTick();
    expect(key.value).toBe(1);
  });

  it('goes up each time the saved draft says something new', async () => {
    const saved = ref<SaveIn | null>(toDraft(SITE));
    const key = usePreviewReload(saved);
    saved.value = withTitle('Theirs');
    await nextTick();
    expect(key.value).toBe(2);
    saved.value = withTitle('Ours');
    await nextTick();
    expect(key.value).toBe(3);
  });

  it('stays when the draft comes back as the server keeps it: no spaces around a text, no empty address lines', async () => {
    const saved = ref<SaveIn | null>(withTitle('Fresh food '));
    const key = usePreviewReload(saved);
    const kept = withTitle('Fresh food');
    kept.content.location.address_lines = [];
    saved.value = kept;
    await nextTick();
    expect(key.value).toBe(1);
  });

  it('stays when a new photo comes back named by its file: the server writes that name on every read', async () => {
    const photo = { id: '0192f0b2-0000-7000-8000-000000000001', url: '/p/media/a/website/img/b.png' };
    const sent = toDraft(SITE);
    sent.content.gallery.images = [photo];
    const saved = ref<SaveIn | null>(sent);
    const key = usePreviewReload(saved);
    const gallery = { ...SITE.content.gallery, images: [{ ...photo, name: 'terraza.png' }] };
    saved.value = toDraft({ ...SITE, content: { ...SITE.content, gallery } });
    await nextTick();
    expect(key.value).toBe(1);
  });
});
