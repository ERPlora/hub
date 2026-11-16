<script setup lang="ts">
// The amount of a service without a fixed price (SALE-F38, SERVICE-F03: «From», «per hour», «Variable»,
// «Free»): «Amount of <service>», the amount typed on the keypad, big on top, the service's price as
// the suggestion («Use <price>», one tap types it) and «Add <amount>», which waits for an amount. Both wait in
// grey for the business's money (hub#921: the amount is read and the price typed in it, never before it answers; if
// that read fails it says so with «Retry», hub#938). It hands the cents up; the server keeps them within the service's
// minimum and maximum, and its refusal is read here, over the button. Opens blank.
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import BusinessMoneyError from '../../../../../base/frontend/components/BusinessMoneyError.vue';
import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useKeypadAmount } from '../../composables/pos/useKeypadAmount';
import { useLocale } from '../../composables/useT';
import { formatMoney, moneyDecimals } from '../../lib/format';
import PosNumpad from './PosNumpad.vue';
import PosSheet from './PosSheet.vue';

const props = defineProps<{ service: ServiceSaleOut | null; pending: boolean; error: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ add: [cents: number] }>();

const locale = useLocale();
const typed = shallowRef('');
/** «Add» hands up `cents`, 0 until the business answers its money (so it waits in grey); `amount` is the figure. */
const { business, cents, shown: amount } = useKeypadAmount(typed);

watch(open, (isOpen) => isOpen && (typed.value = ''), { immediate: true });

const suggestion = computed(() => formatMoney(props.service?.price ?? 0, locale.value, business.value));

/** Types the service's price, in the business's money's decimals: not before it answers («15.00» for 1500 yen would
 *  not be an amount in yen once it does). */
function suggest(): void {
  const money = business.value;
  if (!money) return;
  typed.value = ((props.service?.price ?? 0) / 10 ** money.decimals).toFixed(money.decimals);
}

function add(): void {
  if (cents.value > 0) emit('add', cents.value);
}
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="$t('sale.pos.servicePriceTitle', { name: service?.name ?? '' })"
    testid="pos-service-price"
  >
    <template #top>
      <p
        class="pos-sheet-figure"
        data-testid="pos-service-price-amount"
      >
        {{ amount }}
      </p>
    </template>
    <PosNumpad
      v-model="typed"
      :decimals="moneyDecimals(business)"
    />
    <ion-button
      v-if="service && service.price > 0"
      fill="outline"
      expand="block"
      data-testid="pos-service-price-suggest"
      :disabled="!business"
      @click="suggest"
    >
      {{ $t('sale.pos.servicePriceSuggest', { price: suggestion }) }}
    </ion-button>
    <template #foot>
      <div class="pos-sheet-foot">
        <BusinessMoneyError />
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-service-price-error"
        >
          {{ error }}
        </p>
        <ion-button
          expand="block"
          class="pos-sheet-confirm"
          data-testid="pos-service-price-add"
          :disabled="cents <= 0 || pending"
          @click="add"
        >
          {{ $t('sale.pos.addAmount', { amount }) }}
        </ion-button>
      </div>
    </template>
  </PosSheet>
</template>
