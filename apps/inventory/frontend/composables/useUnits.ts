// The eight units of measure with their step (WORKBOOK INVENTORY-F26): the product form's «Unit of
// measure» and the step every quantity field states. They never change (live.py does not follow
// them), so they are read once from `inventory.unit.list`, in the request's language; a failed read
// says so and `retry` reads them again.
import { ApiError, type OutputOf, useLiveClient } from '@erplora/ui/sdk';
import { onMounted, type Ref, ref, shallowRef } from 'vue';

export type Unit = OutputOf<'inventory.unit.list'>['rows'][number];

export function useUnits(): {
  units: Ref<Unit[]>;
  status: Ref<'loading' | 'ready' | 'error'>;
  error: Ref<ApiError | null>;
  retry: () => void;
  unitOf: (code: string) => Unit | undefined;
} {
  const client = useLiveClient();
  const units = ref<Unit[]>([]);
  const status = ref<'loading' | 'ready' | 'error'>('loading');
  const error = shallowRef<ApiError | null>(null);

  function retry(): void {
    status.value = 'loading';
    client.api.call('inventory.unit.list', { limit: 100 }).then(
      (page) => {
        units.value = Array.isArray(page?.rows) ? page.rows : [];
        error.value = null;
        status.value = 'ready';
      },
      (failure: unknown) => {
        error.value = failure instanceof ApiError ? failure : new ApiError(0, 'client_error', String(failure));
        status.value = 'error';
      },
    );
  }

  onMounted(retry);

  return { units, status, error, retry, unitOf: (code) => units.value.find((unit) => unit.code === code) };
}
