<script setup lang="ts">
// The table button of the check's bar (SALE-F19), before the customer's: an icon-only grid that opens
// «Choose table». With a table on the check it turns the primary colour and names it («Assign table:
// Table 4»). The product's filled `grid` is not a registered icon, so both states paint `grid-outline`
// and the colour tells them apart. The page mounts it only while Tables is on and the person may seat.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../../composables/useT';

const props = defineProps<{ tableNumber: string | null }>();
const emit = defineEmits<{ open: [] }>();

const t = useT();
const label = computed(() =>
  props.tableNumber
    ? t('sale.pos.table.assignedTo', { table: t('sale.pos.table.chip', { number: props.tableNumber }) })
    : t('sale.pos.table.assign'),
);
</script>

<template>
  <ion-button
    fill="clear"
    class="pos-table-trigger"
    :class="{ 'pos-table-trigger--assigned': !!tableNumber }"
    data-testid="pos-table-trigger"
    :title="label"
    :aria-label="label"
    @click="emit('open')"
  >
    <HubIcon
      slot="icon-only"
      name="ion:grid-outline"
    />
  </ion-button>
</template>

<style scoped>
.pos-table-trigger {
  width: 2.6rem;
  height: 2.6rem;
  margin: 0;
  font-size: var(--pos-hdr-icon-size, 1.75rem);
  --padding-start: 0.3rem;
  --padding-end: 0.3rem;
  --color: var(--ion-text-color, #1c1b18);
}
.pos-table-trigger--assigned {
  --color: var(--ion-color-primary, #0091ce);
}
</style>
