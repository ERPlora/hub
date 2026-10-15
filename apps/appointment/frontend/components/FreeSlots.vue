<script setup lang="ts">
// APPOINTMENT-F02: the «Free times» of the booking panel. With the services (or the minutes typed, which
// then decide the length), a professional and a day, the free times as buttons; a tap fills the time.
// The front desk also sees the times inside the minimum notice, marked. Live: a booking elsewhere takes
// its time away at once. The parent mounts it only once there is something to ask.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale } from '../composables/useT';
import { formatTime, timeOf } from '../lib/clock';
import type { SlotsIn } from '../operations';

const props = defineProps<{
  date: string;
  serviceIds: string[];
  staffId: string;
  /** The time chosen (`HH:MM`): its button is pressed. */
  selected: string;
  /** The minutes typed when they replace the services' length. */
  durationMinutes?: number | null;
  /** The appointment being moved: its own time is free. */
  excludeId?: string | null;
}>();

const emit = defineEmits<{ pick: [time: string] }>();

const locale = useLocale();

const params = computed<SlotsIn>(() => ({
  date: props.date,
  ...(props.durationMinutes ? { duration_minutes: props.durationMinutes } : { service_ids: props.serviceIds }),
  staff_id: props.staffId,
  ...(props.excludeId ? { exclude_id: props.excludeId } : {}),
}));
const { data, status, refresh } = useLive('appointment.availability.slots', params);
const slots = computed(() => data.value?.slots ?? []);
</script>

<template>
  <div
    class="free-slots"
    data-testid="appointment-slots"
  >
    <span class="free-slots__label">{{ $t('appointment.slots.label') }}</span>
    <div
      v-if="status === 'loading' && !data"
      class="free-slots__state"
      data-testid="appointment-slots-loading"
    >
      <ion-spinner name="dots" />{{ $t('appointment.slots.loading') }}
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
    <p
      v-else-if="!slots.length"
      class="free-slots__state"
      data-testid="appointment-slots-empty"
    >
      {{ $t('appointment.slots.empty') }}
    </p>
    <div
      v-else
      class="free-slots__times"
      role="group"
      :aria-label="$t('appointment.slots.label')"
    >
      <ion-button
        v-for="slot in slots"
        :key="slot.start"
        size="small"
        :fill="timeOf(slot.start) === selected ? 'solid' : 'outline'"
        :class="{ 'free-slots__time--notice': slot.within_notice }"
        :title="slot.within_notice ? $t('appointment.slots.withinNotice') : undefined"
        :aria-pressed="timeOf(slot.start) === selected ? 'true' : 'false'"
        data-testid="appointment-slots-time"
        @click="emit('pick', timeOf(slot.start))"
      >
        {{ formatTime(timeOf(slot.start), locale) }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.free-slots {
  display: grid;
  gap: 6px;
}
.free-slots__label {
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b7280);
}
.free-slots__times {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 160px;
  overflow-y: auto;
}
.free-slots__time--notice {
  font-style: italic;
  opacity: 0.8;
}
.free-slots__state {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 0.9rem;
}
</style>
