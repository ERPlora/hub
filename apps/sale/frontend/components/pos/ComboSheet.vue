<script setup lang="ts">
// The menu sheet of the till (SALE-F12; Menus' COMBO-F07): the menu's name and every course at once, each with its
// rule and its dishes (the supplement with its sign when it is not zero). Nothing is picked to begin with. While a
// required course is short the button says which and how many («Choose 1 in «Mains»») and a tap rings that course
// instead of adding (never the native `disabled`: a touchscreen would swallow the tap and nobody would learn why);
// once each one is complete it says «Add · <total>», the closed price plus the supplements (a preview: Menus prices
// the line on the server). The dishes go up, each once with how many times; the server's refusal is read over the
// button. With Modifiers (`options`), a dish picked asks its groups right under its course (SALE-F42): the button names
// a group still short as it names a course, the total adds the options, and each dish goes up with their ids.
import { type AllergenCode, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import type { SaleComboOut } from '../../../../combo/frontend/operations';
import { useLocale, useT } from '../../composables/useT';
import { useDishGroups } from '../../composables/pos/useDishGroups';
import {
  comboChoices,
  comboShort,
  comboTotal,
  dishChoice,
  type DishChoices,
  type DishOptions,
  dishesCents,
  dishShort,
  type PickedDish,
  pickedDishes,
  withDishOptions,
} from '../../lib/comboChoice';
import { formatMoney, useBusinessMoney } from '../../lib/format';
import { refusal } from '../../lib/refusal';
import { choose, type Choice, initialChoice, unchoose } from '../../lib/modifierChoice';
import type { ComboChoiceIn } from '../../operations';
import ChoiceGroupSection, { type SectionGroup } from './ChoiceGroupSection.vue';
import ComboDishOptions from './ComboDishOptions.vue';
import PosSheet from './PosSheet.vue';

const props = defineProps<{ combo: SaleComboOut | null; pending: boolean; error: string | null; options?: boolean }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ add: [choices: ComboChoiceIn[]] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();

const groups = computed(() => props.combo?.groups ?? []);
const choice = shallowRef<Choice>(initialChoice([]));
const attention = shallowRef<string | null>(null);
const dishGroups = useDishGroups();
const dishChoices = shallowRef<DishChoices>({});
/** The dish the sheet points at, and its group short (`true`: the whole dish, its options unread). */
const dishAttention = shallowRef<{ dish: string; group: string | true } | null>(null);
const productDetail = useCommand('inventory.product.get');
const dishAllergens = shallowRef<Record<string, readonly AllergenCode[]>>({});
const allergensStatus = shallowRef<'idle' | 'loading' | 'ready' | 'error'>('idle');
let allergenRequest = 0;

async function loadAllergens(): Promise<void> {
  const combo = props.combo;
  if (!open.value || !combo) return;
  const request = ++allergenRequest;
  allergensStatus.value = 'loading';
  const ids = [...new Set(combo.groups.flatMap((group) => group.options.map((option) => option.product_id)))];
  try {
    const products = await Promise.all(ids.map((id) => productDetail.run({ id })));
    if (request !== allergenRequest) return;
    dishAllergens.value = Object.fromEntries(products.map((product) => [product.id, product.allergens]));
    allergensStatus.value = 'ready';
  } catch (error) {
    if (request !== allergenRequest) return;
    const code = refusal(error, '')?.code;
    allergensStatus.value = code && ['app_inactive', 'permission_denied'].includes(code) ? 'ready' : 'error';
  }
}

watch(
  () => [open.value, props.combo] as const,
  ([isOpen]) => {
    allergenRequest += 1;
    dishAllergens.value = {};
    allergensStatus.value = 'idle';
    if (!isOpen) return;
    choice.value = initialChoice([]);
    attention.value = null;
    dishChoices.value = {};
    dishAttention.value = null;
    dishGroups.reset();
    void loadAllergens();
  },
  { immediate: true },
);

const sections = computed<SectionGroup[]>(() =>
  groups.value.map((group) => ({
    ...group,
    options: group.options.map((option) => ({ ...option, label: option.product_name, allergens: dishAllergens.value[option.product_id] ?? [] })),
  })),
);
const dishes = computed(() => (props.options ? pickedDishes(groups.value, choice.value) : []));
const groupsOf = (productId: string) => {
  const read = dishGroups.of(productId);
  return read?.state === 'ready' ? read.groups : null;
};
const dishOptions = computed<DishOptions>(() => ({ groupsOf, choices: dishChoices.value }));

// A dish taken out (or swapped in a course of one) loses its options: picked again, it starts over.
watch(dishes, (picked) => {
  dishGroups.want(picked.map((dish) => dish.product_id));
  const kept = new Set(picked.map((dish) => dish.id));
  dishChoices.value = Object.fromEntries(Object.entries(dishChoices.value).filter(([id]) => kept.has(id)));
});

const short = computed(() => comboShort(groups.value, choice.value));
const dishMissing = computed(() => (short.value ? null : dishShort(dishes.value, dishOptions.value)));
const unread = computed(() => dishes.value.find((dish) => !groupsOf(dish.product_id)) ?? null);
const waiting = computed(() => !!short.value || !!dishMissing.value || !!unread.value);
const total = computed(() =>
  props.combo
    ? formatMoney(comboTotal(props.combo, choice.value) + dishesCents(dishes.value, dishOptions.value), locale.value, business.value)
    : '',
);
const label = computed(() => {
  const missing = short.value ?? dishMissing.value;
  if (!missing) return t('sale.pos.options.add', { price: total.value });
  return t('sale.pos.menu.chooseIn', { n: missing.n, course: missing.group.name });
});

function tap(group: SectionGroup, optionId: string): void {
  choice.value = choose(choice.value, group, optionId);
  attention.value = choice.value.refused;
}

function less(optionId: string): void {
  choice.value = unchoose(choice.value, optionId);
  attention.value = null;
}

function tapOption(dish: PickedDish, group: SectionGroup, optionId: string): void {
  const next = choose(dishChoice(dish, dishOptions.value), group, optionId);
  dishChoices.value = { ...dishChoices.value, [dish.id]: next };
  dishAttention.value = next.refused ? { dish: dish.id, group: next.refused } : null;
}

function lessOption(dish: PickedDish, optionId: string): void {
  dishChoices.value = { ...dishChoices.value, [dish.id]: unchoose(dishChoice(dish, dishOptions.value), optionId) };
  dishAttention.value = null;
}

function dishPointer(dish: PickedDish): string | boolean {
  const pointer = dishAttention.value;
  return pointer?.dish === dish.id ? pointer.group : false;
}

function add(): void {
  if (short.value) {
    attention.value = short.value.group.id;
    return;
  }
  if (dishMissing.value) {
    dishAttention.value = { dish: dishMissing.value.dish.id, group: dishMissing.value.group.id };
    return;
  }
  if (unread.value) {
    dishAttention.value = { dish: unread.value.id, group: true };
    return;
  }
  emit('add', withDishOptions(comboChoices(choice.value), dishes.value, dishOptions.value));
}
</script>

<template>
  <PosSheet
    v-model:open="open"
    wide
    :title="combo?.name ?? ''"
    testid="pos-menu"
  >
    <p
      v-if="allergensStatus === 'loading'"
      class="pos-sheet-hint"
      role="status"
      data-testid="pos-menu-allergens-loading"
    >
      <IonSpinner name="dots" /> {{ t('sale.pos.allergensLoading') }}
    </p>
    <InlineFeedback
      v-else-if="allergensStatus === 'error'"
      tone="danger"
      data-testid="pos-menu-allergens-error"
    >
      {{ t('sale.pos.allergensLoadFailed') }}
      <template #actions>
        <IonButton
          fill="outline"
          data-testid="pos-menu-allergens-retry"
          @click="loadAllergens"
        >
          {{ t('sale.live.retry') }}
        </IonButton>
      </template>
    </InlineFeedback>
    <template
      v-for="group in sections"
      :key="group.id"
    >
      <ChoiceGroupSection
        kind="menu"
        :group="group"
        :choice="choice"
        :attention="attention"
        @tap="tap(group, $event)"
        @less="less"
      />
      <ComboDishOptions
        v-for="dish in dishes.filter((one) => one.course === group.id && dishGroups.of(one.product_id))"
        :key="dish.id"
        :dish="dish"
        :groups="dishGroups.of(dish.product_id)!"
        :choice="dishChoice(dish, dishOptions)"
        :attention="dishPointer(dish)"
        @tap="(section, optionId) => tapOption(dish, section, optionId)"
        @less="lessOption(dish, $event)"
        @retry="dishGroups.retry(dish.product_id)"
      />
    </template>
    <template #foot>
      <div class="pos-sheet-foot">
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-menu-error"
        >
          {{ error }}
        </p>
        <ion-button
          expand="block"
          class="pos-sheet-confirm"
          :class="{ 'pos-menu__add--waiting': waiting }"
          :aria-disabled="waiting ? 'true' : undefined"
          :disabled="pending"
          data-testid="pos-menu-add"
          @click="add"
        >
          {{ label }}
        </ion-button>
      </div>
    </template>
  </PosSheet>
</template>

<style scoped>
.pos-menu__add--waiting {
  opacity: 0.75;
}
</style>
