<script setup lang="ts">
// STAFF-G02, G03, G04: the old Home panels «Active staff», «On leave today» and «Pending time off»
// (STAFF-F20, F23) above the staff list, as Customers shows its figures above its own, while the Hub's
// Home has no panels. Followed live from `staff.member.stats`: a write anywhere re-runs it on the server.
// The cards are the product's `ok-kpi` (label over a big value), as `CustomerStats.vue` rebuilds them
// until `@erplora/ui` has a KPI card (UI-REQUESTS.md).
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

const { data, status } = useLive('staff.member.stats', {});

const loading = computed(() => data.value === undefined);

const figures = computed(() => {
  const stats = data.value;
  const text = (value: number | undefined) => (value === undefined ? '…' : String(value));
  return [
    { id: 'active', label: 'staff.figures.active', raw: stats?.active, text: text(stats?.active) },
    { id: 'away', label: 'staff.figures.away', raw: stats?.absent_today, text: text(stats?.absent_today) },
    { id: 'pending', label: 'staff.figures.pending', raw: stats?.pending_time_off, text: text(stats?.pending_time_off) },
  ];
});
</script>

<template>
  <div
    class="staff-figures"
    data-testid="staff-figures"
    role="group"
    :aria-label="$t('staff.figures.label')"
    :aria-busy="loading ? 'true' : 'false'"
  >
    <p
      v-if="status === 'error' && !data"
      class="staff-figures__error"
      data-testid="staff-figures-error"
      role="alert"
    >
      {{ $t('staff.figures.loadError') }}
    </p>
    <template v-else>
      <div
        v-for="figure in figures"
        :key="figure.id"
        class="staff-figure"
        :data-testid="`staff-figures-${figure.id}`"
        :data-value="figure.raw"
      >
        <p class="staff-figure__label">
          {{ $t(figure.label) }}
        </p>
        <p class="staff-figure__value">
          {{ figure.text }}
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.staff-figures {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
  gap: 0.5rem;
  margin: 0 0 1rem;
}

/* The product's `ok-kpi`: a card with the label (muted, uppercase) over the value (big, bold). */
.staff-figure {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 1rem 1.125rem;
  background: var(--ep-card-background, var(--ion-card-background, var(--ion-background-color, #fff)));
  color: var(--ion-text-color, #1f2933);
  border: 1px solid var(--ep-border-color, var(--ion-border-color, rgba(0, 0, 0, 0.08)));
  border-radius: var(--ep-radius, 12px);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
}

.staff-figure__label {
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ep-medium, var(--ion-color-medium, #92949c));
}

.staff-figure__value {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.1;
}

.staff-figures__error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
