// What a live list of Printing says when it cannot be read: `blocked`, the whole page (the app is off, or the person
// may not see it), or `tableError`, the table's own error with «Retry» for any other failure.
import type { UseLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

export function useListBlock(
  list: Pick<UseLive<unknown>, 'status' | 'error'>,
  loadError: () => string,
): { blocked: ComputedRef<'app_inactive' | 'permission_denied' | null>; tableError: ComputedRef<string | undefined> } {
  const blocked = computed(() => {
    const code = list.error.value?.code;
    return code === 'app_inactive' || code === 'permission_denied' ? code : null;
  });
  const tableError = computed(() => (list.status.value === 'error' && !blocked.value ? loadError() : undefined));
  return { blocked, tableError };
}
