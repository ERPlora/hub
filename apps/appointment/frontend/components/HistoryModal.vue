<script setup lang="ts">
// APPOINTMENT-F10: «History» of a row (or a block that can no longer move) opens «Appointment history»:
// its number and every change (AppointmentHistory). Read only: its one button closes it.
import { FormModal } from '@erplora/ui/components';

import type { AppointmentRow } from '../operations';
import AppointmentHistory from './AppointmentHistory.vue';

defineProps<{ appointment: AppointmentRow | null }>();
const open = defineModel<boolean>('open', { default: false });
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="appointment-history-modal"
    :title="$t('appointment.history.title')"
    :submit-label="$t('appointment.close')"
    @submit="open = false"
  >
    <template v-if="appointment">
      <p><strong>{{ appointment.number }}</strong></p>
      <AppointmentHistory :appointment-id="appointment.id" />
    </template>
  </FormModal>
</template>
