<script setup lang="ts">
// The order a customer is about to send from their table: each line with what goes with it, its note, one less and one
// more, and its amount; the total; «Send order». The amounts are the menu's as the page shows them: the server prices
// the order again when it arrives. One less of a line of one takes it out.
import { EmptyState, FormModal, type FormModalError, formatMoney, type Money, QuantityStepper } from '@erplora/ui/components';
import { IonItem, IonLabel, IonList, IonNote } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../../../../base/frontend/lib/i18n';
import { basketTotal, type BasketLine, MAX_QUANTITY, unitPrice } from '../lib/basket';

const props = defineProps<{
  lines: BasketLine[];
  money: Money | undefined;
  pending?: boolean;
  error?: FormModalError | null;
}>();
const open = defineModel<boolean>('open', { required: true });
defineEmits<{ quantity: [key: number, quantity: number]; send: [] }>();

const { t, locale } = useBaseI18n();
const money = (minor: number) => formatMoney(minor, locale.value, props.money);
const total = computed(() => money(basketTotal(props.lines)));

function picked(line: BasketLine): string {
  return line.picks.map((pick) => pick.name).join(', ');
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="t('online_order.order.title')"
    :submit-label="t('online_order.order.send')"
    :submit-disabled="!lines.length"
    :pending="pending"
    :error="error"
    size="md"
    testid="oo-order-sheet"
    @submit="$emit('send')"
  >
    <EmptyState
      v-if="!lines.length"
      icon="ion:cart-outline"
      :heading="t('online_order.order.empty')"
      :message="t('online_order.order.emptyMessage')"
      data-testid="oo-order-empty"
    />
    <!-- The order opens on its lines, not in a quantity field that would raise a phone's keyboard. -->
    <ion-list
      v-else
      lines="inset"
      data-autofocus
      tabindex="-1"
      data-testid="oo-order-lines"
    >
      <ion-item
        v-for="line in lines"
        :key="line.key"
        :data-testid="`oo-order-line-${line.key}`"
      >
        <ion-label class="ion-text-wrap">
          <h3>{{ line.name }}</h3>
          <p v-if="line.picks.length">
            {{ picked(line) }}
          </p>
          <p v-if="line.notes">
            {{ line.notes }}
          </p>
          <p>{{ money(unitPrice(line) * line.quantity) }}</p>
        </ion-label>
        <QuantityStepper
          :quantity="line.quantity"
          :max="MAX_QUANTITY"
          :decrease-label="line.quantity === 1 ? t('online_order.order.remove', { name: line.name }) : undefined"
          :testid="`oo-order-qty-${line.key}`"
          @change="$emit('quantity', line.key, Number($event))"
        />
      </ion-item>
      <ion-item
        lines="none"
        data-testid="oo-order-total"
      >
        <ion-label>
          <strong>{{ t('online_order.order.total') }}</strong>
        </ion-label>
        <ion-note slot="end">
          <strong>{{ total }}</strong>
        </ion-note>
      </ion-item>
    </ion-list>
  </FormModal>
</template>
