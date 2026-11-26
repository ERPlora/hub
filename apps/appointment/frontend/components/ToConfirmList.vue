<script setup lang="ts">
// The bookings still waiting for confirmation, of every day and soonest first (APPOINTMENT-F03): the query that counts
// them for «N to confirm» and the bell lists them too, so the figure and the rows never disagree.
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useWholeList } from '../composables/useLiveWindows';
import { useT } from '../composables/useT';
import type { AppointmentRow } from '../operations';
import AppointmentList from './AppointmentList.vue';

defineProps<{ now: Date; canDelete: boolean }>();
const emit = defineEmits<{ action: [event: { actionId: string; row: AppointmentRow }]; back: [] }>();

const t = useT();
const list = useWholeList<'appointment.appointment.list_to_confirm', AppointmentRow>(
  'appointment.appointment.list_to_confirm',
  () => ({}),
);
const error = computed(() => (list.status.value === 'error' ? t('appointment.list.loadError') : undefined));
</script>

<template>
  <InlineFeedback
    tone="info"
    data-testid="appointment-to-confirm-notice"
  >
    {{ $t('appointment.toConfirm.notice') }}
    <template #actions>
      <ion-button
        size="small"
        fill="outline"
        data-testid="appointment-to-confirm-back"
        @click="emit('back')"
      >
        {{ $t('appointment.toConfirm.back') }}
      </ion-button>
    </template>
  </InlineFeedback>
  <AppointmentList
    :rows="list.rows.value"
    :now="now"
    :can-add="false"
    :can-delete="canDelete"
    :loading="list.status.value === 'loading'"
    :error="error"
    with-day
    :empty-message="$t('appointment.toConfirm.empty')"
    @action="emit('action', $event)"
    @retry="list.refresh()"
  />
</template>
