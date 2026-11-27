<script setup lang="ts">
// THE interval editor (SCHEDULE-F02, F04, F05), shared by the weekly day, the special day and the
// override as in the old screen: one line per interval — «Opens», «Closes» (time fields: they hold
// `HH:MM`) and «Remove interval» (44 px, never the last line) —, «+ Add interval» and the hint. The
// server judges overlaps, empty intervals and the 12-line cap: its refusal goes under the lines.
import { TimeField } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';

import type { IntervalRow } from '../lib/intervals';

defineProps<{
  /** Prefix of the hooks: `<testid>-interval-<i>`, `-open-<i>`, `-close-<i>`, `-remove-<i>`, `-add`, `-hint`, `-error`. */
  testid: string;
  /** The server's refusal of the intervals (the 422's `fields.intervals`). */
  error?: string;
}>();

const rows = defineModel<IntervalRow[]>({ required: true });

function set(index: number, field: keyof IntervalRow, value: string): void {
  rows.value = rows.value.map((row, i) => (i === index ? { ...row, [field]: value } : row));
}

function add(): void {
  rows.value = [...rows.value, { open_time: '', close_time: '' }];
}

function remove(index: number): void {
  if (rows.value.length <= 1) return;
  rows.value = rows.value.filter((_, i) => i !== index);
}
</script>

<template>
  <div class="schedule-intervals">
    <div
      v-for="(row, index) in rows"
      :key="index"
      class="schedule-intervals__line"
      :data-testid="`${testid}-interval-${index}`"
    >
      <TimeField
        class="schedule-intervals__time"
        :testid="`${testid}-open-${index}`"
        :model-value="row.open_time"
        :label="$t('schedule.intervals.open')"
        required
        @update:model-value="set(index, 'open_time', $event)"
      />
      <TimeField
        class="schedule-intervals__time"
        :testid="`${testid}-close-${index}`"
        :model-value="row.close_time"
        :label="$t('schedule.intervals.close')"
        required
        @update:model-value="set(index, 'close_time', $event)"
      />
      <ion-button
        :data-testid="`${testid}-remove-${index}`"
        class="schedule-intervals__remove"
        fill="clear"
        color="medium"
        :aria-label="$t('schedule.intervals.remove')"
        :title="$t('schedule.intervals.remove')"
        :disabled="rows.length <= 1"
        @click="remove(index)"
      >
        <HubIcon
          slot="icon-only"
          name="ion:close-outline"
        />
      </ion-button>
    </div>
    <p
      v-if="error"
      class="schedule-intervals__error"
      :data-testid="`${testid}-error`"
    >
      {{ error }}
    </p>
    <ion-button
      :data-testid="`${testid}-add`"
      class="schedule-intervals__add"
      fill="outline"
      size="small"
      @click="add"
    >
      {{ $t('schedule.intervals.add') }}
    </ion-button>
    <p
      class="schedule-intervals__hint"
      :data-testid="`${testid}-hint`"
    >
      {{ $t('schedule.intervals.hint') }}
    </p>
  </div>
</template>

<style scoped>
.schedule-intervals {
  display: grid;
  gap: 8px;
}
/* One interval per line: opens · closes · ✕, aligned at the top (a field's error grows it downwards). */
.schedule-intervals__line {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.schedule-intervals__time {
  flex: 1 1 6rem;
  min-width: 6rem;
}
.schedule-intervals__remove {
  min-width: 44px;
  min-height: 44px;
  margin-top: 6px;
}
.schedule-intervals__add {
  justify-self: start;
}
.schedule-intervals__hint {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.85rem;
}
.schedule-intervals__error {
  margin: 0;
  color: var(--ion-color-danger, #c5000f);
  font-size: 0.85rem;
}
</style>
