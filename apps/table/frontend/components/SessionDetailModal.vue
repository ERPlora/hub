<script setup lang="ts">
// «Details» of a check (WORKBOOK «Sesiones»; TABLE-F22): zone, server, status, guests, opened, closed, time,
// charged (what its check of Sales charged; «—» when nothing was), customer and notes. Hours are the
// business's; a parked check says it has no table.
import { FormModal } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { clockTime, durationMinutes, formatMoney } from '../lib/format';
import type { SessionOut, SettingsOut } from '../operations';

const props = defineProps<{ session: SessionOut | null; settings: SettingsOut; now: Date }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const NONE = '—';

const rows = computed(() => {
  const s = props.session;
  if (!s) return [];
  const zone = props.settings.timezone;
  return [
    ['zone', t('table.sessions.columns.zone'), s.zone_name || NONE],
    ['waiter', t('table.sessions.columns.waiter'), s.waiter_name || NONE],
    ['status', t('table.sessions.columns.status'), t(`table.sessionStatus.${s.status}`)],
    ['guests', t('table.sessions.columns.guests'), String(s.guests_count)],
    ['opened', t('table.sessions.columns.openedAt'), clockTime(s.opened_at, props.now, locale.value, zone)],
    ['closed', t('table.sessions.columns.closedAt'), clockTime(s.closed_at, props.now, locale.value, zone)],
    ['duration', t('table.sessions.columns.duration'), t('table.minutes', { minutes: durationMinutes(s.opened_at, s.closed_at, props.now) })],
    ['paid', t('table.sessions.columns.paid'), formatMoney(s.paid_total, locale.value)],
    ['customer', t('table.sessions.detail.customer'), s.customer_name || NONE],
    ['notes', t('table.sessions.detail.notes'), s.notes || NONE],
  ] as const;
});

const title = computed(() => {
  const s = props.session;
  const table = s?.table_number ? t('table.tableLabel', { number: s.table_number }) : t('table.sessions.noTable');
  return t('table.sessions.detail.title', { table });
});
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="table-session-detail"
    :title="title"
  >
    <dl class="table-session-detail">
      <template
        v-for="[key, label, value] in rows"
        :key="key"
      >
        <dt>{{ label }}</dt>
        <dd :data-testid="`table-session-detail-${key}`">
          {{ value }}
        </dd>
      </template>
    </dl>
    <template #footer="{ cancel }">
      <ion-button
        fill="clear"
        data-testid="table-session-detail-done"
        @click="cancel"
      >
        {{ $t('table.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.table-session-detail {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.4rem 1rem;
  margin: 0;
}
.table-session-detail dt {
  color: var(--ion-color-medium, #8b897f);
}
.table-session-detail dd {
  margin: 0;
  white-space: pre-wrap;
}
</style>
