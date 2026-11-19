<script setup lang="ts">
import { formatAllergens } from '@erplora/ui/components';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';

const props = defineProps<{ codes: readonly string[]; name?: string; testid?: string }>();
const t = useT();
const locale = useLocale();
const names = computed(() => formatAllergens(props.codes, locale.value));
</script>

<template>
  <span
    v-if="names"
    class="allergen-row"
    :data-testid="testid"
  ><span v-if="name">{{ name }} · </span>{{ t('sale.pos.allergens', { names }) }}</span>
</template>

<style scoped>
.allergen-row {
  display: block;
  margin-block-start: 0.2rem;
  font-size: 0.75rem;
  line-height: 1.4;
  overflow-wrap: anywhere;
  color: var(--ion-color-medium-shade, #636469);
}
</style>
