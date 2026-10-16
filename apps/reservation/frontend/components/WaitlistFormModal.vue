<script setup lang="ts">
// RESERVATION-F14: «Add guest» puts somebody on the waitlist — the Customer (Customers' own search) or the
// guest's Name and, if given, Phone (the server links the card with that phone, or makes one), the Date
// (the day the list is on), the preferred Time, the Party and notes. No contact is required (market, duda
// 7). A refusal goes on top, a bad field under it, and what was typed stays.
import { FormModal } from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { IonInput, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import CustomerSearch, { type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { hhmm } from '../lib/clock';
import type { WaitlistOut } from '../operations';

const props = defineProps<{ day: string }>();
const emit = defineEmits<{ saved: [entry: WaitlistOut] }>();
const open = defineModel<boolean>('open', { default: false });

const create = useCommand('reservation.waitlist.create');
const customer = ref<CustomerSnapshot | null>(null);
const name = ref('');
const phone = ref('');
const date = ref('');
const time = ref('');
const party = ref('2');
const notes = ref('');
const failure = ref<ApiError | null>(null);

const partySize = computed(() => (/^\d+$/.test(party.value.trim()) ? Number(party.value.trim()) : null));
const ready = computed(() => (!!customer.value || !!name.value.trim()) && !!date.value && !!time.value && !!partySize.value);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    customer.value = null;
    name.value = '';
    phone.value = '';
    date.value = props.day;
    time.value = '';
    party.value = '2';
    notes.value = '';
    failure.value = null;
  },
  { immediate: true },
);

watch(customer, (picked) => {
  if (picked) name.value = picked.customer_name;
});

async function save(): Promise<void> {
  failure.value = null;
  try {
    const saved = await create.run({
      ...(customer.value ? { customer_id: customer.value.customer_id } : {}),
      guest_name: name.value.trim(),
      guest_phone: phone.value.trim(),
      date: date.value,
      preferred_time: hhmm(time.value),
      party_size: partySize.value ?? 0,
      notes: notes.value,
    });
    emit('saved', saved);
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
    testid="reservation-waitlist-form"
    :title="$t('reservation.waitlist.form.title')"
    :submit-label="$t('reservation.waitlist.form.submit')"
    :pending="create.pending.value"
    :error="failure"
    :submit-disabled="!ready"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="reservation-waitlist-form">
        <div class="reservation-waitlist-form__customer">
          <span class="reservation-waitlist-form__label">{{ $t('reservation.form.customer') }}</span>
          <CustomerSearch v-model="customer" />
        </div>
        <ion-input
          data-testid="reservation-waitlist-form-guest_name"
          :value="name"
          :label="$t('reservation.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.guest_name"
          :class="invalid(fieldErrors.guest_name)"
          @ion-input="name = text($event.detail.value)"
        />
        <ion-input
          data-testid="reservation-waitlist-form-guest_phone"
          type="tel"
          :value="phone"
          :label="$t('reservation.form.phone')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="60"
          :error-text="fieldErrors.guest_phone"
          :class="invalid(fieldErrors.guest_phone)"
          @ion-input="phone = text($event.detail.value)"
        />
        <div class="reservation-waitlist-form__when">
          <ion-input
            data-testid="reservation-waitlist-form-date"
            type="date"
            :value="date"
            :label="$t('reservation.form.date')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.date"
            :class="invalid(fieldErrors.date)"
            @ion-input="date = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-waitlist-form-preferred_time"
            type="time"
            :value="time"
            :label="$t('reservation.form.time')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.preferred_time"
            :class="invalid(fieldErrors.preferred_time)"
            @ion-input="time = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-waitlist-form-party_size"
            type="number"
            inputmode="numeric"
            min="1"
            :value="party"
            :label="$t('reservation.form.party')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.party_size"
            :class="invalid(fieldErrors.party_size)"
            @ion-input="party = text($event.detail.value)"
          />
        </div>
        <ion-textarea
          data-testid="reservation-waitlist-form-notes"
          :value="notes"
          :label="$t('reservation.form.notes')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :maxlength="2000"
          @ion-input="notes = text($event.detail.value)"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.reservation-waitlist-form {
  display: grid;
  gap: 14px;
}
.reservation-waitlist-form__customer {
  display: grid;
  gap: 6px;
}
.reservation-waitlist-form__label {
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8b897f);
}
.reservation-waitlist-form__when {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 0.7fr);
  gap: 12px;
}
</style>
