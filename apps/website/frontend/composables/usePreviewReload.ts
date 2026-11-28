// The preview frames the draft the server holds, so it reloads whenever that draft says something new: after a save
// of the editor and when one made elsewhere (the assistant, another device) comes in live. A result that says the
// same (its own save coming back, a publication) leaves it as it is.
import { readonly, ref, type Ref, watch } from 'vue';

import { sameDraft } from '../lib/draft';
import type { SaveIn } from '../operations';

/** The preview's reload key, following `saved` (what the server holds of the draft). */
export function usePreviewReload(saved: Ref<SaveIn | null>): Readonly<Ref<number>> {
  const key = ref(1);
  watch(saved, (now, before) => {
    if (now && before && !sameDraft(now, before)) key.value += 1;
  });
  return readonly(key);
}
