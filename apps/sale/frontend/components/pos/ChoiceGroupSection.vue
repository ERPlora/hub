<script lang="ts">
import type { ChoiceGroup } from '../../lib/modifierChoice';

/** A group as the section paints it: each choice with the label it shows. */
export interface SectionGroup extends ChoiceGroup {
  readonly name: string;
  readonly options: readonly { readonly id: string; readonly label: string; readonly price_delta: number }[];
}
</script>

<script setup lang="ts">
// One group of a choosing sheet of the till: a group of options of Modifiers (SALE-F11, `kind="options"`) or a
// course of a menu of Menus (SALE-F12, `kind="menu"`). Its name and rule («Choose N», «Up to N», «Optional»),
// its choices with their supplement when it is not zero (with its sign), a counter and a minus where a choice
// may repeat, the warning ring while the sheet points at it and, when its ceiling refused a tap, a line saying
// it is full. A group whose choices repeat lays them one per line, the counter and the minus to the right of the
// name (as Square and Toast do): in a tile they left the name a few pixels and it broke letter by letter. The
// taps go up; the rules live in `modifierChoice`.
import { useLocale, useT } from '../../composables/useT';
import { formatMoney } from '../../lib/format';
import { type Choice, countOf, ruleOf } from '../../lib/modifierChoice';

const props = defineProps<{ kind: 'options' | 'menu'; group: SectionGroup; choice: Choice; attention: string | null }>();
const emit = defineEmits<{ tap: [optionId: string]; less: [optionId: string] }>();

const t = useT();
const locale = useLocale();

/** The hooks of each kind: the options sheet keeps the ones it had. */
const HOOKS = {
  options: { group: 'pos-options-group', rule: 'pos-options-rule', choice: 'pos-option', name: 'pos-option-name', count: 'pos-option-count', less: 'pos-option-less' },
  menu: { group: 'pos-menu-course', rule: 'pos-menu-rule', choice: 'pos-menu-dish', name: 'pos-menu-dish-name', count: 'pos-menu-dish-count', less: 'pos-menu-dish-less' },
} as const;
const hook = HOOKS[props.kind];

function supplement(cents: number): string {
  if (!cents) return '';
  return `${cents > 0 ? '+' : '−'}${formatMoney(Math.abs(cents), locale.value)}`;
}
</script>

<template>
  <section
    class="pos-options__group"
    :class="{ 'pos-options__group--missing': attention === group.id }"
    :data-testid="`${hook.group}-${group.id}`"
  >
    <header class="pos-options__head">
      <h3 class="pos-options__name">
        {{ group.name }}
      </h3>
      <span
        class="pos-options__rule"
        :data-testid="`${hook.rule}-${group.id}`"
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
    <div
      class="pos-options__list"
      :class="{ 'pos-options__list--rows': group.allow_repeat }"
    >
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
          :data-testid="`${hook.choice}-${option.id}`"
          @click="emit('tap', option.id)"
        >
          <span
            class="pos-options__label"
            :data-testid="`${hook.name}-${option.id}`"
          >{{ option.label }}</span>
          <span
            v-if="option.price_delta"
            class="pos-options__delta"
          >{{ supplement(option.price_delta) }}</span>
          <span
            v-if="group.allow_repeat && countOf(choice, option.id) > 0"
            class="pos-options__count"
            :data-testid="`${hook.count}-${option.id}`"
          >× {{ countOf(choice, option.id) }}</span>
        </button>
        <button
          v-if="group.allow_repeat && countOf(choice, option.id) > 0"
          type="button"
          class="pos-options__less"
          :aria-label="t('sale.pos.options.less', { name: option.label })"
          :data-testid="`${hook.less}-${option.id}`"
          @click="emit('less', option.id)"
        >
          −
        </button>
      </div>
    </div>
  </section>
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
.pos-options__list--rows {
  grid-template-columns: 1fr;
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
</style>
