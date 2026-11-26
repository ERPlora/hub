<script setup lang="ts">
// The order a customer is about to send from their table: each line with what goes with it, its note, one less and one
// more, and its amount; the total; «Send order». The amounts are the menu's as the page shows them: the server prices
// the order again when it arrives. One less of a line of one takes it out.
import { EmptyState, FormModal, type FormModalError, formatMoney, type Money } from '@erplora/ui/components';
import { IonButton, IonItem, IonLabel, IonList, IonNote } from '@ionic/vue';
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
      icon="ion:restaurant-outline"
      :heading="t('online_order.order.empty')"
      :message="t('online_order.order.emptyMessage')"
      data-testid="oo-order-empty"
    />
    <ion-list
      v-else
      lines="inset"
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
        <ion-button
          fill="clear"
          :aria-label="line.quantity === 1 ? t('online_order.order.remove', { name: line.name }) : t('online_order.order.fewer')"
          :data-testid="`oo-order-less-${line.key}`"
          @click="$emit('quantity', line.key, line.quantity - 1)"
        >
          −
        </ion-button>
        <span :data-testid="`oo-order-quantity-${line.key}`">{{ line.quantity }}</span>
        <ion-button
          fill="clear"
          :disabled="line.quantity >= MAX_QUANTITY"
          :aria-label="t('online_order.order.another')"
          :data-testid="`oo-order-more-${line.key}`"
          @click="$emit('quantity', line.key, line.quantity + 1)"
        >
          +
        </ion-button>
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
