<script setup lang="ts">
// The menu sheet of the till (SALE-F12; Menus' COMBO-F07): the menu's name and every course at once, each with its
// rule and its dishes (the supplement with its sign when it is not zero). Nothing is picked to begin with. While a
// required course is short the button says which and how many («Choose 1 in «Mains»») and a tap rings that course
// instead of adding (never the native `disabled`: a touchscreen would swallow the tap and nobody would learn why);
// once each one is complete it says «Add · <total>», the closed price plus the supplements (a preview: Menus prices
// the line on the server). The dishes go up, each once with how many times; the server's refusal is read over the
// button.
import { type AllergenCode, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import type { SaleComboOut } from '../../../../combo/frontend/operations';
import { useLocale, useT } from '../../composables/useT';
import { comboChoices, comboShort, comboTotal } from '../../lib/comboChoice';
import { formatMoney, useBusinessMoney } from '../../lib/format';
import { refusal } from '../../lib/refusal';
import { choose, type Choice, initialChoice, unchoose } from '../../lib/modifierChoice';
import type { ComboChoiceIn } from '../../operations';
import ChoiceGroupSection, { type SectionGroup } from './ChoiceGroupSection.vue';
import PosSheet from './PosSheet.vue';

const props = defineProps<{ combo: SaleComboOut | null; pending: boolean; error: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ add: [choices: ComboChoiceIn[]] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();

const groups = computed(() => props.combo?.groups ?? []);
const choice = shallowRef<Choice>(initialChoice([]));
const attention = shallowRef<string | null>(null);
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
const short = computed(() => comboShort(groups.value, choice.value));
const total = computed(() => (props.combo ? formatMoney(comboTotal(props.combo, choice.value), locale.value, business.value) : ''));

function tap(group: SectionGroup, optionId: string): void {
  choice.value = choose(choice.value, group, optionId);
  attention.value = choice.value.refused;
}

function less(optionId: string): void {
  choice.value = unchoose(choice.value, optionId);
  attention.value = null;
}

function add(): void {
  if (short.value) {
    attention.value = short.value.group.id;
    return;
  }
  emit('add', comboChoices(choice.value));
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
    <ChoiceGroupSection
      v-for="group in sections"
      :key="group.id"
      kind="menu"
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
          data-testid="pos-menu-error"
        >
          {{ error }}
        </p>
        <ion-button
          expand="block"
          class="pos-sheet-confirm"
          :class="{ 'pos-menu__add--waiting': !!short }"
          :aria-disabled="short ? 'true' : undefined"
          :disabled="pending"
          data-testid="pos-menu-add"
          @click="add"
        >
          {{
            short
              ? t('sale.pos.menu.chooseIn', { n: short.n, course: short.group.name })
              : t('sale.pos.options.add', { price: total })
          }}
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
