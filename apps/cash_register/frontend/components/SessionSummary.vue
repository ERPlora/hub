<script setup lang="ts">
// The summary of a session's detail (CASH_REGISTER-F11; the old detail's two-column list): who opened and
// closed it and when, its drawer, the float, the sales and their split by payment method, refunds, cash in
// and out, comps, expected, counted, difference and the notes. The same list the report prints.
import { formatDateTime } from '@erplora/ui/components';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { summaryItems } from '../lib/summary';
import type { SessionOut } from '../operations';

const props = defineProps<{ session: SessionOut }>();

const t = useT();
const locale = useLocale();
const items = computed(() => summaryItems(props.session, t, locale.value, (iso) => formatDateTime(iso, locale.value)));
</script>

<template>
  <dl
    class="cash-summary"
    data-testid="cash-register-summary"
  >
    <div
      v-for="item in items"
      :key="item.key"
      class="cash-summary__item"
      :data-testid="`cash-register-summary-${item.key}`"
    >
      <dt>{{ item.label }}</dt>
      <dd>{{ item.value }}</dd>
    </div>
  </dl>
</template>

<style scoped>
.cash-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.6rem 1.25rem;
  margin: 0;
}
.cash-summary__item dt {
  font-size: 0.8rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.cash-summary__item dd {
  margin: 0.1rem 0 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}
</style>
