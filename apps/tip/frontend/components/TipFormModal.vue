<script setup lang="ts">
// «Record tip» (TIP-F03, TIP-F04, TIP-F05): «Of a sale» — its number, the payment method it was paid by (the active
// ones of Sales, as the tip settings list them) and the amount, for whoever served it — or «To the pool, no ticket»,
// only the cash counted from the jar. «Save» runs `tip.tip.add`; what is missing, a voided sale or a closed drawer is
// said by the server, inside the window. The new row comes back through the list's stream.
import { FormModal, MoneyInput } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonLabel, IonSegment, IonSegmentButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../../../sale/frontend/composables/useT';
import { refusal } from '../../../sale/frontend/lib/refusal';
import { useBusinessMoney } from '../../../../base/frontend/lib/money';
import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';
import { type RecordForm, recordInput } from '../lib/tipInput';

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const money = useBusinessMoney();
const settings = useLive('tip.settings.get', {});
const methods = computed(() => settings.data.value?.methods ?? []);
const command = useCommand('tip.tip.add');

const EMPTY: RecordForm = { target: 'sale', sale: '', methodId: '', amount: '' };
const form = shallowRef<RecordForm>({ ...EMPTY });
/** The key of what the screen could not read in the amount. */
const amountError = shallowRef('');

function set<K extends keyof RecordForm>(field: K, value: RecordForm[K]): void {
  form.value = { ...form.value, [field]: value };
}

watch(
  open,
  (now) => {
    if (!now) return;
    form.value = { ...EMPTY };
    amountError.value = '';
    command.error.value = null;
  },
  { immediate: true },
);

const error = computed(() => refusal(command.error.value, t('tip.form.failed')));

async function save(): Promise<void> {
  const built = recordInput(form.value, money.value);
  if ('errors' in built) {
    amountError.value = built.errors.amount;
    return;
  }
  amountError.value = '';
  try {
    await command.run(built.input as Parameters<typeof command.run>[0]);
  } catch {
    return; // The window shows `command.error`.
  }
  toastSuccess(t('tip.form.done'));
  open.value = false;
}

const canDismiss = useUnsavedFormOnOpen('tip-form', () => `${form.value.sale}${form.value.amount}`, open);
</script>

<template>
  <FormModal
    v-model:open="open"
    :can-dismiss="canDismiss"
    size="sm"
    testid="tip-form"
    :title="$t('tip.form.title')"
    :submit-label="$t('tip.form.save')"
    :cancel-label="$t('tip.form.cancel')"
    :pending="command.pending.value"
    :error="error"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <ion-segment
        data-testid="tip-form-target"
        :value="form.target"
        :aria-label="$t('tip.form.target.label')"
        @ion-change="set('target', $event.detail.value === 'pool' ? 'pool' : 'sale')"
      >
        <ion-segment-button
          value="sale"
          data-testid="tip-form-target-sale"
        >
          <ion-label>{{ $t('tip.form.target.sale') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button
          value="pool"
          data-testid="tip-form-target-pool"
        >
          <ion-label>{{ $t('tip.form.target.pool') }}</ion-label>
        </ion-segment-button>
      </ion-segment>
      <template v-if="form.target === 'sale'">
        <ion-input
          class="ion-margin-top"
          :class="{ 'ion-invalid': !!fieldErrors.sale, 'ion-touched': !!fieldErrors.sale }"
          data-testid="tip-form-sale"
          name="sale"
          :label="$t('tip.form.sale')"
          label-placement="stacked"
          fill="outline"
          mode="md"
          :maxlength="24"
          :value="form.sale"
          :error-text="fieldErrors.sale"
          @ion-input="set('sale', String($event.detail.value ?? ''))"
        />
        <ion-select
          class="ion-margin-top"
          data-testid="tip-form-method"
          name="method_id"
          :label="$t('tip.form.method')"
          label-placement="stacked"
          fill="outline"
          mode="md"
          interface="popover"
          :value="form.methodId"
          @ion-change="set('methodId', String($event.detail.value ?? ''))"
        >
          <ion-select-option
            v-for="method in methods"
            :key="method.method_id"
            :value="method.method_id"
          >
            {{ method.method_name }}
          </ion-select-option>
        </ion-select>
      </template>
      <p
        v-else
        class="ion-margin-top"
        data-testid="tip-form-pool-hint"
      >
        {{ $t('tip.form.poolHint') }}
      </p>
      <div class="ion-margin-top">
        <MoneyInput
          :model-value="form.amount"
          testid="tip-form-amount"
          :label="$t('tip.form.amount')"
          :money="money"
          :error-text="amountError ? $t(amountError) : fieldErrors.amount"
          :show-error="!!amountError || !!fieldErrors.amount"
          @update:model-value="set('amount', $event)"
        />
      </div>
    </template>
  </FormModal>
</template>
