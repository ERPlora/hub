<script setup lang="ts">
// «All-Day» on the kitchen display: how much of each dish is left to cook, as the server adds it up.
import { EmptyState } from '@erplora/ui/components';

import { useLocale } from '../composables/useT';
import { quantityWithUnit } from '../lib/format';
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
    class="ep-text-muted"
    role="status"
    data-testid="kitchen-display-allday-loading"
  >
    {{ $t('kitchen.display.loading') }}
  </p>
  <table
    v-else-if="rows.length"
    class="ep-order-board-totals"
    data-testid="kitchen-display-allday"
  >
    <thead>
      <tr>
        <th>{{ $t('kitchen.display.colDish') }}</th>
        <th v-if="showStation">
          {{ $t('kitchen.display.colStation') }}
        </th>
        <th class="ep-order-board-totals__num">
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
        <td class="ep-order-board-totals__num">
          {{ quantityWithUnit(dish.quantity, dish.unit, locale) }}
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

