<script setup lang="ts">
// APPOINTMENT-F10: the history of one appointment (the old «Historial de la cita» panel). Each line says
// what happened, when on the business's clock, who did it («Requested by the customer» when she asked;
// the platform when nobody did) and what changed: from which professional or service to which, the new
// time and the reason. Live: a change shows up as soon as it is saved.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { dayOf, formatDay, formatTime, timeOf } from '../lib/clock';
import type { HistoryOut } from '../operations';

const props = defineProps<{ appointmentId: string }>();

const t = useT();
const locale = useLocale();
const { data, status, refresh } = useLive(
  'appointment.appointment.history',
  computed(() => ({ id: props.appointmentId, limit: 100 })),
);
const lines = computed(() => data.value?.rows ?? []);

const when = (moment: string): string => `${formatDay(dayOf(moment), locale.value)} · ${formatTime(timeOf(moment), locale.value)}`;
const text = (value: unknown): string => (Array.isArray(value) ? value.join(', ') : String(value ?? ''));

function who(line: HistoryOut): string {
  if (line.by_customer) return t('appointment.history.byCustomer');
  return line.actor || t('appointment.history.byPlatform');
}

/** What changed, as a person reads it; empty when the action says it all. */
function change(line: HistoryOut): string {
  if (line.action === 'rescheduled' && typeof line.new_value.start === 'string') {
    return `${t('appointment.history.newTime')}: ${when(line.new_value.start)}`;
  }
  if (line.action === 'staff_changed') {
    return `${t('appointment.history.professional')}: ${text(line.old_value.staff)} → ${text(line.new_value.staff)}`;
  }
  if (line.action === 'service_changed') {
    return `${t('appointment.history.service')}: ${text(line.old_value.services)} → ${text(line.new_value.services)}`;
  }
  return '';
}
</script>

<template>
  <div
    class="appointment-history"
    data-testid="appointment-history"
  >
    <div
      v-if="status === 'loading' && !data"
      class="appointment-history__loading"
      data-testid="appointment-history-loading"
    >
      <ion-spinner name="dots" />
      {{ $t('appointment.loading') }}
    </div>
    <InlineFeedback
      v-else-if="status === 'error'"
      tone="danger"
      data-testid="appointment-history-error"
    >
      {{ $t('appointment.history.error') }}
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
    <EmptyState
      v-else-if="!lines.length"
      icon="time-outline"
      data-testid="appointment-history-empty"
      :heading="$t('appointment.history.empty')"
    />
    <ol
      v-else
      class="appointment-history__list"
    >
      <li
        v-for="line in lines"
        :key="line.id"
        class="appointment-history__entry"
        data-testid="appointment-history-entry"
      >
        <strong>{{ t(`appointment.history.action.${line.action}`) }}</strong>
        <span class="appointment-history__meta">{{ when(line.at) }} · {{ who(line) }}</span>
        <span v-if="change(line)">{{ change(line) }}</span>
        <span v-if="line.reason">{{ $t('appointment.history.reason') }}: {{ line.reason }}</span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.appointment-history__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.appointment-history__entry {
  display: grid;
  gap: 2px;
  padding-left: 10px;
  border-left: 3px solid var(--ion-color-primary, #3880ff);
}
.appointment-history__meta {
  font-size: 0.82rem;
  color: var(--ion-color-medium, #6b7280);
}
.appointment-history__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
