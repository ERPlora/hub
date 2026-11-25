<script setup lang="ts">
// The summary of a session's detail (CASH_REGISTER-F11; the old detail's two-column list): who opened and
// closed it and when, its drawer, the float, the sales and their split by payment method, refunds, cash in
// and out, comps, what another app recorded (tips, F18), expected, counted, difference and the notes. The same
// list the report prints.
import { formatDateTime } from '@erplora/ui/components';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { useBusinessMoney } from '../lib/money';
import { summaryItems } from '../lib/summary';
import type { SessionOut } from '../operations';
import FigureList from './FigureList.vue';

const props = defineProps<{ session: SessionOut }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const items = computed(() => summaryItems(props.session, t, locale.value, (iso) => formatDateTime(iso, locale.value), business.value));
</script>

<template>
  <FigureList
    :items="items"
    testid="cash-register-summary"
  />
</template>
