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
});
