<script setup lang="ts">
// What a customer reads on opening a dish or a set menu of their table's menu: its photo, what it is, its allergens
// and price, and each group of what goes with it (a dish's options, a set menu's courses) with how many to pick.
// Only to read: ordering is not here.
import { AllergenRow, FormModal, formatMoney, InlineFeedback, type Money } from '@erplora/ui/components';
import { IonButton, IonImg, IonItem, IonLabel, IonList, IonListHeader, IonNote, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import { useBaseI18n } from '../../../../base/frontend/lib/i18n';
import { choiceRule } from '../lib/choice-rule';
import type { ChoiceOut } from '../operations';

/** A group of what goes with it: a dish's modifier group or a set menu's course. */
export interface ChoiceGroup {
  name: string;
  min_choices: number;
  max_choices: number;
  choices: ChoiceOut[];
}

export interface OpenedDish {
  name: string;
  description: string;
  price: number;
  image_url: string;
  allergens: string[];
}

const props = defineProps<{
  dish: OpenedDish;
  groups: ChoiceGroup[];
  money: Money | undefined;
  loading?: boolean;
  error?: boolean;
}>();
const open = defineModel<boolean>('open', { required: true });
defineEmits<{ retry: [] }>();

const { t, locale } = useBaseI18n();
const photo = computed(() => {
  const url = props.dish.image_url;
  return url.startsWith('/') && !url.startsWith('//') ? url : '';
});

function rule(group: ChoiceGroup): string {
  const [key, named] = choiceRule(group.min_choices, group.max_choices);
  return t(key, named);
}

function delta(minor: number): string {
  if (minor === 0) return '';
  const money = formatMoney(minor, locale.value, props.money);
  return minor > 0 ? `+${money}` : money;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="dish.name"
    readonly
    size="md"
    testid="oo-menu-sheet"
  >
    <div>
      <ion-img
        v-if="photo"
        :src="photo"
        :alt="t('online_order.menu.photo', { name: dish.name })"
      />
      <p v-if="dish.description">
        {{ dish.description }}
      </p>
      <AllergenRow :codes="dish.allergens" />
      <p>
        <strong>{{ formatMoney(dish.price, locale, money) }}</strong>
      </p>
      <p
        v-if="loading"
        role="status"
      >
        <ion-spinner name="crescent" />
        {{ t('online_order.menu.loadingOptions') }}
      </p>
      <InlineFeedback
        v-else-if="error"
        tone="danger"
        role="alert"
        data-testid="oo-menu-options-error"
      >
        {{ t('online_order.menu.optionsError') }}
        <template #actions>
          <ion-button
            fill="clear"
            data-testid="oo-menu-options-retry"
            @click="$emit('retry')"
          >
            {{ t('online_order.menu.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <ion-list
        v-for="(group, g) in groups"
        :key="`${g}-${group.name}`"
        lines="inset"
      >
        <ion-list-header>
          <ion-label>
            <h3>{{ group.name }}</h3>
            <p>{{ rule(group) }}</p>
          </ion-label>
        </ion-list-header>
        <ion-item
          v-for="(choice, c) in group.choices"
          :key="`${c}-${choice.name}`"
          :data-testid="`oo-menu-choice-${g}-${c}`"
        >
          <ion-label class="ion-text-wrap">
            {{ choice.name }}
            <AllergenRow :codes="choice.allergens" />
          </ion-label>
          <ion-note
            v-if="choice.price_delta"
            slot="end"
          >
            {{ delta(choice.price_delta) }}
          </ion-note>
        </ion-item>
      </ion-list>
    </div>
  </FormModal>
</template>

