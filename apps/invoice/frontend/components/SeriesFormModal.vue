<script setup lang="ts">
// «New numbering series» and «Edit series <code>» (INVOICE-F12, F13; the old panel of the Series table): Code,
// Name, Invoice type (F1–R5), Year (the business's to begin with), Prefix (empty = the code), Number format
// and Next number (to continue another system), Active and Default series, with the hints of the old screen.
// Editing, code, type and year are locked, and once the series has numbered a document so are prefix, format
// and next number (it says why: the number is part of the VeriFactu chain); «Next number» is the one the
// server will hand out. Saving runs `invoice.series.create`, or `invoice.series.update` with only what
// changed, says so and closes; the table catches up by itself. A refusal stays in the window, under its
// field when it is one.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonItem, IonSelect, IonSelectOption, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { TYPE_CODES } from '../lib/invoice';
import { refusal } from '../lib/refusal';
import type { InvoiceType, SeriesOut, SeriesUpdateIn } from '../operations';

const props = defineProps<{
  /** The series to edit; none = a new one. */
  series: SeriesOut | null;
  /** The year a new series starts on (the business's). */
  year: number;
}>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const creating = useCommand('invoice.series.create');
const updating = useCommand('invoice.series.update');

interface Form {
  code: string;
  name: string;
  invoiceType: InvoiceType;
  year: string;
  prefix: string;
  format: string;
  nextNumber: string;
  active: boolean;
  isDefault: boolean;
}

const blank = (): Form => ({
  code: '',
  name: '',
  invoiceType: 'F1',
  year: String(props.year),
  prefix: '',
  format: '',
  nextNumber: '1',
  active: true,
  isDefault: false,
});

const fromSeries = (series: SeriesOut): Form => ({
  code: series.code,
  name: series.name,
  invoiceType: series.invoice_type,
  year: String(series.year),
  prefix: series.prefix,
  format: series.format,
  nextNumber: String(series.current_number + 1),
  active: series.is_active,
  isDefault: series.is_default,
});

const form = ref<Form>(blank());
const editing = computed(() => props.series !== null);
const locked = computed(() => props.series?.format_locked ?? false);
const command = computed(() => (editing.value ? updating : creating));

watch(
  open,
  (now) => {
    if (!now) return;
    form.value = props.series ? fromSeries(props.series) : blank();
    creating.error.value = null;
    updating.error.value = null;
  },
  { immediate: true },
);

const error = computed(() => refusal(command.value.error.value, t('invoice.series.form.failed')));
const fieldErrors = computed<Record<string, string | undefined>>(() => {
  const fields: Record<string, string | undefined> = { ...(error.value?.fields ?? {}) };
  return { ...fields, nextNumber: fields.next_number, invoiceType: fields.invoice_type };
});
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const title = computed(() =>
  editing.value ? t('invoice.series.form.editTitle', { code: props.series?.code ?? '' }) : t('invoice.series.form.createTitle'),
);

function set<K extends keyof Form>(field: K, value: Form[K]): void {
  form.value = { ...form.value, [field]: value };
}

const whole = (text: string): number => Number.parseInt(text.trim(), 10);

/** What an edit changes: only the fields that differ from the series (locked ones never travel). */
function changes(series: SeriesOut): SeriesUpdateIn {
  const out: SeriesUpdateIn = { series_id: series.id };
  if (form.value.name.trim() !== series.name) out.name = form.value.name.trim();
  if (!locked.value) {
    if (form.value.prefix.trim() !== series.prefix) out.prefix = form.value.prefix.trim();
    if (form.value.format.trim() !== series.format) out.format = form.value.format.trim();
    if (whole(form.value.nextNumber) !== series.current_number + 1) out.next_number = whole(form.value.nextNumber);
  }
  if (form.value.active !== series.is_active) out.is_active = form.value.active;
  if (form.value.isDefault !== series.is_default) out.is_default = form.value.isDefault;
  return out;
}

async function save(): Promise<void> {
  let saved: SeriesOut;
  try {
    if (props.series) {
      saved = await updating.run(changes(props.series));
    } else {
      saved = await creating.run({
        code: form.value.code.trim(),
        name: form.value.name.trim(),
        invoice_type: form.value.invoiceType,
        year: whole(form.value.year),
        prefix: form.value.prefix.trim(),
        format: form.value.format.trim(),
        next_number: whole(form.value.nextNumber),
        is_active: form.value.active,
        is_default: form.value.isDefault,
      });
    }
  } catch {
    return; // The window shows the command's error.
  }
  void toastSuccess(t(editing.value ? 'invoice.series.form.saved' : 'invoice.series.form.created', { code: saved.code }));
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="invoice-series-form"
    :title="title"
    :submit-label="editing ? $t('invoice.series.form.save') : $t('invoice.series.form.create')"
    :cancel-label="$t('invoice.cancel')"
    :pending="command.pending.value"
    :error="error"
    :submit-disabled="!editing && !form.code.trim()"
    @submit="save"
  >
    <div class="invoice-series-form">
      <ion-input
        data-testid="invoice-series-code"
        :label="$t('invoice.series.form.code')"
        label-placement="floating"
        fill="outline"
        mode="md"
        autocapitalize="characters"
        :maxlength="20"
        :disabled="editing"
        :value="form.code"
        :error-text="fieldErrors.code"
        :class="invalid(fieldErrors.code)"
        @ion-input="set('code', String($event.detail.value ?? ''))"
      />
      <ion-input
        data-testid="invoice-series-name"
        :label="$t('invoice.series.form.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="120"
        :value="form.name"
        :error-text="fieldErrors.name"
        :class="invalid(fieldErrors.name)"
        @ion-input="set('name', String($event.detail.value ?? ''))"
      />
      <ion-select
        data-testid="invoice-series-type"
        :label="$t('invoice.series.form.type')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :disabled="editing"
        :value="form.invoiceType"
        :error-text="fieldErrors.invoiceType"
        @ion-change="set('invoiceType', $event.detail.value as InvoiceType)"
      >
        <ion-select-option
          v-for="code in TYPE_CODES"
          :key="code"
          :value="code"
        >
          {{ $t(`invoice.typeNames.${code}`) }}
        </ion-select-option>
      </ion-select>
      <ion-input
        data-testid="invoice-series-year"
        :label="$t('invoice.series.form.year')"
        label-placement="floating"
        fill="outline"
        mode="md"
        inputmode="numeric"
        :disabled="editing"
        :value="form.year"
        :error-text="fieldErrors.year"
        :class="invalid(fieldErrors.year)"
        @ion-input="set('year', String($event.detail.value ?? ''))"
      />
      <ion-input
        data-testid="invoice-series-prefix"
        :label="$t('invoice.series.form.prefix')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="20"
        :disabled="locked"
        :value="form.prefix"
        :error-text="fieldErrors.prefix"
        :class="invalid(fieldErrors.prefix)"
        @ion-input="set('prefix', String($event.detail.value ?? ''))"
      />
      <ion-input
        data-testid="invoice-series-format"
        :label="$t('invoice.series.form.format')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="60"
        :disabled="locked"
        :value="form.format"
        :error-text="fieldErrors.format"
        :class="invalid(fieldErrors.format)"
        @ion-input="set('format', String($event.detail.value ?? ''))"
      />
      <ion-input
        data-testid="invoice-series-next-number"
        :label="$t('invoice.series.form.nextNumber')"
        label-placement="floating"
        fill="outline"
        mode="md"
        inputmode="numeric"
        :disabled="locked"
        :value="form.nextNumber"
        :error-text="fieldErrors.nextNumber"
        :class="invalid(fieldErrors.nextNumber)"
        @ion-input="set('nextNumber', String($event.detail.value ?? ''))"
      />
      <p
        v-if="!editing"
        class="invoice-series-form__hint"
        data-testid="invoice-series-code-hint"
      >
        {{ $t('invoice.series.form.codeHint') }}
      </p>
      <p class="invoice-series-form__hint">
        {{ $t('invoice.series.form.prefixHint') }}
      </p>
      <p
        class="invoice-series-form__hint"
        data-testid="invoice-series-format-hint"
      >
        {{ $t('invoice.series.form.formatHint') }}
      </p>
      <InlineFeedback
        v-if="locked"
        tone="warning"
        icon="lock-closed-outline"
        data-testid="invoice-series-format-locked"
      >
        {{ $t('invoice.series.form.lockedHint') }}
      </InlineFeedback>
      <p
        v-if="series"
        class="invoice-series-form__hint"
        data-testid="invoice-series-preview"
      >
        {{ $t('invoice.series.form.preview') }}: <strong>{{ series.next_number }}</strong>
      </p>
      <ion-item lines="none">
        <ion-toggle
          data-testid="invoice-series-active"
          :checked="form.active"
          @ion-change="set('active', !!$event.detail.checked)"
        >
          {{ $t('invoice.series.form.active') }}
        </ion-toggle>
      </ion-item>
      <ion-item lines="none">
        <ion-toggle
          data-testid="invoice-series-default"
          :checked="form.isDefault"
          @ion-change="set('isDefault', !!$event.detail.checked)"
        >
          {{ $t('invoice.series.form.default') }}
        </ion-toggle>
      </ion-item>
    </div>
  </FormModal>
</template>

<style scoped>
.invoice-series-form {
  display: grid;
  gap: 12px;
}
.invoice-series-form__hint {
  margin: -0.25rem 0 0;
  font-size: 0.72rem;
  color: var(--ion-color-medium, #8a8577);
}
.invoice-series-form ion-item {
  --background: transparent;
  --padding-start: 0;
  --inner-padding-end: 0;
}
</style>
