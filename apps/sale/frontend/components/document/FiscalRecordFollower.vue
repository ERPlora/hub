<script setup lang="ts">
// VeriFactu's record of a sale's fiscal document (VERIFACTU-F19): `verifactu.record.by_invoice`, followed live.
// Renderless: the document mounts it only while VeriFactu is on, the person may read its records and the sale has
// a fiscal document (`useLive` has no «skip»). It hands up the record (none while VeriFactu has none) or why it
// could not be read, from the first answer on. Sales does not require VeriFactu: it asks only by the operation's name.
import { type ApiError, type OutputOf, useLive } from '@erplora/ui/sdk';
import { watch } from 'vue';

export type FiscalRecord = NonNullable<OutputOf<'verifactu.record.by_invoice'>['record']>;
/** What the document knows of the record: `undefined` while it has not answered yet. */
export interface FiscalRecordState {
  record: FiscalRecord | null | undefined;
  error: ApiError | null;
}

const props = defineProps<{ invoiceId: string }>();
const emit = defineEmits<{ change: [state: FiscalRecordState] }>();

const { data, error } = useLive('verifactu.record.by_invoice', () => ({ invoice_id: props.invoiceId }));

watch(
  [data, error],
  ([found, failed]) => {
    if (found === undefined && !failed) return;
    emit('change', { record: found === undefined ? undefined : found.record, error: failed });
  },
  { immediate: true },
);
</script>

<template>
  <slot />
</template>
