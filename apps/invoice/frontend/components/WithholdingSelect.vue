<script setup lang="ts">
// The «IRPF withholding» of a manual invoice (INVOICE-F03): none, or one of the closed list. The tax is Spanish: a
// business abroad is not asked.
import { useLive } from '@erplora/ui/sdk';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale } from '../composables/useT';
import type { WithholdingRate } from '../invoice-withholding';
import { formatPercent } from '../lib/format';
import { HOME_COUNTRY } from '../lib/recipient';
import { WITHHOLDING_RATES } from '../lib/withholding';

defineProps<{ errorText?: string }>();
const rate = defineModel<WithholdingRate | null>({ required: true });

/** What the select holds for «No withholding». */
const NONE = 0;
const locale = useLocale();
const { data: business } = useLive('base.business.get', {});
const asked = computed(() => (business.value?.country ?? HOME_COUNTRY) === HOME_COUNTRY);
</script>

<template>
  <ion-select
    v-if="asked"
    data-testid="invoice-create-withholding"
    :label="$t('invoice.withholding.label')"
    label-placement="floating"
    fill="outline"
    mode="md"
    interface="popover"
    :value="rate ?? NONE"
    :error-text="errorText"
    :class="{ 'ion-invalid': !!errorText, 'ion-touched': !!errorText }"
    @ion-change="rate = ($event.detail.value || null) as WithholdingRate | null"
  >
    <ion-select-option :value="NONE">
      {{ $t('invoice.withholding.none') }}
    </ion-select-option>
    <ion-select-option
      v-for="option in WITHHOLDING_RATES"
      :key="option"
      :value="option"
    >
      {{ formatPercent(option, locale) }}
    </ion-select-option>
  </ion-select>
</template>
