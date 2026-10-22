<script setup lang="ts">
// HoursEditor — the opening hours of the website's contact section, the way Google Business Profile asks for them:
// the week, Monday first; each day open or closed, and an open day with up to three intervals (opens, closes; a
// closing time earlier than the opening one runs past midnight). `v-model` is the whole week; every change emits a
// new one (lib/hours).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonInput, IonItem, IonLabel, IonNote, IonToggle } from '@ionic/vue';

import { useT } from '../composables/useT';
import { addInterval, MAX_INTERVALS, removeInterval, setOpen, setTime } from '../lib/hours';
import type { Day, DayHours, Interval } from '../operations';

const props = withDefaults(
  defineProps<{
    modelValue: DayHours[];
    disabled?: boolean;
    /** The server's refusal of these hours, if any. */
    error?: string;
  }>(),
  { disabled: false, error: undefined },
);

const emit = defineEmits<{ 'update:modelValue': [value: DayHours[]] }>();

const t = useT();

function emitWeek(week: DayHours[]): void {
  if (!props.disabled) emit('update:modelValue', week);
}

const open = (day: Day, checked: boolean) => emitWeek(setOpen(props.modelValue, day, checked));
const add = (day: Day) => emitWeek(addInterval(props.modelValue, day));
const remove = (day: Day, index: number) => emitWeek(removeInterval(props.modelValue, day, index));
const time = (day: Day, index: number, edge: keyof Interval, value: unknown) =>
  emitWeek(setTime(props.modelValue, day, index, edge, String(value ?? '')));
</script>

<template>
  <div
    class="wh"
    role="group"
    :aria-label="t('website.hours.label')"
  >
    <div
      v-for="row in modelValue"
      :key="row.day"
      class="wh-day"
      :data-testid="`website-hours-day-${row.day}`"
    >
      <ion-item lines="none">
        <ion-toggle
          :data-testid="`website-hours-open-${row.day}`"
          :checked="row.intervals.length > 0"
          :disabled="disabled"
          justify="space-between"
          @ion-change="open(row.day, $event.detail.checked)"
        >
          <ion-label>
            <strong>{{ t(`website.hours.days.${row.day}`) }}</strong>
            <ion-note
              v-if="!row.intervals.length"
              class="wh-closed"
            >
              {{ t('website.hours.closed') }}
            </ion-note>
          </ion-label>
        </ion-toggle>
      </ion-item>
      <div
        v-for="(interval, index) in row.intervals"
        :key="index"
        class="wh-interval"
      >
        <ion-input
          type="time"
          :data-testid="`website-hours-${row.day}-${index}-opens`"
          :label="t('website.hours.opens')"
          label-placement="stacked"
          :value="interval.opens"
          :disabled="disabled"
          @ion-input="time(row.day, index, 'opens', $event.detail.value)"
        />
        <ion-input
          type="time"
          :data-testid="`website-hours-${row.day}-${index}-closes`"
          :label="t('website.hours.closes')"
          label-placement="stacked"
          :value="interval.closes"
          :disabled="disabled"
          @ion-input="time(row.day, index, 'closes', $event.detail.value)"
        />
        <ion-button
          fill="clear"
          color="medium"
          :aria-label="t('website.hours.remove')"
          :data-testid="`website-hours-${row.day}-${index}-remove`"
          :disabled="disabled"
          @click="remove(row.day, index)"
        >
          <HubIcon
            slot="icon-only"
            name="ion:close-outline"
          />
        </ion-button>
      </div>
      <ion-button
        v-if="row.intervals.length && row.intervals.length < MAX_INTERVALS"
        fill="clear"
        size="small"
        :data-testid="`website-hours-add-${row.day}`"
        :disabled="disabled"
        @click="add(row.day)"
      >
        <HubIcon
          slot="start"
          name="ion:add-outline"
        />
        {{ t('website.hours.add') }}
      </ion-button>
    </div>
    <p
      v-if="error"
      class="wh-error"
      role="alert"
      data-testid="website-hours-error"
    >
      {{ error }}
    </p>
  </div>
</template>

<style scoped>
.wh {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wh-day {
  border-bottom: 1px solid var(--ion-color-step-100, #e6e6e6);
  padding-bottom: 4px;
}
.wh-closed {
  margin-inline-start: 8px;
}
.wh-interval {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  align-items: end;
  gap: 8px;
  padding: 0 16px;
}
.wh-error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
  margin: 4px 16px;
}
</style>
