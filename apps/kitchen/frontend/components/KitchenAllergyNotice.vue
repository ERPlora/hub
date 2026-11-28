<script setup lang="ts">
import { formatAllergens } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import type { ItemOut } from '../operations/tickets';

const props = defineProps<{
  line: ItemOut;
  testid: string;
}>();

const t = useT();
const locale = useLocale();
const allergy = computed(() => formatAllergens(props.line.allergy, locale.value));
const contained = computed(() => formatAllergens(props.line.allergy_in_dish, locale.value));
</script>

<template>
  <div
    v-if="allergy"
    class="ep-order-ticket__allergy"
    :data-testid="testid"
  >
    <HubIcon
      class="ep-order-ticket__allergy-icon"
      name="ion:warning-outline"
      decorative
    />
    <div>
      <strong>{{ t('kitchen.card.allergyNames', { names: allergy }) }}</strong>
      <span
        v-if="contained"
        class="ep-order-ticket__allergy-contains"
        :data-testid="`${testid}-contains`"
      >{{ t('kitchen.card.contains', { names: contained }) }}</span>
    </div>
  </div>
</template>
