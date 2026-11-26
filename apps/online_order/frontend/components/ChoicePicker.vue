<script setup lang="ts">
// One group of what goes with a dish (a modifier group) or a set menu (a course), as a customer picks it on their
// table's page: its name and how many to pick, and each choice with its allergens and what it adds. A choice that may
// be repeated has one-less and one-more buttons with its count; the others are a checkbox, and once a group with a
// ceiling above one is full its unchecked choices wait. The rules of a tap are the till's (`modifierChoice` of Sales).
import { AllergenRow, formatMoney, type Money } from '@erplora/ui/components';
import { IonButton, IonCheckbox, IonItem, IonLabel, IonList, IonListHeader, IonNote } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../../../../base/frontend/lib/i18n';
import { type Choice, countOf } from '../../../sale/frontend/lib/modifierChoice';
import { choiceRule } from '../lib/choice-rule';
import type { ChoiceOut } from '../operations';

/** A dish's modifier group or a set menu's course, with its choices. */
export interface PickGroup {
  id: string;
  name: string;
  min_choices: number;
  max_choices: number;
  allow_repeat: boolean;
  options: ChoiceOut[];
}

const props = defineProps<{ group: PickGroup; choice: Choice; money: Money | undefined }>();
defineEmits<{ tap: [optionId: string]; less: [optionId: string] }>();

const { t, locale } = useBaseI18n();
const rule = computed(() => {
  const [key, named] = choiceRule(props.group.min_choices, props.group.max_choices);
  return t(key, named);
});
const picked = computed(() => props.group.options.reduce((sum, option) => sum + countOf(props.choice, option.id), 0));
/** A ceiling above one reached: a group of one swaps its choice instead. */
const full = computed(() => props.group.max_choices > 1 && picked.value >= props.group.max_choices);

function delta(minor: number): string {
  if (minor === 0) return '';
  const money = formatMoney(minor, locale.value, props.money);
  return minor > 0 ? `+${money}` : money;
}
</script>

<template>
  <ion-list
    lines="inset"
    :data-testid="`oo-pick-group-${group.id}`"
  >
    <ion-list-header>
      <ion-label>
        <h3>{{ group.name }}</h3>
        <p>{{ rule }}</p>
      </ion-label>
    </ion-list-header>
    <ion-item
      v-for="option in group.options"
      :key="option.id"
      :data-testid="`oo-pick-${option.id}`"
    >
      <ion-checkbox
        v-if="!group.allow_repeat"
        :checked="countOf(choice, option.id) > 0"
        :disabled="full && countOf(choice, option.id) === 0"
        justify="start"
        label-placement="end"
        :data-testid="`oo-pick-check-${option.id}`"
        @ion-change="$emit('tap', option.id)"
      >
        <span class="ion-text-wrap">{{ option.name }}</span>
        <AllergenRow :codes="option.allergens" />
      </ion-checkbox>
      <template v-else>
        <ion-label class="ion-text-wrap">
          {{ option.name }}
          <AllergenRow :codes="option.allergens" />
        </ion-label>
        <ion-button
          fill="clear"
          :disabled="countOf(choice, option.id) === 0"
          :aria-label="t('online_order.order.less', { name: option.name })"
          :data-testid="`oo-pick-less-${option.id}`"
          @click="$emit('less', option.id)"
        >
          −
        </ion-button>
        <span :data-testid="`oo-pick-count-${option.id}`">{{ countOf(choice, option.id) }}</span>
        <ion-button
          fill="clear"
          :disabled="full"
          :aria-label="t('online_order.order.more', { name: option.name })"
          :data-testid="`oo-pick-more-${option.id}`"
          @click="$emit('tap', option.id)"
        >
          +
        </ion-button>
      </template>
      <ion-note
        v-if="option.price_delta"
        slot="end"
      >
        {{ delta(option.price_delta) }}
      </ion-note>
    </ion-item>
  </ion-list>
</template>
