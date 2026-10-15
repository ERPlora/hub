<script setup lang="ts">
// RESERVATION-F01: «Add slot» — the Day of the week (the weekday of the day on screen first), From, To,
// Max reservations (10) and, optionally, Max guests; «Create slot». The slots of a day never overlap: the
// server says which one it overlaps, on top and under «From».
import { FormModal } from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { WEEKDAYS } from '../lib/weekdays';

const props = defineProps<{ weekday: number }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const create = useCommand('reservation.time_slot.create');
const day = ref(0);
const start = ref('');
const end = ref('');
const max = ref('10');
const maxCovers = ref('');
const failure = ref<ApiError | null>(null);

const number = (value: string): number | null => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : null);
const ready = computed(() => !!start.value && !!end.value && !!number(max.value));

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    day.value = props.weekday;
    start.value = '';
    end.value = '';
    max.value = '10';
    maxCovers.value = '';
    failure.value = null;
  },
  { immediate: true },
);

async function save(): Promise<void> {
  failure.value = null;
  try {
    await create.run({
      day_of_week: day.value,
      start_time: start.value.slice(0, 5),
      end_time: end.value.slice(0, 5),
      max_reservations: number(max.value) ?? 10,
      max_covers: number(maxCovers.value),
    });
    open.value = false;
  } catch (error) {
    failure.value = error as ApiError;
  }
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="reservation-slot-form"
    size="sm"
    :title="$t('reservation.availability.slotForm.title')"
    :submit-label="$t('reservation.availability.slotForm.submit')"
    :pending="create.pending.value"
    :error="failure"
    :submit-disabled="!ready"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="reservation-slot-form">
        <ion-select
          data-testid="reservation-slot-form-day_of_week"
          :value="day"
          :label="$t('reservation.availability.slotForm.day')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="day = Number($event.detail.value)"
        >
          <ion-select-option
            v-for="(name, index) in WEEKDAYS"
            :key="name"
            :value="index"
          >
            {{ t(`reservation.weekday.${name}`) }}
          </ion-select-option>
        </ion-select>
        <div class="reservation-slot-form__pair">
          <ion-input
            data-testid="reservation-slot-form-start_time"
            type="time"
            :value="start"
            :label="$t('reservation.availability.slotForm.from')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.start_time"
            :class="invalid(fieldErrors.start_time)"
            @ion-input="start = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-slot-form-end_time"
            type="time"
            :value="end"
            :label="$t('reservation.availability.slotForm.to')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.end_time"
            :class="invalid(fieldErrors.end_time)"
            @ion-input="end = text($event.detail.value)"
          />
        </div>
        <div class="reservation-slot-form__pair">
          <ion-input
            data-testid="reservation-slot-form-max_reservations"
            type="number"
            inputmode="numeric"
            min="1"
            :value="max"
            :label="$t('reservation.availability.slotForm.max')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.max_reservations"
            :class="invalid(fieldErrors.max_reservations)"
            @ion-input="max = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-slot-form-max_covers"
            type="number"
            inputmode="numeric"
            min="1"
            :value="maxCovers"
            :label="$t('reservation.availability.slotForm.maxCovers')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.max_covers"
            :class="invalid(fieldErrors.max_covers)"
            @ion-input="maxCovers = text($event.detail.value)"
          />
        </div>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.reservation-slot-form {
  display: grid;
  gap: 14px;
}
.reservation-slot-form__pair {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
</style>
