<script setup lang="ts">
// The agenda's bar (WORKBOOK «Agenda»): the day (‹ date › and «Today», and the calendar to jump to a date;
// in a week, the week), «Filter by status», «N to confirm» when customers' bookings wait (a tap filters the
// pending ones), the «List · By professional · Repeating» switch (icons only on a phone) and, for the
// first two, «Day · Week». A device on another zone than the business is told the agenda shows the
// business's clock. One or two rows, as the old agenda (appointments#93, #206, #243): on a phone, ‹ the day's
// field › and «Today», then the filter and the switches; the long date only where it fits.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonInput, IonLabel, IonSegment, IonSegmentButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { addDays, deviceZoneDiffers, formatDay, weekStart } from '../lib/clock';
import type { AppointmentStatus } from '../operations';

export type AgendaView = 'list' | 'staff' | 'series';
export type AgendaSpan = 'day' | 'week';

const STATUSES: readonly AppointmentStatus[] = ['pending', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show'];
const VIEWS: ReadonlyArray<{ id: AgendaView; icon: string }> = [
  { id: 'list', icon: 'ion:list-outline' },
  { id: 'staff', icon: 'ion:people-outline' },
  { id: 'series', icon: 'ion:sync-outline' },
];

const props = defineProps<{
  toConfirm: number;
  /** Today on the business's clock. */
  today: string;
  /** The business's time zone. */
  zone: string;
}>();

const day = defineModel<string>('day', { required: true });
const view = defineModel<AgendaView>('view', { required: true });
const span = defineModel<AgendaSpan>('span', { required: true });
const status = defineModel<string>('status', { required: true });

const t = useT();
const locale = useLocale();

const step = computed(() => (span.value === 'week' ? 7 : 1));
const label = computed(() =>
  span.value === 'week'
    ? t('appointment.toolbar.week', { date: formatDay(weekStart(day.value), locale.value) })
    : formatDay(day.value, locale.value),
);
const otherZone = computed(() => deviceZoneDiffers(props.zone));

function jump(value: unknown): void {
  const text = String(value ?? '');
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) day.value = text;
}
</script>

<template>
  <div
    class="agenda-toolbar"
    data-testid="appointment-toolbar"
  >
    <div
      v-if="view !== 'series'"
      class="agenda-toolbar__day"
    >
      <ion-button
        fill="clear"
        class="agenda-toolbar__prev"
        data-testid="appointment-toolbar-prev"
        :aria-label="span === 'week' ? $t('appointment.toolbar.prevWeek') : $t('appointment.toolbar.prevDay')"
        @click="day = addDays(day, -step)"
      >
        <HubIcon
          slot="icon-only"
          name="ion:chevron-back-outline"
        />
      </ion-button>
      <strong
        class="agenda-toolbar__date"
        data-testid="appointment-toolbar-date"
      >{{ label }}</strong>
      <ion-button
        fill="clear"
        class="agenda-toolbar__next"
        data-testid="appointment-toolbar-next"
        :aria-label="span === 'week' ? $t('appointment.toolbar.nextWeek') : $t('appointment.toolbar.nextDay')"
        @click="day = addDays(day, step)"
      >
        <HubIcon
          slot="icon-only"
          name="ion:chevron-forward-outline"
        />
      </ion-button>
      <ion-button
        fill="outline"
        size="small"
        class="agenda-toolbar__today"
        data-testid="appointment-toolbar-today"
        @click="day = today"
      >
        {{ $t('appointment.toolbar.today') }}
      </ion-button>
      <ion-input
        class="agenda-toolbar__calendar"
        data-testid="appointment-toolbar-calendar"
        type="date"
        :value="day"
        :aria-label="$t('appointment.toolbar.openCalendar')"
        fill="outline"
        mode="md"
        @ion-change="jump($event.detail.value)"
      />
    </div>
    <div class="agenda-toolbar__controls">
      <ion-button
        v-if="toConfirm > 0"
        size="small"
        color="warning"
        data-testid="appointment-toolbar-to-confirm"
        @click="status = 'pending'"
      >
        {{ t('appointment.toolbar.toConfirm', { n: toConfirm }) }}
      </ion-button>
      <ion-select
        v-if="view !== 'series'"
        data-testid="appointment-toolbar-status"
        class="agenda-toolbar__status"
        :value="status"
        :label="$t('appointment.toolbar.filterStatus')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @ion-change="status = String($event.detail.value ?? '')"
      >
        <ion-select-option value="">
          {{ $t('appointment.toolbar.allStatuses') }}
        </ion-select-option>
        <ion-select-option
          v-for="option in STATUSES"
          :key="option"
          :value="option"
        >
          {{ t(`appointment.status.${option}`) }}
        </ion-select-option>
      </ion-select>
      <ion-segment
        v-if="view !== 'series'"
        data-testid="appointment-toolbar-span"
        :value="span"
        :aria-label="$t('appointment.views.label')"
        @ion-change="span = ($event.detail.value as AgendaSpan) ?? 'day'"
      >
        <ion-segment-button
          value="day"
          data-testid="appointment-toolbar-span-day"
        >
          <ion-label>{{ $t('appointment.views.day') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button
          value="week"
          data-testid="appointment-toolbar-span-week"
        >
          <ion-label>{{ $t('appointment.views.week') }}</ion-label>
        </ion-segment-button>
      </ion-segment>
      <ion-segment
        data-testid="appointment-toolbar-view"
        :value="view"
        :aria-label="$t('appointment.views.label')"
        @ion-change="view = ($event.detail.value as AgendaView) ?? 'list'"
      >
        <ion-segment-button
          v-for="option in VIEWS"
          :key="option.id"
          :value="option.id"
          :data-testid="`appointment-toolbar-view-${option.id}`"
          :aria-label="t(`appointment.views.${option.id}`)"
        >
          <HubIcon :name="option.icon" />
          <ion-label class="agenda-toolbar__view-label">
            {{ t(`appointment.views.${option.id}`) }}
          </ion-label>
        </ion-segment-button>
      </ion-segment>
    </div>
    <p
      v-if="otherZone"
      class="agenda-toolbar__zone"
      data-testid="appointment-toolbar-zone"
    >
      {{ t('appointment.toolbar.deviceZone', { zone }) }}
    </p>
  </div>
</template>

<style scoped>
.agenda-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  margin-bottom: 12px;
}
.agenda-toolbar__day,
.agenda-toolbar__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.agenda-toolbar__date {
  min-width: 12rem;
  text-align: center;
}
.agenda-toolbar__calendar {
  flex: 0 0 10.5rem;
  width: 10.5rem;
}
.agenda-toolbar__status {
  flex: 0 0 13rem;
  width: 13rem;
}
.agenda-toolbar ion-segment {
  width: auto;
}
.agenda-toolbar__zone {
  flex-basis: 100%;
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-warning-shade, #8a6d00);
}
@media (max-width: 640px) {
  .agenda-toolbar {
    gap: 6px;
  }
  .agenda-toolbar__view-label {
    display: none;
  }
  /* The day's field says the day: the long date would take a row of its own. */
  .agenda-toolbar__date {
    display: none;
  }
  /* ‹ the day's field ›, then «Today», as the old agenda. */
  .agenda-toolbar__prev {
    order: 1;
  }
  .agenda-toolbar__calendar {
    order: 2;
  }
  .agenda-toolbar__next {
    order: 3;
  }
  .agenda-toolbar__today {
    order: 4;
  }
  .agenda-toolbar__status {
    flex: 1 1 9rem;
    width: auto;
    min-width: 0;
  }
}
</style>
