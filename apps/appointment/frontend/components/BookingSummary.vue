<script setup lang="ts">
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { addMinutes, formatShortDayMonth, formatTime } from '../lib/clock';

const props = defineProps<{
  day: string;
  /** `HH:MM`; `''` while it is missing. */
  time: string;
  minutes: number | null;
  staffName: string;
}>();

const t = useT();
const locale = useLocale();

const span = computed(() => {
  const start = formatTime(props.time, locale.value);
  if (!props.minutes) return start;
  const end = formatTime(addMinutes(props.time, props.minutes), locale.value);
  return `${start} – ${end} · ${t('appointment.form.durationValue', { n: props.minutes })}`;
});
const where = computed(
  () => `${formatShortDayMonth(props.day, locale.value)} · ${props.staffName || t('appointment.form.pickStaff')}`,
);
</script>

<template>
  <div
    v-if="time"
    class="booking-summary"
  >
    <strong
      class="booking-summary__span"
      data-testid="appointment-form-chosen-span"
    >{{ span }}</strong>
    <span
      class="booking-summary__where"
      data-testid="appointment-form-chosen-where"
    >{{ where }}</span>
  </div>
</template>

<style scoped>
.booking-summary {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.booking-summary__span {
  font-size: 1rem;
  font-variant-numeric: tabular-nums;
}
.booking-summary__where {
  overflow: hidden;
  font-size: 0.85rem;
  color: var(--ep-text-muted, #646b78);
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
