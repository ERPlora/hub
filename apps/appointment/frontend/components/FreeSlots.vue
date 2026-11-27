<script setup lang="ts">
// The free times of the booking panel, in one tab per span the professional works that day. Live: a booking
// elsewhere takes its time away at once. The parent mounts it only once there is something to ask.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonLabel, IonSegment, IonSegmentButton, IonSkeletonText, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDayMonth, formatTime, timeOf } from '../lib/clock';
import { defaultWindow, groupByWindow, type WindowGroup } from '../lib/free-times';
import type { SlotsIn } from '../operations';
import ChoiceButton from './ChoiceButton.vue';

const props = defineProps<{
  date: string;
  serviceIds: string[];
  staffId: string;
  staffName: string;
  /** The time chosen (`HH:MM`): its button is pressed and its span open. */
  selected: string;
  /** The business's today: its shift is «today». */
  today: string;
  /** The minutes typed when they replace the services' length. */
  durationMinutes?: number | null;
  /** The appointment being moved: its own time is free. */
  excludeId?: string | null;
}>();

const emit = defineEmits<{ pick: [time: string]; off: [off: boolean] }>();

const t = useT();
const locale = useLocale();

const params = computed<SlotsIn>(() => ({
  date: props.date,
  ...(props.durationMinutes ? { duration_minutes: props.durationMinutes } : { service_ids: props.serviceIds }),
  staff_id: props.staffId,
  ...(props.excludeId ? { exclude_id: props.excludeId } : {}),
}));
const { data, status, refresh } = useLive('appointment.availability.slots', params);

const loading = computed(() => status.value === 'loading');
const groups = computed(() => groupByWindow(data.value?.windows ?? [], data.value?.slots ?? []));
/** The professional does not work that day: the server would refuse any time of it. */
const off = computed(() => !loading.value && status.value !== 'error' && !!data.value && groups.value.length === 0);
watch(off, (value) => emit('off', value), { immediate: true });

/** The tab the person opened; `null` follows the chosen time. Another day or professional starts over. */
const opened = ref<number | null>(null);
watch(() => JSON.stringify(data.value?.windows ?? []), () => (opened.value = null));
const shown = computed(() => opened.value ?? defaultWindow(groups.value, props.date, props.selected));
const shownSlots = computed(() => groups.value[shown.value]?.slots ?? []);
const marked = computed(() => shownSlots.value.some((slot) => slot.within_notice));

const clock = (moment: string): string => formatTime(timeOf(moment), locale.value);
const range = (group: WindowGroup): string => `${clock(group.start)} – ${clock(group.end)}`;
const isToday = computed(() => props.date === props.today);

const shift = computed(() => {
  const spans = new Intl.ListFormat(locale.value, { type: 'conjunction' }).format(
    groups.value.map((group) => t('appointment.slots.span', { start: clock(group.start), end: clock(group.end) })),
  );
  const named = { name: props.staffName, spans, day: formatDayMonth(props.date, locale.value) };
  return t(isToday.value ? 'appointment.slots.worksToday' : 'appointment.slots.worksOn', named);
});
const offSaid = computed(() =>
  t(isToday.value ? 'appointment.slots.offToday' : 'appointment.slots.offOn', {
    name: props.staffName,
    day: formatDayMonth(props.date, locale.value),
  }),
);

function openTab(value: unknown): void {
  opened.value = Number(value ?? 0);
}
</script>

<template>
  <div
    class="free-slots"
    data-testid="appointment-slots"
    aria-live="polite"
  >
    <div
      v-if="loading"
      class="free-slots__loading"
      aria-busy="true"
      data-testid="appointment-slots-loading"
    >
      <p class="free-slots__state">
        <ion-spinner name="dots" />{{ $t('appointment.slots.loading') }}
      </p>
      <div class="free-slots__grid">
        <ion-skeleton-text
          v-for="n in 8"
          :key="n"
          animated
          class="free-slots__skeleton"
        />
      </div>
    </div>
    <InlineFeedback
      v-else-if="status === 'error'"
      tone="warning"
      data-testid="appointment-slots-error"
    >
      {{ $t('appointment.slots.error') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          @click="refresh()"
        >
          {{ $t('appointment.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <InlineFeedback
      v-else-if="off"
      tone="neutral"
      :heading="offSaid"
      data-testid="appointment-slots-off"
    >
      {{ $t('appointment.slots.offHint') }}
    </InlineFeedback>
    <template v-else-if="data">
      <p
        class="free-slots__shift"
        data-testid="appointment-slots-shift"
      >
        {{ shift }}
      </p>
      <ion-segment
        v-if="groups.length > 1"
        class="free-slots__windows"
        data-testid="appointment-slots-windows"
        :value="String(shown)"
        :aria-label="$t('appointment.slots.windows')"
        @ion-change="openTab($event.detail.value)"
      >
        <ion-segment-button
          v-for="(group, index) in groups"
          :key="group.start"
          :value="String(index)"
          data-testid="appointment-slots-window"
        >
          <ion-label class="free-slots__window">
            <span class="free-slots__window-range">{{ range(group) }}</span>
            <small>{{ $t('appointment.slots.free', { n: group.slots.length }) }}</small>
          </ion-label>
        </ion-segment-button>
      </ion-segment>
      <InlineFeedback
        v-if="!shownSlots.length"
        tone="info"
        data-testid="appointment-slots-empty"
      >
        {{ $t('appointment.slots.empty') }}
      </InlineFeedback>
      <div
        v-else
        class="free-slots__grid"
        role="group"
        :aria-label="$t('appointment.slots.label')"
      >
        <ChoiceButton
          v-for="slot in shownSlots"
          :key="slot.start"
          :pressed="timeOf(slot.start) === selected"
          :marked="slot.within_notice"
          :title="slot.within_notice ? $t('appointment.slots.withinNotice') : undefined"
          :aria-label="slot.within_notice ? $t('appointment.slots.timeWithinNotice', { time: clock(slot.start) }) : undefined"
          data-testid="appointment-slots-time"
          @click="emit('pick', timeOf(slot.start))"
        >
          {{ clock(slot.start) }}
        </ChoiceButton>
      </div>
      <p
        v-if="marked"
        class="free-slots__legend"
        data-testid="appointment-slots-notice"
      >
        {{ $t('appointment.slots.noticeLegend') }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.free-slots {
  display: grid;
  gap: 10px;
}
.free-slots__state,
.free-slots__shift {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 0.9rem;
}
.free-slots__shift {
  display: block;
  color: var(--ion-text-color, #1d2025);
}
.free-slots__loading {
  display: grid;
  gap: 10px;
}
.free-slots__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
  gap: 8px;
}
.free-slots__skeleton {
  height: var(--ep-touch-min, 48px);
  margin: 0;
  border-radius: var(--ep-radius-sm, 10px);
}
.free-slots__window {
  display: grid;
  gap: 2px;
  padding: 6px 0;
  white-space: normal;
}
.free-slots__window-range {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.free-slots__legend {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 0.8rem;
  color: var(--ep-text-muted, #646b78);
}
.free-slots__legend::before {
  content: '';
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ep-warning-text, #7a4f00);
}
</style>
