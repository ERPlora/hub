<script setup lang="ts">
// What a customer reads on opening a dish or a set menu of their table's menu, and how they add it to their order: its
// photo, what it is, its allergens and price, each group of what goes with it (a dish's options, a set menu's courses)
// to pick from, how many and a note for the kitchen. «Add» waits until each group has what it asks; its price is the
// menu's as the page shows it, and the server prices the order again.
import { AllergenRow, FormModal, formatMoney, InlineFeedback, type Money } from '@erplora/ui/components';
import { IonButton, IonImg, IonInput, IonItem, IonLabel, IonSpinner } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useBaseI18n } from '../../../../base/frontend/lib/i18n';
import { ownImageUrl } from '../../../../base/frontend/lib/own-image';
import { addedCents, type Choice, choose, missingGroup, unchoose } from '../../../sale/frontend/lib/modifierChoice';
import { type BasketPick, MAX_QUANTITY } from '../lib/basket';
import ChoicePicker, { type PickGroup } from './ChoicePicker.vue';

export interface OpenedDish {
  name: string;
  description: string;
  price: number;
  image_url: string;
  allergens: string[];
}

/** What the customer adds: what they picked, how many and their note. */
export interface Added {
  picks: BasketPick[];
  quantity: number;
  notes: string;
}

const props = defineProps<{
  dish: OpenedDish;
  groups: PickGroup[];
  money: Money | undefined;
  loading?: boolean;
  error?: boolean;
}>();
const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ retry: []; add: [added: Added] }>();

const { t, locale } = useBaseI18n();
const photo = computed(() => ownImageUrl(props.dish.image_url));

const choice = ref<Choice>({ picks: [], refused: null });
const quantity = ref(1);
const notes = ref('');
watch(open, (opened) => {
  if (!opened) return;
  choice.value = { picks: [], refused: null };
  quantity.value = 1;
  notes.value = '';
});

const ready = computed(() => !props.loading && !props.error && !missingGroup(props.groups, choice.value));
const price = computed(() => (props.dish.price + addedCents(props.groups, choice.value)) * quantity.value);

function add(): void {
  const byId = new Map(props.groups.flatMap((group) => group.options.map((option) => [option.id, option] as const)));
  const picks = choice.value.picks.map((id) => ({ id, name: byId.get(id)!.name, price_delta: byId.get(id)!.price_delta }));
  emit('add', { picks, quantity: quantity.value, notes: notes.value.trim() });
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="dish.name"
    :submit-label="t('online_order.order.add', { price: formatMoney(price, locale, money) })"
    :submit-disabled="!ready"
    size="md"
    testid="oo-menu-sheet"
    @submit="add"
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
      <ChoicePicker
        v-for="group in groups"
        :key="group.id"
        :group="group"
        :choice="choice"
        :money="money"
        @tap="(id) => (choice = choose(choice, group, id))"
        @less="(id) => (choice = unchoose(choice, id))"
      />
      <ion-item lines="none">
        <ion-label>{{ t('online_order.order.quantity') }}</ion-label>
        <ion-button
          fill="clear"
          :disabled="quantity <= 1"
          :aria-label="t('online_order.order.fewer')"
          data-testid="oo-dish-fewer"
          @click="quantity -= 1"
        >
          −
        </ion-button>
        <span data-testid="oo-dish-quantity">{{ quantity }}</span>
        <ion-button
          fill="clear"
          :disabled="quantity >= MAX_QUANTITY"
          :aria-label="t('online_order.order.another')"
          data-testid="oo-dish-another"
          @click="quantity += 1"
        >
          +
        </ion-button>
      </ion-item>
      <ion-item lines="none">
        <ion-input
          :label="t('online_order.order.note')"
          label-placement="stacked"
          :maxlength="200"
          :value="notes"
          data-testid="oo-dish-note"
          @ion-input="notes = String($event.detail.value ?? '')"
        />
      </ion-item>
    </div>
  </FormModal>
</template>
