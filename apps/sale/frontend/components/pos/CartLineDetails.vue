<script setup lang="ts">
import { formatAllergens, InlineFeedback } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import type { OrderLineOut } from '../../operations';
import { useLocale, useT } from '../../composables/useT';
import { dishLabel } from '../../lib/comboChoice';
import AllergenRow from './AllergenRow.vue';

const props = defineProps<{ line: OrderLineOut }>();
const t = useT();
const locale = useLocale();
const allergy = computed(() => formatAllergens(props.line.allergy ?? [], locale.value));
const directMatch = computed(() => formatAllergens(props.line.allergy_in_dish ?? [], locale.value));
const menuMatches = computed(() =>
  (props.line.combo?.components ?? [])
    .filter((dish) => dish.allergy_in_dish?.length)
    .map((dish) => ({ id: dish.option_id, dish: dishLabel(dish), names: formatAllergens(dish.allergy_in_dish, locale.value) })),
);
const hasMatch = computed(() => !!directMatch.value || menuMatches.value.length > 0);
</script>

<template>
  <AllergenRow
    :codes="line.allergens ?? []"
    :testid="`pos-line-${line.id}-allergens`"
  />
  <p
    v-if="line.modifiers.length"
    class="pos-line__options"
    :data-testid="`pos-line-${line.id}-options`"
  >
    {{ line.modifiers.map((pick) => pick.name).join(', ') }}
  </p>
  <p
    v-if="line.combo?.components.length"
    class="pos-line__options"
    :data-testid="`pos-line-${line.id}-dishes`"
  >
    {{ line.combo.components.map(dishLabel).join(', ') }}
  </p>
  <AllergenRow
    v-for="dish in line.combo?.components ?? []"
    :key="dish.option_id"
    :codes="dish.allergens ?? []"
    :name="dishLabel(dish)"
    :testid="`pos-line-${line.id}-dish-allergens-${dish.product_name}`"
  />
  <InlineFeedback
    v-if="allergy"
    class="pos-line__allergy"
    :tone="hasMatch ? 'danger' : 'warning'"
    :heading="t('sale.pos.allergy', { names: allergy })"
    :data-testid="`pos-line-${line.id}-allergy`"
  >
    <p
      v-if="directMatch"
      class="pos-line__allergy-match"
      :data-testid="`pos-line-${line.id}-allergy-match`"
    >
      {{ t('sale.pos.dishContains', { names: directMatch }) }}
    </p>
    <p
      v-for="match in menuMatches"
      :key="match.id"
      class="pos-line__allergy-match"
      :data-testid="`pos-line-${line.id}-allergy-dish-match-${match.id}`"
    >
      {{ t('sale.pos.namedDishContains', match) }}
    </p>
  </InlineFeedback>
  <p
    v-if="line.notes"
    class="pos-line__note"
  >
    <HubIcon name="ion:chatbubbles-outline" />{{ line.notes }}
  </p>
</template>

<style scoped>
.pos-line__options {
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
  overflow-wrap: anywhere;
  color: var(--ion-color-medium-shade, #636469);
}
.pos-line__allergy {
  --padding: 0.35rem 0.45rem;
  --border-radius: 8px;
  margin-block-start: 0.35rem;
}
.pos-line__allergy :deep(.box) {
  min-height: 0;
  gap: 0.4rem;
}
.pos-line__allergy :deep(.icon) {
  font-size: 1rem;
}
.pos-line__allergy :deep(.heading) {
  font-size: 0.8rem;
}
.pos-line__allergy :deep(.body) {
  font-size: 0.75rem;
  line-height: 1.3;
}
.pos-line__allergy-match {
  margin: 0;
  font-weight: 600;
}
.pos-line__note {
  display: flex;
  gap: 0.25rem;
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
  overflow-wrap: anywhere;
  color: var(--ion-color-medium-shade, #636469);
}
.pos-line__note :deep(ion-icon) {
  flex: none;
  margin-top: 0.1rem;
}
</style>
