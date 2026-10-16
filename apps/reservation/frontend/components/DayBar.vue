<script setup lang="ts">
// The day bar of the book (WORKBOOK «Pantallas · Reservas»; RESERVATION-F05): the three questions of the
// shift. Which day — previous · date · next, «Today» when the book is on another day, the day in words —,
// how many covers and bookings it has, and the slot to watch with what is left (`lib/states.ts nextSlot`).
// It sits outside the table, so it stays on screen when the day is empty. The figures are the live
// `reservation.availability.day` the page follows; while they load they are grey, and a failure says so.
import { IonButton, IonIcon, IonInput, IonSkeletonText } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { addDays, formatDay, formatTime } from '../lib/clock';
import { nextSlot } from '../lib/states';
import type { DayOut } from '../operations';

const props = defineProps<{
  /** The day the book is on (`YYYY-MM-DD`). */
  day: string;
  /** The business's today. */
  today: string;
  /** The business's wall clock now (`HH:MM`): on today, the slot to watch is the first not ended. */
  now: string;
  figures: DayOut | undefined;
  /** The figures could not be read (the message is the page's). */
  failed: string | null;
}>();
const emit = defineEmits<{ 'update:day': [day: string] }>();

const t = useT();
const locale = useLocale();

const next = computed(() => (props.figures ? nextSlot(props.figures, props.day === props.today, props.now) : null));
const range = computed(() =>
  next.value && 'slot' in next.value
    ? `${formatTime(next.value.slot.start_time, locale.value)}–${formatTime(next.value.slot.end_time, locale.value)}`
    : '—',
);
const nextText = computed(() => {
  const state = next.value;
  if (!state) return '';
  if (state.state === 'open') return t('reservation.day.left', { count: state.slot.available });
  if (state.state === 'full') return t('reservation.day.full');
  return t({ over: 'reservation.day.over', 'no-service': 'reservation.day.noService', closed: 'reservation.day.closed' }[state.state]);
});

function go(day: string): void {
  if (/^\d{4}-\d{2}-\d{2}$/.test(day) && day !== props.day) emit('update:day', day);
}
</script>

<template>
  <div
    class="reservation-day"
    data-testid="reservation-day"
    :data-day="day"
  >
    <div class="reservation-day__nav">
      <ion-button
        class="reservation-day__step"
        fill="clear"
        data-testid="reservation-day-prev"
        :aria-label="$t('reservation.day.previous')"
        @click="go(addDays(day, -1))"
      >
        <ion-icon
          slot="icon-only"
          name="chevron-back-outline"
          aria-hidden="true"
        />
      </ion-button>
      <ion-input
        class="reservation-day__input"
        data-testid="reservation-day-input"
        type="date"
        :value="day"
        :aria-label="$t('reservation.day.date')"
        fill="outline"
        mode="md"
        @ion-change="go(String($event.detail.value ?? ''))"
      />
      <ion-button
        class="reservation-day__step"
        fill="clear"
        data-testid="reservation-day-next"
        :aria-label="$t('reservation.day.next')"
        @click="go(addDays(day, 1))"
      >
        <ion-icon
          slot="icon-only"
          name="chevron-forward-outline"
          aria-hidden="true"
        />
      </ion-button>
      <ion-button
        v-if="day !== today"
        size="small"
        fill="clear"
        data-testid="reservation-day-today"
        @click="go(today)"
      >
        {{ $t('reservation.day.today') }}
      </ion-button>
    </div>
    <p
      class="reservation-day__name"
      data-testid="reservation-day-name"
    >
      {{ formatDay(day, locale) }}
    </p>
    <div class="reservation-day__figures">
      <p
        v-if="failed"
        class="reservation-day__error"
        data-testid="reservation-day-error"
      >
        {{ $t('reservation.day.figuresError') }}
      </p>
      <ion-skeleton-text
        v-else-if="!figures"
        animated
        class="reservation-day__skeleton"
        data-testid="reservation-day-loading"
      />
      <template v-else>
        <div
          class="reservation-day__figure"
          data-testid="reservation-day-covers"
          :data-value="figures.covers"
        >
          <strong>{{ figures.covers }}</strong> <span>{{ $t('reservation.day.covers') }}</span>
        </div>
        <div
          class="reservation-day__figure"
          data-testid="reservation-day-bookings"
          :data-value="figures.reservations"
        >
          <strong>{{ figures.reservations }}</strong> <span>{{ $t('reservation.day.bookings') }}</span>
        </div>
        <div
          class="reservation-day__figure"
          data-testid="reservation-day-next-slot"
          :data-state="next?.state"
        >
          <strong>{{ range }}</strong>
          <span :class="{ 'reservation-day__full': next?.state === 'full' }">{{ nextText }}</span>
          <span>{{ $t('reservation.day.nextSlot') }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.reservation-day {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 20px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--ion-color-step-150, #e0e0e0);
}
.reservation-day__nav {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
}
.reservation-day__step {
  width: 44px;
  height: 44px;
  margin: 0;
  --padding-start: 4px;
  --padding-end: 4px;
}
.reservation-day__input {
  min-width: 8.5rem;
  max-width: 11rem;
}
.reservation-day__name {
  margin: 0;
  font-weight: 600;
}
.reservation-day__figures {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px 24px;
}
.reservation-day__figure {
  display: flex;
  flex-direction: column;
  min-width: 4.5rem;
}
.reservation-day__figure strong {
  font-size: 1.35rem;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.reservation-day__figure span {
  font-size: 0.8rem;
  color: var(--ion-color-medium, #92949c);
}
.reservation-day__figure .reservation-day__full {
  color: var(--ion-color-danger, #eb445a);
  font-weight: 600;
}
.reservation-day__skeleton {
  width: 9rem;
  height: 1.35rem;
}
.reservation-day__error {
  margin: 0;
  color: var(--ion-color-danger, #eb445a);
  font-weight: 600;
}
@media (max-width: 575px) {
  .reservation-day {
    padding: 6px 8px;
  }
  .reservation-day__step {
    width: 40px;
  }
  .reservation-day__figures {
    gap: 6px 16px;
  }
}
</style>
