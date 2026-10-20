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
import { formatMoney } from '../../lib/format';
import { addedCents, choose, type Choice, chosenIds, countOf, initialChoice, missingGroup, ruleOf, unchoose } from '../../lib/modifierChoice';
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
const price = computed(() => formatMoney((props.product?.price ?? 0) + addedCents(props.groups, choice.value), locale.value));

function supplement(cents: number): string {
  if (!cents) return '';
  return `${cents > 0 ? '+' : '−'}${formatMoney(Math.abs(cents), locale.value)}`;
}

function tap(group: TargetGroupOut, optionId: string): void {
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
    <section
      v-for="group in groups"
      :key="group.id"
      class="pos-options__group"
      :class="{ 'pos-options__group--missing': attention === group.id }"
      :data-testid="`pos-options-group-${group.id}`"
    >
      <header class="pos-options__head">
        <h3 class="pos-options__name">{{ group.name }}</h3>
        <span
          class="pos-options__rule"
          :data-testid="`pos-options-rule-${group.id}`"
        >
          {{ t(ruleOf(group).key, { n: ruleOf(group).n }) }}
        </span>
      </header>
      <p
        v-if="attention === group.id && choice.refused === group.id"
        class="pos-options__note"
        role="status"
      >
        {{ t('sale.pos.options.full', { group: group.name }) }}
      </p>
      <div class="pos-options__list">
        <div
          v-for="option in group.options"
          :key="option.id"
          class="pos-options__item"
        >
          <button
            type="button"
            class="pos-options__option"
            :class="{ 'pos-options__option--on': countOf(choice, option.id) > 0 }"
            :aria-pressed="countOf(choice, option.id) > 0 ? 'true' : 'false'"
            :data-testid="`pos-option-${option.id}`"
            @click="tap(group, option.id)"
          >
            <span class="pos-options__label">{{ option.name }}</span>
            <span
              v-if="option.price_delta"
              class="pos-options__delta"
            >{{ supplement(option.price_delta) }}</span>
            <span
              v-if="group.allow_repeat && countOf(choice, option.id) > 0"
              class="pos-options__count"
              :data-testid="`pos-option-count-${option.id}`"
            >× {{ countOf(choice, option.id) }}</span>
          </button>
          <button
            v-if="group.allow_repeat && countOf(choice, option.id) > 0"
            type="button"
            class="pos-options__less"
            :aria-label="t('sale.pos.options.less', { name: option.name })"
            :data-testid="`pos-option-less-${option.id}`"
            @click="less(option.id)"
          >
            −
          </button>
        </div>
      </div>
    </section>
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
.pos-options__group {
  display: grid;
  gap: 0.5rem;
  padding: 0.5rem 0.25rem 0.75rem;
  border-radius: 12px;
}
.pos-options__group + .pos-options__group {
  border-top: 1px solid var(--ep-border, rgba(0, 0, 0, 0.08));
}
.pos-options__group--missing {
  box-shadow: inset 0 0 0 2px var(--ion-color-warning, #f59e0b);
}
.pos-options__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}
.pos-options__name {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}
.pos-options__rule {
  font-size: 0.8125rem;
  color: var(--ion-color-medium, #6b7280);
  white-space: nowrap;
}
.pos-options__note {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--ion-color-warning-shade, #b45309);
}
.pos-options__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
  gap: 0.5rem;
}
.pos-options__item {
  display: flex;
  align-items: center;
  min-width: 0;
}
.pos-options__option {
  flex: 1;
  min-width: 0;
  min-height: 2.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--ep-border, rgba(0, 0, 0, 0.15));
  border-radius: 10px;
  background: var(--ion-background-color, #fff);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.pos-options__option--on {
  border-color: var(--ion-color-primary, #3880ff);
  background: rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.1);
}
.pos-options__label {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.pos-options__delta,
.pos-options__count {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  font-size: 0.875rem;
}
.pos-options__count {
  font-weight: 600;
}
.pos-options__less {
  min-width: 2.75rem;
  min-height: 2.75rem;
  margin-left: 0.25rem;
  border: 1px solid var(--ep-border, rgba(0, 0, 0, 0.15));
  border-radius: 10px;
  background: var(--ion-background-color, #fff);
  color: inherit;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
}
.pos-options__add--waiting {
  opacity: 0.75;
}
</style>
