<script setup lang="ts">
// The «Tip» row Sales' charge sheet mounts between the amount and the tenders, because Tips declares it (TIP-F02,
// SALE-F39): Sales mounts it by this file's name and its contract (lib/checkout/steps.ts of Sales), so renaming it or
// changing its props, its `update:added` or its `afterCharge` breaks the charge. With tips on, «No tip», the payment
// method's three suggestions with the tip each comes to (the server works them out on the check's total before
// discounts) and, if the settings allow it, «Other amount» in the platform's money field. Once the sale is charged it
// records the tip with that sale and the payment that charged it, under the charge's attempt key and that payment's
// position: a retry records it once.
import { InlineFeedback, MoneyInput, moneyFieldText, parseMoney } from '@erplora/ui/components';
import { ApiError, useLive, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../../../sale/frontend/composables/useT';
import type { Added, StepProps } from '../../../sale/frontend/lib/checkout/steps';
import { formatMoney, useBusinessMoney } from '../../../sale/frontend/lib/format';
import type { SaleOut } from '../../../sale/frontend/operations';
import { afterMethod, type Choice, opening, type Rechosen } from '../lib/choice';
import type { SuggestedTip, SuggestionOut } from '../operations';

const props = defineProps<StepProps>();
const emit = defineEmits<{ 'update:added': [added: Added] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const client = useLiveClient();

const read = useLive('tip.suggestion.get', () => ({ method_id: props.method.id, total: props.total + props.discount }));
const fresh = computed<SuggestionOut | undefined>(() => (read.status.value === 'live' ? read.data.value : undefined));
const offered = computed(() => read.data.value);
const shown = computed(() => offered.value?.enabled !== false);
const loading = computed(() => offered.value === undefined && !read.error.value);

const choice = shallowRef<Choice>({ kind: 'none' });
const customText = shallowRef('');

// The choice is made on the suggestions read for a method; another method's arrive later, and then it is rechosen.
let chosenFor: { method: string; read: SuggestionOut } | null = null;
watch(
  fresh,
  (now) => {
    if (!now) return;
    if (chosenFor?.method !== props.method.id) apply(chosenFor ? afterMethod(choice.value, chosenFor.read, now) : { choice: opening(now) });
    chosenFor = { method: props.method.id, read: now };
  },
  { immediate: true },
);

function apply(next: Rechosen): void {
  choice.value = next.choice;
  if (next.custom !== undefined) customText.value = moneyFieldText(next.custom, locale.value, business.value);
}

const custom = computed(() => parseMoney(customText.value, { money: business.value }));
const amount = computed(() => {
  const now = choice.value;
  if (!shown.value || now.kind === 'none') return 0;
  if (now.kind === 'suggestion') return offered.value?.suggestions[now.index]?.amount ?? 0;
  return custom.value.ok ? (custom.value.cents ?? 0) : 0;
});
const issue = computed(() => (choice.value.kind === 'custom' && !custom.value.ok ? t('tip.step.invalid') : ''));

watch(
  [amount, issue, locale],
  () => emit('update:added', { amount: amount.value, label: t('tip.step.label'), issue: issue.value }),
  { immediate: true },
);

const money = (cents: number): string => formatMoney(cents, locale.value, business.value);
const percent = (value: number): string => new Intl.NumberFormat(locale.value, { style: 'percent' }).format(value / 100);
const pressed = (kind: Choice['kind'], index?: number): 'true' | 'false' =>
  choice.value.kind === kind && (kind !== 'suggestion' || (choice.value as { index: number }).index === index) ? 'true' : 'false';

function pick(next: Choice): void {
  choice.value = next;
}

function nameOf(suggestion: SuggestedTip): string {
  return suggestion.percent === null ? money(suggestion.amount) : percent(suggestion.percent);
}

/** Records the tip chosen with `sale`, charged under `attemptKey`; throws with what to say when it is not saved. */
async function afterCharge(sale: SaleOut, attemptKey: string): Promise<void> {
  const tip = amount.value;
  const payment = sale.payments.find((leg) => leg.extra > 0) ?? sale.payments[0];
  if (tip <= 0 || !payment) return;
  try {
    await client.api.call('tip.tip.add', {
      sale_id: sale.id,
      method_id: payment.method_id,
      amount: tip,
      attempt_key: `${attemptKey}:${payment.position}`,
    });
  } catch (error) {
    // A refusal says why in the server's words; a lost answer, only that it was not saved (the retry is safe).
    const why = error instanceof ApiError && error.status >= 400 && error.status < 500 ? ` ${error.message}` : '';
    throw new Error(`${t('tip.step.notSaved')}${why}`, { cause: error });
  }
}

defineExpose({ afterCharge });
</script>

<template>
  <section
    v-if="shown"
    class="tip-step"
    data-testid="tip-step"
    :aria-label="$t('tip.step.title')"
  >
    <p
      v-if="loading"
      class="tip-step__note"
      role="status"
      data-testid="tip-step-loading"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('tip.step.loading') }}
    </p>
    <InlineFeedback
      v-else-if="read.error.value && !offered"
      tone="danger"
      data-testid="tip-step-error"
    >
      {{ read.error.value.message }}
      <template #actions>
        <ion-button
          fill="clear"
          size="small"
          data-testid="tip-step-retry"
          @click="read.refresh()"
        >
          {{ $t('tip.step.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <template v-else-if="offered">
      <div
        class="tip-step__choices"
        role="group"
        :aria-label="$t('tip.step.title')"
      >
        <ion-button
          class="tip-step__choice"
          data-testid="tip-step-none"
          :fill="pressed('none') === 'true' ? 'solid' : 'outline'"
          :aria-pressed="pressed('none')"
          :disabled="locked"
          @click="pick({ kind: 'none' })"
        >
          {{ $t('tip.step.none') }}
        </ion-button>
        <ion-button
          v-for="(suggestion, index) in offered.suggestions"
          :key="index"
          class="tip-step__choice"
          :data-testid="`tip-step-suggestion-${index}`"
          :fill="pressed('suggestion', index) === 'true' ? 'solid' : 'outline'"
          :aria-pressed="pressed('suggestion', index)"
          :disabled="locked"
          @click="pick({ kind: 'suggestion', index })"
        >
          <span class="tip-step__lines">
            <span>{{ nameOf(suggestion) }}</span>
            <span
              v-if="suggestion.percent !== null"
              class="tip-step__amount"
            >{{ money(suggestion.amount) }}</span>
          </span>
        </ion-button>
        <ion-button
          v-if="offered.allow_custom"
          class="tip-step__choice"
          data-testid="tip-step-custom"
          :fill="pressed('custom') === 'true' ? 'solid' : 'outline'"
          :aria-pressed="pressed('custom')"
          :disabled="locked"
          @click="pick({ kind: 'custom' })"
        >
          {{ $t('tip.step.custom') }}
        </ion-button>
      </div>
      <MoneyInput
        v-if="choice.kind === 'custom'"
        v-model="customText"
        class="tip-step__amount-field"
        testid="tip-step-amount"
        :label="$t('tip.step.amount')"
        :money="business"
        :show-error="!!issue"
        :disabled="locked"
      />
    </template>
  </section>
</template>

<style scoped>
.tip-step {
  margin: 0.1rem 0 0.6rem;
}

.tip-step__choices {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(5.5rem, 1fr));
  gap: 0.4rem;
}

.tip-step__choice {
  --border-radius: 12px;
  min-height: var(--ep-touch-lg, 56px);
  height: auto;
  margin: 0;
  font-weight: 700;
}

.tip-step__lines {
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.2;
}

.tip-step__amount {
  font-size: 0.8rem;
  font-weight: 600;
}

.tip-step__amount-field {
  margin-top: 0.5rem;
}

.tip-step__note {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  color: var(--ion-color-medium, #8b897f);
}
</style>
