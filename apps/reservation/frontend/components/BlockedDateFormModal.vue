<script setup lang="ts">
// RESERVATION-F02: «Add blocked date» — the Date (the day on screen first), the Reason and «Whole day»
// (on); off, From and Until (both included), the old API's window that now has a screen. «Block date».
// A date already blocked at that time goes on top and under the date.
import { FormModal } from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { IonInput, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import type { BlockedDateIn } from '../operations';

const props = defineProps<{ day: string }>();
const open = defineModel<boolean>('open', { default: false });

const create = useCommand('reservation.blocked_date.create');
const date = ref('');
const reason = ref('');
const wholeDay = ref(true);
const from = ref('');
const until = ref('');
const failure = ref<ApiError | null>(null);

const ready = computed(() => !!date.value && (wholeDay.value || (!!from.value && !!until.value)));

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    date.value = props.day;
    reason.value = '';
    wholeDay.value = true;
    from.value = '';
    until.value = '';
    failure.value = null;
  },
  { immediate: true },
);

async function save(): Promise<void> {
  failure.value = null;
  const block: BlockedDateIn = { date: date.value, reason: reason.value.trim(), is_full_day: wholeDay.value };
  if (!wholeDay.value) {
    block.blocked_from = from.value.slice(0, 5);
    block.blocked_until = until.value.slice(0, 5);
  }
  try {
    await create.run(block);
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
    testid="reservation-blocked-form"
    size="sm"
    :title="$t('reservation.availability.blockedForm.title')"
    :submit-label="$t('reservation.availability.blockedForm.submit')"
    :pending="create.pending.value"
    :error="failure"
    :submit-disabled="!ready"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="reservation-blocked-form">
        <ion-input
          data-testid="reservation-blocked-form-date"
          type="date"
          :value="date"
          :label="$t('reservation.availability.blockedForm.date')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.date"
          :class="invalid(fieldErrors.date)"
          @ion-input="date = text($event.detail.value)"
        />
        <ion-input
          data-testid="reservation-blocked-form-reason"
          :value="reason"
          :label="$t('reservation.availability.blockedForm.reason')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          @ion-input="reason = text($event.detail.value)"
        />
        <ion-toggle
          data-testid="reservation-blocked-form-is_full_day"
          label-placement="end"
          justify="start"
          :checked="wholeDay"
          @ion-change="wholeDay = $event.detail.checked"
        >
          {{ $t('reservation.availability.blockedForm.wholeDay') }}
        </ion-toggle>
        <div
          v-if="!wholeDay"
          class="reservation-blocked-form__pair"
        >
          <ion-input
            data-testid="reservation-blocked-form-blocked_from"
            type="time"
            :value="from"
            :label="$t('reservation.availability.blockedForm.from')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.blocked_from"
            :class="invalid(fieldErrors.blocked_from)"
            @ion-input="from = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-blocked-form-blocked_until"
            type="time"
            :value="until"
            :label="$t('reservation.availability.blockedForm.to')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.blocked_until"
            :class="invalid(fieldErrors.blocked_until)"
            @ion-input="until = text($event.detail.value)"
          />
        </div>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.reservation-blocked-form {
  display: grid;
  gap: 14px;
}
.reservation-blocked-form__pair {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
</style>
