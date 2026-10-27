<script setup lang="ts">
// The amount of a service without a fixed price (SALE-F38, SERVICE-F03: «From», «per hour», «Variable»,
// «Free»): «Amount of <service>», the amount typed on the keypad, big on top, the service's price as
// the suggestion («Use <price>», one tap types it) and «Add <amount>», which waits for an amount. It
// hands the cents up; the server keeps them within the service's minimum and maximum, and its refusal
// is read here, over the button. Opens blank.
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useLocale } from '../../composables/useT';
import { centsFromAmount, formatMoney, moneyDecimals, useBusinessMoney } from '../../lib/format';
import PosNumpad from './PosNumpad.vue';
import PosSheet from './PosSheet.vue';

const props = defineProps<{ service: ServiceSaleOut | null; pending: boolean; error: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ add: [cents: number] }>();

const locale = useLocale();
const business = useBusinessMoney();
const typed = shallowRef('');

watch(open, (isOpen) => isOpen && (typed.value = ''), { immediate: true });

const cents = computed(() => centsFromAmount(typed.value.replace(/\.$/, ''), business.value) ?? 0);
const amount = computed(() => formatMoney(cents.value, locale.value, business.value));
const suggestion = computed(() => formatMoney(props.service?.price ?? 0, locale.value, business.value));

function suggest(): void {
  const decimals = moneyDecimals(business.value);
  typed.value = ((props.service?.price ?? 0) / 10 ** decimals).toFixed(decimals);
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
      @click="suggest"
    >
      {{ $t('sale.pos.servicePriceSuggest', { price: suggestion }) }}
    </ion-button>
    <template #foot>
      <div class="pos-sheet-foot">
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
