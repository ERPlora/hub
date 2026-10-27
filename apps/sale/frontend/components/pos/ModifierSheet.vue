<script setup lang="ts">
// The options sheet of the till (SALE-F11; Modifiers' MODIFIER-F06): the product's name; each group with its
// rule («Choose N», «Up to N», «Optional») and its options with their supplement when it is not zero (with its
// sign); the defaults already chosen; a counter where an option may repeat. «Add · <price>» previews the price
// (the server values the line); while a required group is short it says «Choose an option to continue» and a
// tap marks that group instead of adding. A tap at a full group's ceiling is answered, naming the group. The
// ids go up in the order they were chosen; the server's refusal is read over the button.
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import type { ProductOut } from '../../../../inventory/frontend/operations';
import type { TargetGroupOut } from '../../../../modifier/frontend/operations';
import { useLocale, useT } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';
import { addedCents, choose, type Choice, chosenIds, initialChoice, missingGroup, unchoose } from '../../lib/modifierChoice';
import ChoiceGroupSection, { type SectionGroup } from './ChoiceGroupSection.vue';
import PosSheet from './PosSheet.vue';

const props = defineProps<{
  product: Pick<ProductOut, 'id' | 'name' | 'price'> | null;
  groups: readonly TargetGroupOut[];
  pending: boolean;
  error: string | null;
}>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ add: [optionIds: string[]] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();

const choice = shallowRef<Choice>(initialChoice(props.groups));
const attention = shallowRef<string | null>(null);

watch(
  () => [open.value, props.groups] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    choice.value = initialChoice(props.groups);
    attention.value = null;
  },
  { immediate: true },
);

const missing = computed(() => missingGroup(props.groups, choice.value));
const price = computed(() => formatMoney((props.product?.price ?? 0) + addedCents(props.groups, choice.value), locale.value, business.value));

const sections = computed<SectionGroup[]>(() =>
  props.groups.map((group) => ({ ...group, options: group.options.map((option) => ({ ...option, label: option.name })) })),
);

function tap(group: SectionGroup, optionId: string): void {
  choice.value = choose(choice.value, group, optionId);
  attention.value = choice.value.refused;
}

function less(optionId: string): void {
  choice.value = unchoose(choice.value, optionId);
  attention.value = null;
}

function add(): void {
  if (missing.value) {
    attention.value = missing.value.id;
    return;
  }
  emit('add', chosenIds(choice.value));
}
</script>

<template>
  <PosSheet
    v-model:open="open"
    wide
    :title="product?.name ?? ''"
    testid="pos-options"
  >
    <ChoiceGroupSection
      v-for="group in sections"
      :key="group.id"
      kind="options"
      :group="group"
      :choice="choice"
      :attention="attention"
      @tap="tap(group, $event)"
      @less="less"
    />
    <template #foot>
      <div class="pos-sheet-foot">
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-options-error"
        >
          {{ error }}
        </p>
        <ion-button
          expand="block"
          class="pos-sheet-confirm"
          :class="{ 'pos-options__add--waiting': !!missing }"
          :aria-disabled="missing ? 'true' : undefined"
          :disabled="pending"
          data-testid="pos-options-add"
          @click="add"
        >
          {{ missing ? t('sale.pos.options.chooseToContinue') : t('sale.pos.options.add', { price }) }}
        </ion-button>
      </div>
    </template>
  </PosSheet>
</template>

<style scoped>
.pos-options__add--waiting {
  opacity: 0.75;
}
</style>
