<script setup lang="ts">
// «All-Day» on the kitchen display: how much of each dish is left to cook, as the server adds it up.
import { EmptyState } from '@erplora/ui/components';

import { useLocale } from '../composables/useT';
import { formatQuantity } from '../lib/format';
import type { AllDayRowOut } from '../operations';

defineProps<{
  /** `undefined` until the server answers. */
  rows: AllDayRowOut[] | undefined;
  /** «All» (the pass): each dish says its station. */
  showStation: boolean;
}>();

const locale = useLocale();
</script>

<template>
  <p
    v-if="rows === undefined"
    class="kds-allday__loading"
    role="status"
    data-testid="kitchen-display-allday-loading"
  >
    {{ $t('kitchen.display.loading') }}
  </p>
  <table
    v-else-if="rows.length"
    class="kds-allday"
    data-testid="kitchen-display-allday"
  >
    <thead>
      <tr>
        <th>{{ $t('kitchen.display.colDish') }}</th>
        <th v-if="showStation">
          {{ $t('kitchen.display.colStation') }}
        </th>
        <th class="kds-allday__num">
          {{ $t('kitchen.display.colLeft') }}
        </th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="dish in rows"
        :key="`${dish.product_id ?? dish.name}-${dish.station_id ?? 'none'}-${dish.unit}`"
      >
        <td>{{ dish.name }}</td>
        <td v-if="showStation">
          {{ dish.station_name || $t('kitchen.display.stationNone') }}
        </td>
        <td class="kds-allday__num">
          {{ formatQuantity(dish.quantity, locale) }}
        </td>
      </tr>
    </tbody>
  </table>
  <EmptyState
    v-else
    data-testid="kitchen-display-empty"
    icon="ion:checkmark-circle-outline"
    :heading="$t('kitchen.display.emptyAllDay')"
  />
</template>

<style scoped>
.kds-allday__loading {
  color: var(--ep-text-muted);
}
.kds-allday {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  overflow: hidden;
  border: 1px solid var(--ion-border-color);
  border-radius: var(--ep-radius-lg);
  background: var(--ion-card-background, var(--ion-background-color));
  font-size: 1.2rem;
}
.kds-allday th,
.kds-allday td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--ion-border-color);
  text-align: left;
}
.kds-allday tbody tr:last-child td {
  border-bottom: none;
}
.kds-allday th {
  background: var(--ion-color-step-50);
  color: var(--ep-text-muted);
  font-size: 0.8rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.kds-allday .kds-allday__num {
  text-align: right;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
</style>
