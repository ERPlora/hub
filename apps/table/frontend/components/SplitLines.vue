<script setup lang="ts">
// «Split check» (WORKBOOK TABLE-F17): the lines of the table's check in Sales (`sale.order.get`, live
// while open), each with a checkbox; the ones marked move to the new check, none marked = a blank one.
// The page sends `table.session.split`, which divides the check in Sales in the same operation. Each amount in the
// business's currency (an open check is not charged yet; flow table-business-currency).
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonCheckbox, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import { formatQuantity } from '../../../sale/frontend/lib/format';
import { useLocale } from '../composables/useT';
import { formatMoney, useBusinessMoney } from '../lib/format';

const props = withDefaults(defineProps<{ orderId: string; marked: string[]; pending?: boolean }>(), { pending: false });
const emit = defineEmits<{ toggle: [lineId: string]; confirm: []; back: [] }>();

const locale = useLocale();
const money = useBusinessMoney();
const { data, status, error } = useLive('sale.order.get', () => ({ order_id: props.orderId }));
const lines = computed(() => data.value?.lines ?? []);
</script>

<template>
  <div class="table-split">
    <p>{{ $t('table.split.hint') }}</p>
    <p
      v-if="status === 'loading' && !data"
      class="table-split__loading"
      data-testid="table-sheet-split-loading"
    >
      <ion-spinner name="crescent" />
      {{ $t('table.loading') }}
    </p>
    <InlineFeedback
      v-else-if="error && !data"
      tone="danger"
      data-testid="table-sheet-split-error"
    >
      {{ $t('table.split.loadError') }}
    </InlineFeedback>
    <p
      v-else-if="lines.length === 0"
      data-testid="table-sheet-split-empty"
    >
      {{ $t('table.split.empty') }}
    </p>
    <ul
      v-else
      class="table-split__lines"
    >
      <li
        v-for="line in lines"
        :key="line.id"
      >
        <ion-checkbox
          :data-testid="`table-sheet-split-line-${line.id}`"
          :checked="marked.includes(line.id)"
          label-placement="end"
          justify="start"
          @ion-change="emit('toggle', line.id)"
        >
          {{ formatQuantity(line.quantity, line.unit, locale) }} × {{ line.name }} · {{ formatMoney(line.line_total, locale, money) }}
        </ion-checkbox>
      </li>
    </ul>
    <div class="table-split__row">
      <ion-button
        fill="clear"
        data-testid="table-sheet-split-back"
        @click="emit('back')"
      >
        {{ $t('table.back') }}
      </ion-button>
      <ion-button
        data-testid="table-sheet-split-confirm"
        :disabled="pending"
        @click="emit('confirm')"
      >
        {{ $t('table.split.confirm') }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.table-split__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
.table-split__lines {
  display: grid;
  gap: 0.4rem;
  margin: 0.5rem 0;
  padding: 0;
  list-style: none;
}
.table-split__lines ion-checkbox {
  min-height: 44px;
}
.table-split__row {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}
</style>
