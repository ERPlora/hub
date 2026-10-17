<script setup lang="ts">
// SALE-F35: «New section» (the «+» of Sections) or «Edit section» (a row's «Edit»), as the old
// table's create panel: Name, «VAT charged» (TaxCategoryPicker, searched on the server) and Position,
// «Add» or «Save». No VAT chosen: «Choose the VAT this section charges.» under it, and nothing is sent.
// «VAT» is the business territory's tax («IGIC» in the Canary Islands, «IPSI» in Ceuta and Melilla).
// An edit sends only what changed (nothing changed: it just closes). It closes once the server saved it
// — the live list paints the department with the rate its category charges —; a refusal keeps it open
// with what was typed (`refusal`).
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useTaxName } from '../../composables/useTaxName';
import { useLocale, useT } from '../../composables/useT';
import { refusal } from '../../lib/refusal';
import { taxLabel } from '../../lib/taxLabel';
import type { DepartmentOut } from '../../operations';
import TaxCategoryPicker from '../TaxCategoryPicker.vue';

const props = defineProps<{
  /** The department to edit; `null` adds a new one. */
  department: DepartmentOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const taxName = useTaxName();
const locale = useLocale();
const create = useCommand('sale.department.create');
const update = useCommand('sale.department.update');

const name = ref('');
const taxKey = ref('');
const order = ref('0');
/** «Save» was tapped with no VAT chosen. */
const taxMissing = ref(false);
/** The business has no tax category to choose: nothing can be saved (the picker says why). */
const noCategories = ref(false);

const editing = computed(() => props.department !== null);
const pending = computed(() => create.pending.value || update.pending.value);
const error = computed(() => refusal(create.error.value ?? update.error.value, t('sale.departments.saveFailed')));
const complete = computed(() => name.value.trim() !== '' && !noCategories.value);
/** How the department's VAT reads in its row: the picker shows it until another one is chosen. */
const currentTax = computed(() =>
  props.department ? taxLabel(props.department.tax_category_name, props.department.tax_rate_pct, locale.value, props.department.tax_category_key) : undefined,
);
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

// Every opening starts from the department being edited (or blank) and with no refusal left over.
watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    name.value = props.department?.name ?? '';
    taxKey.value = props.department?.tax_category_key ?? '';
    order.value = String(props.department?.sort_order ?? 0);
    taxMissing.value = false;
    noCategories.value = false;
    create.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

watch(taxKey, (key) => {
  if (key) taxMissing.value = false;
});

/** The Position as the server takes it: blank is its first place, 0. */
const position = (): number => (order.value.trim() === '' ? 0 : Number(order.value));

async function save(): Promise<void> {
  if (!taxKey.value) {
    taxMissing.value = true;
    return;
  }
  const department = props.department;
  const fields = { name: name.value.trim(), tax_category_key: taxKey.value, sort_order: position() };
  try {
    if (!department) {
      await create.run(fields);
    } else {
      const changed = {
        ...(fields.name !== department.name ? { name: fields.name } : {}),
        ...(fields.tax_category_key !== department.tax_category_key ? { tax_category_key: fields.tax_category_key } : {}),
        ...(fields.sort_order !== department.sort_order ? { sort_order: fields.sort_order } : {}),
      };
      if (Object.keys(changed).length) await update.run({ id: department.id, ...changed });
    }
  } catch {
    return; // The dialog paints the refusal.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="sale-department-form"
    :title="editing ? $t('sale.departments.form.editTitle') : $t('sale.departments.form.createTitle')"
    :submit-label="editing ? $t('sale.departments.form.save') : $t('sale.departments.form.add')"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="sale-backoffice-form">
        <ion-input
          data-testid="sale-department-form-name"
          :value="name"
          :label="$t('sale.departments.columns.name')"
          :placeholder="$t('sale.departments.form.namePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="60"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="name = String($event.detail.value ?? '')"
        />
        <TaxCategoryPicker
          v-model="taxKey"
          v-model:empty="noCategories"
          :label="$t('sale.departments.columns.taxCategory', { tax: taxName })"
          :placeholder="$t('sale.departments.form.taxPlaceholder', { tax: taxName })"
          testid="sale-department-form-tax"
          :chosen-label="currentTax"
          :error-text="taxMissing ? $t('sale.departments.taxCategoryMissing', { tax: taxName }) : fieldErrors.tax_category_key"
        />
        <ion-input
          data-testid="sale-department-form-order"
          :value="order"
          type="number"
          inputmode="numeric"
          min="0"
          step="1"
          :label="$t('sale.departments.columns.sortOrder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.sort_order"
          :class="invalid(fieldErrors.sort_order)"
          @ion-input="order = String($event.detail.value ?? '')"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.sale-backoffice-form {
  display: grid;
  gap: 14px;
}
</style>
