// `useCatalog()`: what an automation can start on and do in this business (`flow.catalog.read`: the
// events, actions and reads of the active apps, the app names already in the person's language). Read
// once when the screen opens, with its loading and its failure; `reload` reads it again.
import { type ApiError, useLiveClient } from '@erplora/ui/sdk';
import { ref, shallowRef } from 'vue';

import type { CatalogOut } from '../operations';

export function useCatalog() {
  const client = useLiveClient();
  const catalog = shallowRef<CatalogOut | null>(null);
  const error = shallowRef<ApiError | null>(null);
  const loading = ref(true);

  async function reload(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      catalog.value = await client.api.call('flow.catalog.read', {});
    } catch (failure) {
      error.value = failure as ApiError;
    } finally {
      loading.value = false;
    }
  }

  void reload();
  return { catalog, error, loading, reload };
}
