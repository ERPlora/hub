<script setup lang="ts">
// APPOINTMENT-F20: the «Visit history» block at the end of a customer's card in Customers (CUSTOMER-F24's
// contract: one prop, `customerId`; Customers paints it only while Appointments is on). Her ten last
// appointments, the newest first, with services, professional, status and the visit's notes (the
// internal one first: a colour formula is what the next visit needs). Live: a new booking shows up.
import { EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { dayOf, formatDay, formatTime, timeOf } from '../lib/clock';
import { STATUS_TONE } from '../lib/states';

const props = defineProps<{ customerId: string }>();

const t = useT();
const locale = useLocale();
const { data, status } = useLive(
  'appointment.appointment.list_for_customer',
  computed(() => ({ customer_id: props.customerId, limit: 10 })),
);
const visits = computed(() => data.value?.rows ?? []);
</script>

<template>
  <section
    class="visit-history"
    data-testid="appointment-visits"
  >
    <h3 class="visit-history__title">
      {{ $t('appointment.visits.title') }}
    </h3>
    <div
      v-if="status === 'loading' && !data"
      class="visit-history__state"
    >
      <ion-spinner name="dots" />{{ $t('appointment.loading') }}
    </div>
    <InlineFeedback
      v-else-if="status === 'error'"
      tone="danger"
      data-testid="appointment-visits-error"
    >
      {{ $t('appointment.visits.error') }}
    </InlineFeedback>
    <EmptyState
      v-else-if="!visits.length"
      icon="calendar-outline"
      data-testid="appointment-visits-empty"
      :heading="$t('appointment.visits.empty')"
    />
    <ul
      v-else
      class="visit-history__list"
    >
      <li
        v-for="visit in visits"
        :key="visit.id"
        class="visit-history__visit"
        data-testid="appointment-visit"
      >
        <div class="visit-history__head">
          <strong>{{ formatDay(dayOf(visit.start), locale) }} · {{ formatTime(timeOf(visit.start), locale) }}</strong>
          <StatusPill
            size="sm"
            :tone="STATUS_TONE[visit.status]"
            :label="t(`appointment.status.${visit.status}`)"
          />
        </div>
        <span>{{ visit.service_names }} · {{ visit.staff_name || $t('appointment.list.unassigned') }}</span>
        <span
          v-if="visit.internal_notes"
          class="visit-history__note"
        ><em>{{ $t('appointment.visits.internal') }}:</em> {{ visit.internal_notes }}</span>
        <span
          v-if="visit.notes"
          class="visit-history__note"
        >{{ visit.notes }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.visit-history__title {
  margin: 0 0 8px;
  font-size: 1rem;
}
.visit-history__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.visit-history__visit {
  display: grid;
  gap: 2px;
}
.visit-history__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.visit-history__note {
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b7280);
}
.visit-history__state {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
