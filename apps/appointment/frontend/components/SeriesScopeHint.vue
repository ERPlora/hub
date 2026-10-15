<script setup lang="ts">
// APPOINTMENT-F14: what editing a series from a date reaches — its booked appointments from that date on,
// and how many of those are charged (an edit never touches them). Live: it follows the date picked.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDay } from '../lib/clock';

const props = defineProps<{ seriesId: string; fromDate: string }>();

const t = useT();
const locale = useLocale();
const { data } = useLive(
  'appointment.recurring.get',
  computed(() => ({ id: props.seriesId, from_date: props.fromDate })),
);
const hint = computed(() =>
  data.value
    ? t('appointment.series.form.scopeHint', {
        from: formatDay(props.fromDate, locale.value),
        upcoming: data.value.upcoming,
        charged: data.value.charged,
      })
    : '',
);
</script>

<template>
  <InlineFeedback
    v-if="hint"
    tone="info"
    data-testid="series-form-scope"
  >
    {{ hint }}
  </InlineFeedback>
</template>
