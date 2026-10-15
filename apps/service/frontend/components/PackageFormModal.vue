<script setup lang="ts">
// SERVICE-F12, F13: the old packages panel as a dialog. «New package» asks for Name, Discount type
// (Percentage or Fixed amount) and its value, Closed price, Validity (days) and Uses, each with the old
// help, and «Services included»: a row per offered service (searched) with its Sessions, «Remove line»
// and «Add service». «Create package» needs a name and a line. «Editing package — {name}» changes
// everything but the lines (shown, fixed) and sends only what changed; an emptied closed price,
// validity or uses removes it (null). Refusals stay in the dialog, under their field.
import { Combo, type ComboOption, FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { percentFieldText, readPercentBp } from '../lib/format';
import { moneyFieldText, parseMoney } from '../lib/money';
import { searchServices } from '../lib/pickers';
import type { DiscountType, PackageIn, PackageOut, PackagePatchIn } from '../operations';
import MoneyInput from './MoneyInput.vue';

const props = defineProps<{
  /** The package being edited; `null` = «New package». */
  pkg: PackageOut | null;
}>();
const open = defineModel<boolean>('open', { default: false });

interface Line {
  key: number;
  service: ComboOption | null;
  sessions: string;
}

interface Form {
  name: string;
  discountType: DiscountType;
  percent: string;
  amount: string;
  fixedPrice: string;
  validity: string;
  uses: string;
  lines: Line[];
}

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const searchOffered = computed(() => searchServices(client, locale.value));
const creation = useCommand('service.package.create');
const update = useCommand('service.package.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.pkg ? update.error.value : creation.error.value));
const title = computed(() => (props.pkg ? t('service.packages.form.titleEdit', { name: props.pkg.name }) : t('service.packages.form.titleNew')));

let lineKey = 0;
const newLine = (): Line => ({ key: ++lineKey, service: null, sessions: '1' });

function fromPackage(current: PackageOut | null): Form {
  if (!current) {
    return { name: '', discountType: 'percentage', percent: '', amount: '', fixedPrice: '', validity: '', uses: '', lines: [newLine()] };
  }
  return {
    name: current.name,
    discountType: current.discount_type,
    percent: current.discount_percent_bp ? percentFieldText(current.discount_percent_bp, locale.value) : '',
    amount: current.discount_amount ? moneyFieldText(current.discount_amount, locale.value) : '',
    fixedPrice: moneyFieldText(current.fixed_price, locale.value),
    validity: current.validity_days === null ? '' : String(current.validity_days),
    uses: current.max_uses === null ? '' : String(current.max_uses),
    lines: [],
  };
}

const form = ref<Form>(fromPackage(null));
const tried = ref(false);

watch(
  () => [open.value, props.pkg?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromPackage(props.pkg);
    tried.value = false;
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const completeLines = computed(() => form.value.lines.filter((line) => line.service));
/** The lines of the last create, in the order they were sent: a 422 names them by that position. */
const sentKeys = ref<number[]>([]);
/** The field of the server's refusal for `line` (`items.<sent position>.<field>`). */
const lineField = (line: Line, field: string): string => `items.${sentKeys.value.indexOf(line.key)}.${field}`;
const percentBp = computed(() => readPercentBp(form.value.percent));
const percentError = computed(() =>
  form.value.discountType === 'percentage' && tried.value && percentBp.value === null ? t('service.packages.form.percentInvalid') : undefined,
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
/** A whole number as the server takes it, or null when empty; anything else as typed, for the server to refuse. */
const wholeOrNull = (value: string): number | null => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  return /^\d+$/.test(trimmed) ? Number(trimmed) : (trimmed as unknown as number);
};
const money = (value: string): number | null | undefined => {
  const read = parseMoney(value);
  return read.ok ? read.cents : undefined;
};

function setLine(index: number, part: Partial<Line>): void {
  form.value = { ...form.value, lines: form.value.lines.map((line, i) => (i === index ? { ...line, ...part } : line)) };
}

/** The money and discount of the form, or `null` when something typed is not an amount (it says so). */
function amounts() {
  const f = form.value;
  const fixedPrice = money(f.fixedPrice);
  const amount = money(f.amount);
  if (fixedPrice === undefined || amount === undefined || (f.discountType === 'percentage' && percentBp.value === null)) return null;
  return { fixedPrice, amount: amount ?? 0, percent: percentBp.value ?? 0 };
}

function patch(current: PackageOut, read: NonNullable<ReturnType<typeof amounts>>): PackagePatchIn {
  const f = form.value;
  const out: PackagePatchIn = { id: current.id };
  if (f.name.trim() !== current.name) out.name = f.name.trim();
  if (f.discountType !== current.discount_type) out.discount_type = f.discountType;
  if (f.discountType === 'percentage' && read.percent !== current.discount_percent_bp) out.discount_percent_bp = read.percent;
  if (f.discountType === 'fixed' && read.amount !== current.discount_amount) out.discount_amount = read.amount;
  if (read.fixedPrice !== current.fixed_price) out.fixed_price = read.fixedPrice;
  const validity = wholeOrNull(f.validity);
  if (validity !== current.validity_days) out.validity_days = validity;
  const uses = wholeOrNull(f.uses);
  if (uses !== current.max_uses) out.max_uses = uses;
  return out;
}

function creationBody(read: NonNullable<ReturnType<typeof amounts>>): PackageIn {
  const f = form.value;
  return {
    name: f.name.trim(),
    discount_type: f.discountType,
    ...(f.discountType === 'percentage' ? { discount_percent_bp: read.percent } : { discount_amount: read.amount }),
    fixed_price: read.fixedPrice,
    validity_days: wholeOrNull(f.validity),
    max_uses: wholeOrNull(f.uses),
    items: completeLines.value.map((line) => ({ service_id: line.service!.id, sessions: wholeOrNull(line.sessions) ?? 1 })),
  };
}

async function save(): Promise<void> {
  tried.value = true;
  const read = amounts();
  if (!read) return;
  try {
    if (props.pkg) await update.run(patch(props.pkg, read));
    else {
      sentKeys.value = completeLines.value.map((line) => line.key);
      await creation.run(creationBody(read));
    }
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="service-package-form"
    :title="title"
    :submit-label="pkg ? $t('service.packages.form.save') : $t('service.packages.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim() || (!pkg && completeLines.length === 0)"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="service-package-form">
        <ion-input
          data-testid="service-package-form-name"
          :value="form.name"
          :label="$t('service.packages.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <ion-select
          data-testid="service-package-form-discount_type"
          :value="form.discountType"
          :label="$t('service.packages.form.discountType')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="form = { ...form, discountType: $event.detail.value === 'fixed' ? 'fixed' : 'percentage' }"
        >
          <ion-select-option value="percentage">
            {{ $t('service.packages.form.percentage') }}
          </ion-select-option>
          <ion-select-option value="fixed">
            {{ $t('service.packages.form.fixed') }}
          </ion-select-option>
        </ion-select>
        <ion-input
          v-if="form.discountType === 'percentage'"
          data-testid="service-package-form-discount_percent"
          type="text"
          inputmode="decimal"
          :value="form.percent"
          :label="$t('service.packages.form.discountPercent')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="percentError || fieldErrors.discount_percent_bp"
          :class="invalid(percentError || fieldErrors.discount_percent_bp)"
          @ion-input="form = { ...form, percent: text($event.detail.value) }"
        />
        <MoneyInput
          v-else
          testid="service-package-form-discount_amount"
          :model-value="form.amount"
          :label="t('service.packages.form.discountAmount')"
          :error-text="fieldErrors.discount_amount"
          :show-error="tried"
          @update:model-value="form = { ...form, amount: $event }"
        />
        <MoneyInput
          testid="service-package-form-fixed_price"
          :model-value="form.fixedPrice"
          :label="t('service.packages.form.fixedPrice')"
          :helper-text="t('service.packages.form.fixedPriceHelp')"
          :error-text="fieldErrors.fixed_price"
          :show-error="tried"
          @update:model-value="form = { ...form, fixedPrice: $event }"
        />
        <ion-input
          data-testid="service-package-form-validity_days"
          type="number"
          inputmode="numeric"
          min="1"
          :value="form.validity"
          :label="$t('service.packages.form.validity')"
          :helper-text="$t('service.packages.form.validityHelp')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.validity_days"
          :class="invalid(fieldErrors.validity_days)"
          @ion-input="form = { ...form, validity: text($event.detail.value) }"
        />
        <ion-input
          data-testid="service-package-form-max_uses"
          type="number"
          inputmode="numeric"
          min="1"
          :value="form.uses"
          :label="$t('service.packages.form.uses')"
          :helper-text="$t('service.packages.form.usesHelp')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.max_uses"
          :class="invalid(fieldErrors.max_uses)"
          @ion-input="form = { ...form, uses: text($event.detail.value) }"
        />
        <h3 class="service-package-form__lines-title">
          {{ $t('service.packages.form.lines') }}
        </h3>
        <template v-if="pkg">
          <p
            class="service-package-form__hint"
            data-testid="service-package-form-lines-fixed"
          >
            {{ $t('service.packages.form.linesFixed') }}
          </p>
          <ul
            class="service-package-form__fixed"
            data-testid="service-package-form-lines"
          >
            <li
              v-for="item in pkg.items"
              :key="item.id"
            >
              {{ item.service_name }} × {{ item.sessions }}
            </li>
          </ul>
        </template>
        <template v-else>
          <div
            v-for="(line, index) in form.lines"
            :key="line.key"
            class="service-package-form__line"
          >
            <Combo
              :testid="`service-package-form-line-service-${index}`"
              :model-value="line.service"
              :search="searchOffered"
              :label="t('service.packages.form.service')"
              :error-text="fieldErrors[lineField(line, 'service_id')]"
              @update:model-value="setLine(index, { service: $event })"
            />
            <ion-input
              :data-testid="`service-package-form-line-sessions-${index}`"
              type="number"
              inputmode="numeric"
              min="1"
              :value="line.sessions"
              :label="$t('service.packages.form.sessions')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :error-text="fieldErrors[lineField(line, 'sessions')]"
              @ion-input="setLine(index, { sessions: text($event.detail.value) })"
            />
            <ion-button
              :data-testid="`service-package-form-remove-line-${index}`"
              fill="clear"
              size="small"
              @click="form = { ...form, lines: form.lines.filter((_, i) => i !== index) }"
            >
              {{ $t('service.packages.form.removeLine') }}
            </ion-button>
          </div>
          <ion-button
            data-testid="service-package-form-add-line"
            fill="outline"
            size="small"
            @click="form = { ...form, lines: [...form.lines, newLine()] }"
          >
            {{ $t('service.packages.form.addLine') }}
          </ion-button>
          <InlineFeedback
            v-if="completeLines.length === 0 || fieldErrors.items"
            tone="warning"
            data-testid="service-package-form-no-lines"
          >
            {{ fieldErrors.items || t('service.packages.form.noLines') }}
          </InlineFeedback>
        </template>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.service-package-form {
  display: grid;
  gap: 14px;
}
.service-package-form__lines-title {
  margin: 4px 0 0;
  font-size: 1rem;
  font-weight: 600;
}
.service-package-form__hint {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.service-package-form__fixed {
  margin: 0;
  padding-left: 1.2rem;
}
.service-package-form__line {
  display: grid;
  grid-template-columns: minmax(10rem, 2fr) minmax(6rem, 1fr) auto;
  align-items: center;
  gap: 8px;
}
</style>
