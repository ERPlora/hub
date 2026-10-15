<script setup lang="ts">
// The table of the check on screen (SALE-F19): Tables' `table.session.by_order`, followed live. Renderless:
// the page mounts it only while Tables is on, the person may see the table checks and there is a check
// (`useLive` has no «skip»). It hands up the check's seat — its open table check with a table, or none —
// and its parked table check (TABLE-F13: the table taken away), which «Choose table» seats again instead
// of opening another. Sales does not require Tables: it talks to it only through the operation's name.
import { type OutputOf, useLive } from '@erplora/ui/sdk';
import { watch } from 'vue';

type TableCheck = OutputOf<'table.session.by_order'>['rows'][number];

const props = defineProps<{ orderId: string }>();
const emit = defineEmits<{ seat: [check: TableCheck | null]; parked: [check: TableCheck | null] }>();

const { data } = useLive('table.session.by_order', () => ({ order_id: props.orderId }));

watch(
  data,
  (found) => {
    if (!found) return;
    emit('seat', found.rows.find((row) => row.status === 'open' && row.table_id) ?? null);
    emit('parked', found.rows.find((row) => row.status === 'parked') ?? null);
  },
  { immediate: true },
);
</script>

<template>
  <slot />
</template>
