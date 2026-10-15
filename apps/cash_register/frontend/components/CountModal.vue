<script setup lang="ts">
// «Cash count · S-…» (CASH_REGISTER-F06; the old dashboard's count panel): «Count type» («Closing» at the
// end of the shift, or «Opening» to check the float), «Notes», one box per note («Bills») and coin
// («Coins») of the business's currency, labelled as money, and «Total counted» adding up as it is typed —
// the server adds them up again with the currency's decimals. Without a table for the currency, the total
// is typed by hand. A count closes nothing: a closing one tells the page (`counted`), which opens the close.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { countTotal, pieces } from '../lib/count';
import { formatMoney, moneyRefusal, readMoney } from '../lib/money';
import { refusal } from '../lib/refusal';
import type { CountType } from '../operations';
import MoneyField from './MoneyField.vue';

const props = defineProps<{ session: { id: string; number: string } | null }>();

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ counted: [count: { type: CountType; total: number }] }>();

const t = useT();
const locale = useLocale();
const currency = useLive('cash_register.currency.get', {});
const command = useCommand('cash_register.count.add');

const type = shallowRef<CountType>('closing');
const notes = shallowRef('');
const boxes = ref<Record<string, string>>({});
const typedTotal = shallowRef('');

watch(
  open,
  (now) => {
    if (!now) return;
    type.value = 'closing';
    notes.value = '';
    boxes.value = {};
    typedTotal.value = '';
    command.error.value = null;
  },
  { immediate: true },
);

const table = computed(() => currency.data.value);
const hasTable = computed(() => !!table.value && table.value.bills.length + table.value.coins.length > 0);
const decimals = computed(() => table.value?.decimals ?? 2);

/** What each note or coin reads as: money of the business («50,00 €»). */
const faceLabel = (face: string): string => formatMoney(Math.round(Number(face) * 10 ** decimals.value), locale.value, table.value?.currency);

const typedRead = computed(() => readMoney(typedTotal.value, decimals.value));
const typedError = computed(() => moneyRefusal(typedRead.value, t, locale.value, table.value?.currency));

/** The total counted, in minor units; `null` while a typed total is not an amount yet. */
const total = computed<number | null>(() => {
  if (hasTable.value) return countTotal(boxes.value, decimals.value);
  return typedRead.value.ok ? typedRead.value.cents : null;
});

function counted(kind: 'bills' | 'coins'): Record<string, number> {
  const out: Record<string, number> = {};
  for (const face of table.value?.[kind] ?? []) {
    const n = pieces(boxes.value[face]);
    if (n > 0) out[face] = n;
  }
  return out;
}

const error = computed<FormModalError | null>(() => refusal(command.error.value, t('cash_register.count.failed')));

async function confirm(): Promise<void> {
  const session = props.session;
  if (!session || !table.value || total.value === null) return;
  const sent = total.value;
  const kind = type.value;
  try {
    await command.run({
      session_id: session.id,
      type: kind,
      ...(hasTable.value ? { denominations: { bills: counted('bills'), coins: counted('coins') } } : { total: sent }),
      notes: notes.value.trim(),
    });
  } catch {
    return; // The window shows `command.error`.
  }
  void toastSuccess(t('cash_register.count.done', { total: formatMoney(sent, locale.value, table.value?.currency) }));
  open.value = false;
  emit('counted', { type: kind, total: sent });
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="cash-register-count"
    :title="$t('cash_register.count.title', { number: session?.number ?? '' })"
    :submit-label="$t('cash_register.count.submit')"
    :cancel-label="$t('cash_register.count.cancel')"
    :pending="command.pending.value"
    :submit-disabled="!table || total === null"
    :error="error"
    @submit="confirm"
  >
    <div class="cash-count">
      <div class="cash-count__row">
        <ion-select
          data-testid="cash-register-count-type"
          :label="$t('cash_register.count.type')"
          label-placement="stacked"
          fill="outline"
          mode="md"
          interface="popover"
          :value="type"
          @ion-change="type = $event.detail.value === 'opening' ? 'opening' : 'closing'"
        >
          <ion-select-option value="closing">
            {{ $t('cash_register.countTypes.closing') }}
          </ion-select-option>
          <ion-select-option value="opening">
            {{ $t('cash_register.countTypes.opening') }}
          </ion-select-option>
        </ion-select>
        <ion-input
          data-testid="cash-register-count-notes"
          :label="$t('cash_register.count.notes')"
          label-placement="stacked"
          fill="outline"
          mode="md"
          :maxlength="500"
          :value="notes"
          @ion-input="notes = String($event.detail.value ?? '')"
        />
      </div>
      <p
        v-if="!table"
        class="cash-count__hint"
        data-testid="cash-register-count-loading"
      >
        {{ $t('cash_register.count.loading') }}
      </p>
      <template v-else-if="hasTable">
        <template
          v-for="kind in (['bills', 'coins'] as const)"
          :key="kind"
        >
          <h3 class="cash-count__heading">
            {{ $t(`cash_register.count.${kind}`) }}
          </h3>
          <div
            class="cash-count__grid"
            :data-testid="`cash-register-count-${kind}`"
          >
            <ion-input
              v-for="face in table[kind]"
              :key="face"
              :data-testid="`cash-register-count-denom-${face}`"
              :label="faceLabel(face)"
              label-placement="stacked"
              fill="outline"
              mode="md"
              type="number"
              inputmode="numeric"
              min="0"
              step="1"
              :value="boxes[face] ?? ''"
              @ion-input="boxes = { ...boxes, [face]: String($event.detail.value ?? '') }"
            />
          </div>
        </template>
        <p
          class="cash-count__total"
          data-testid="cash-register-count-total"
        >
          {{ $t('cash_register.count.total', { total: formatMoney(total, locale, table.currency) }) }}
        </p>
      </template>
      <template v-else>
        <p
          class="cash-count__hint"
          data-testid="cash-register-count-no-breakdown"
        >
          {{ $t('cash_register.count.noBreakdown', { currency: table.currency }) }}
        </p>
        <MoneyField
          v-model="typedTotal"
          testid="cash-register-count-total-input"
          :label="$t('cash_register.count.totalInput')"
          :error="typedError"
        />
      </template>
    </div>
  </FormModal>
</template>

<style scoped>
.cash-count {
  display: grid;
  gap: 0.75rem;
}
.cash-count__row {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
}
.cash-count__heading {
  margin: 0.25rem 0 0;
  font-size: 1rem;
}
/* Each box is as wide as the longest money label of the drawer needs, three columns on a phone. */
.cash-count__grid {
  display: grid;
  gap: 0.6rem;
  grid-template-columns: repeat(auto-fill, minmax(6.5rem, 1fr));
}
.cash-count__total {
  margin: 0.25rem 0;
  font-weight: 700;
}
.cash-count__hint {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
